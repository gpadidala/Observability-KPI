"""KPI Calculator: Data Loss Rate.

Computes the percentage of observability data lost (dropped / discarded)
relative to the total volume ingested, broken down by pillar:

    Data Loss Rate = (Dropped Events / Total Events) x 100

Each pillar has its own pair of Prometheus counters for dropped vs. total
events.  For time ranges exceeding 30 days the numerator and denominator
are accumulated independently across chunks before computing the final rate.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from clients.prometheus_client import PrometheusQueryExecutor
from kpis.base import BaseKPICalculator
from time_window.chunker import TimeWindowChunker

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-pillar metric definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class _PillarMetrics:
    """Prometheus counter pair for a single observability pillar."""

    pillar: str
    dropped_query: str
    total_query: str


_PILLAR_METRICS: list[_PillarMetrics] = [
    _PillarMetrics(
        pillar="mimir",
        dropped_query="sum(increase(cortex_discarded_samples_total[{range}]))",
        total_query="sum(increase(cortex_ingester_ingested_samples_total[{range}]))",
    ),
    _PillarMetrics(
        pillar="loki",
        dropped_query="sum(increase(loki_discarded_entries_total[{range}]))",
        total_query="sum(increase(loki_ingester_entries_total[{range}]))",
    ),
    _PillarMetrics(
        pillar="tempo",
        dropped_query="sum(increase(tempo_discarded_spans_total[{range}]))",
        total_query="sum(increase(tempo_ingester_spans_received_total[{range}]))",
    ),
    _PillarMetrics(
        pillar="pyroscope",
        dropped_query="sum(increase(pyroscope_discarded_profiles_total[{range}]))",
        total_query="sum(increase(pyroscope_ingested_profiles_total[{range}]))",
    ),
]


class DataLossRateCalculator(BaseKPICalculator):
    """Calculate the Data Loss Rate KPI across all observability pillars.

    The calculator queries Prometheus for dropped and total event counters
    for each pillar (Mimir, Loki, Tempo, Pyroscope).  For ranges longer
    than 30 days the :class:`TimeWindowChunker` is used to split the range
    into safe windows; numerator (dropped) and denominator (total) are
    summed across chunks before computing the percentage.
    """

    def __init__(self, chunker: TimeWindowChunker | None = None) -> None:
        self._chunker = chunker or TimeWindowChunker()

    # ------------------------------------------------------------------
    # BaseKPICalculator interface
    # ------------------------------------------------------------------

    @property
    def kpi_name(self) -> str:
        return "Data Loss Rate"

    @property
    def unit(self) -> str:
        return "%"

    async def calculate(
        self,
        prometheus_client: PrometheusQueryExecutor,
        start: datetime,
        end: datetime,
        environment: str,
    ) -> dict[str, Any]:
        """Calculate the Data Loss Rate KPI.

        Returns a result dict with:
        - ``value``: Overall data loss rate percentage.
        - ``details.pillar_breakdown``: Per-pillar dropped, total, and rate.
        """
        pillar_results: list[dict[str, Any]] = []
        total_dropped: float = 0.0
        total_events: float = 0.0
        errors: list[str] = []

        tasks = [
            self._calculate_pillar(prometheus_client, pm, start, end)
            for pm in _PILLAR_METRICS
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for pm, result in zip(_PILLAR_METRICS, results):
            if isinstance(result, Exception):
                error_msg = f"{pm.pillar}: {result}"
                logger.error("Data loss rate calculation failed for %s: %s", pm.pillar, result)
                errors.append(error_msg)
                pillar_results.append({
                    "pillar": pm.pillar,
                    "dropped": None,
                    "total": None,
                    "loss_rate_pct": None,
                    "error": error_msg,
                })
                continue

            dropped, total, rate = result
            pillar_results.append({
                "pillar": pm.pillar,
                "dropped": round(dropped, 2),
                "total": round(total, 2),
                "loss_rate_pct": round(rate, 6),
                "error": None,
            })
            total_dropped += dropped
            total_events += total

        overall_rate = self._safe_divide(total_dropped, total_events) * 100.0

        return self._build_result(
            value=overall_rate,
            details={
                "pillar_breakdown": pillar_results,
                "total_dropped": round(total_dropped, 2),
                "total_events": round(total_events, 2),
                "environment": environment,
                "chunked": self._chunker.needs_chunking(start, end),
            },
            error="; ".join(errors) if errors else None,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _calculate_pillar(
        self,
        prom: PrometheusQueryExecutor,
        metrics: _PillarMetrics,
        start: datetime,
        end: datetime,
    ) -> tuple[float, float, float]:
        """Calculate dropped, total, and loss-rate for a single pillar.

        Returns (dropped, total, loss_rate_pct).
        """
        chunks = self._chunker.chunk(start, end)

        dropped_values: list[float] = []
        total_values: list[float] = []

        for chunk in chunks:
            duration_seconds = int((chunk.end - chunk.start).total_seconds())
            range_str = f"{duration_seconds}s"

            dropped_query = metrics.dropped_query.replace("{range}", range_str)
            total_query = metrics.total_query.replace("{range}", range_str)

            dropped_val, total_val = await asyncio.gather(
                prom.get_metric_value(dropped_query, chunk.start, chunk.end, default=0.0),
                prom.get_metric_value(total_query, chunk.start, chunk.end, default=0.0),
            )

            dropped_values.append(dropped_val or 0.0)
            total_values.append(total_val or 0.0)

        total_dropped = sum(dropped_values)
        total_events = sum(total_values)
        loss_rate = self._safe_divide(total_dropped, total_events) * 100.0

        logger.info(
            "Data loss rate for %s: %.4f%% (dropped=%.0f, total=%.0f, chunks=%d)",
            metrics.pillar,
            loss_rate,
            total_dropped,
            total_events,
            len(chunks),
        )

        return total_dropped, total_events, loss_rate
