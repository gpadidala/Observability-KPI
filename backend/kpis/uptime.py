"""KPI Calculator: Uptime / Availability per Pillar.

Computes the availability percentage for each observability pillar by
measuring the ratio of successful requests to total requests:

    Uptime % = (Successful Requests / Total Requests) x 100

Each pillar has separate ingest (write) and read (query) SLIs.  The
overall pillar uptime is the weighted average of its ingest and read
availability.  Platform-wide availability is the weighted average across
all pillars.

For time ranges exceeding 30 days, numerator and denominator are summed
independently across chunks before computing the rate (the mathematically
correct approach for ratio aggregation).
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
# SLI definitions per pillar
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class _SLI:
    """A single Service Level Indicator with success and total queries."""

    pillar: str
    name: str
    success_query: str
    total_query: str


_SLIS: list[_SLI] = [
    # ---- Grafana UI ----
    _SLI(
        pillar="grafana",
        name="ui_availability",
        success_query=(
            'sum(increase(grafana_http_request_duration_seconds_count{{status_code=~"2.."}}[{range}]))'
        ),
        total_query=(
            "sum(increase(grafana_http_request_duration_seconds_count[{range}]))"
        ),
    ),
    # ---- Mimir (Metrics) ----
    _SLI(
        pillar="mimir",
        name="ingest_availability",
        success_query=(
            'sum(increase(cortex_ingester_ingested_samples_total[{range}]))'
        ),
        total_query=(
            "sum(increase(cortex_ingester_ingested_samples_total[{range}])) "
            "+ sum(increase(cortex_discarded_samples_total[{range}]))"
        ),
    ),
    _SLI(
        pillar="mimir",
        name="read_availability",
        success_query=(
            'sum(increase(cortex_query_frontend_queries_total{{status_code=~"2.."}}[{range}]))'
        ),
        total_query=(
            "sum(increase(cortex_query_frontend_queries_total[{range}]))"
        ),
    ),
    # ---- Loki (Logs) ----
    _SLI(
        pillar="loki",
        name="ingest_availability",
        success_query=(
            'sum(increase(loki_distributor_lines_received_total[{range}]))'
        ),
        total_query=(
            "sum(increase(loki_distributor_lines_received_total[{range}])) "
            "+ sum(increase(loki_discarded_entries_total[{range}]))"
        ),
    ),
    _SLI(
        pillar="loki",
        name="read_availability",
        success_query=(
            'sum(increase(loki_query_frontend_queries_total{{status_code=~"2.."}}[{range}]))'
        ),
        total_query=(
            "sum(increase(loki_query_frontend_queries_total[{range}]))"
        ),
    ),
    # ---- Tempo (Traces) ----
    _SLI(
        pillar="tempo",
        name="ingest_availability",
        success_query=(
            "sum(increase(tempo_ingester_spans_received_total[{range}]))"
        ),
        total_query=(
            "sum(increase(tempo_ingester_spans_received_total[{range}])) "
            "+ sum(increase(tempo_discarded_spans_total[{range}]))"
        ),
    ),
    _SLI(
        pillar="tempo",
        name="read_availability",
        success_query=(
            'sum(increase(tempo_query_frontend_queries_total{{status_code=~"2.."}}[{range}]))'
        ),
        total_query=(
            "sum(increase(tempo_query_frontend_queries_total[{range}]))"
        ),
    ),
    # ---- Pyroscope (Profiles) ----
    _SLI(
        pillar="pyroscope",
        name="ingest_availability",
        success_query=(
            "sum(increase(pyroscope_ingested_profiles_total[{range}]))"
        ),
        total_query=(
            "sum(increase(pyroscope_ingested_profiles_total[{range}])) "
            "+ sum(increase(pyroscope_discarded_profiles_total[{range}]))"
        ),
    ),
    _SLI(
        pillar="pyroscope",
        name="read_availability",
        success_query=(
            'sum(increase(pyroscope_query_frontend_queries_total{{status_code=~"2.."}}[{range}]))'
        ),
        total_query=(
            "sum(increase(pyroscope_query_frontend_queries_total[{range}]))"
        ),
    ),
]


class UptimeCalculator(BaseKPICalculator):
    """Calculate the Uptime / Availability KPI for each observability pillar.

    Each pillar's availability is computed from ingest (write) and read
    (query) SLIs.  Grafana UI has a single availability SLI based on
    HTTP request success rate.

    For time ranges exceeding 30 days, numerator and denominator counters
    are summed across :class:`TimeWindowChunker` chunks before computing
    the ratio -- the mathematically correct approach for availability
    percentages.
    """

    def __init__(self, chunker: TimeWindowChunker | None = None) -> None:
        self._chunker = chunker or TimeWindowChunker()

    # ------------------------------------------------------------------
    # BaseKPICalculator interface
    # ------------------------------------------------------------------

    @property
    def kpi_name(self) -> str:
        return "Uptime"

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
        """Calculate uptime for each pillar and overall platform availability.

        Returns a result dict with:
        - ``value``: Overall platform availability percentage.
        - ``details.pillar_breakdown``: Per-pillar uptime with SLI-level detail.
        """
        errors: list[str] = []

        # Query all SLIs in parallel
        tasks = [
            self._calculate_sli(prometheus_client, sli, start, end)
            for sli in _SLIS
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Group SLI results by pillar
        pillar_slis: dict[str, list[dict[str, Any]]] = {}
        for sli, result in zip(_SLIS, results):
            if sli.pillar not in pillar_slis:
                pillar_slis[sli.pillar] = []

            if isinstance(result, Exception):
                error_msg = f"{sli.pillar}/{sli.name}: {result}"
                logger.error("SLI calculation failed: %s", error_msg)
                errors.append(error_msg)
                pillar_slis[sli.pillar].append({
                    "name": sli.name,
                    "success_count": None,
                    "total_count": None,
                    "availability_pct": None,
                    "error": error_msg,
                })
            else:
                success, total, pct = result
                pillar_slis[sli.pillar].append({
                    "name": sli.name,
                    "success_count": round(success, 2),
                    "total_count": round(total, 2),
                    "availability_pct": round(pct, 6),
                    "error": None,
                })

        # Compute per-pillar availability (weighted average of SLIs)
        pillar_breakdown: list[dict[str, Any]] = []
        overall_success: float = 0.0
        overall_total: float = 0.0

        for pillar in ["grafana", "mimir", "loki", "tempo", "pyroscope"]:
            sli_list = pillar_slis.get(pillar, [])
            pillar_success: float = 0.0
            pillar_total: float = 0.0

            for sli_result in sli_list:
                s = sli_result.get("success_count")
                t = sli_result.get("total_count")
                if s is not None and t is not None:
                    pillar_success += s
                    pillar_total += t

            pillar_pct = self._safe_divide(pillar_success, pillar_total) * 100.0

            pillar_breakdown.append({
                "pillar": pillar,
                "uptime_pct": round(pillar_pct, 6),
                "total_success": round(pillar_success, 2),
                "total_requests": round(pillar_total, 2),
                "slis": sli_list,
            })

            overall_success += pillar_success
            overall_total += pillar_total

        overall_availability = self._safe_divide(overall_success, overall_total) * 100.0

        return self._build_result(
            value=overall_availability,
            details={
                "pillar_breakdown": pillar_breakdown,
                "overall_success_count": round(overall_success, 2),
                "overall_total_count": round(overall_total, 2),
                "environment": environment,
                "chunked": self._chunker.needs_chunking(start, end),
                "sli_count": len(_SLIS),
            },
            error="; ".join(errors) if errors else None,
        )

    # ------------------------------------------------------------------
    # Internal SLI calculation
    # ------------------------------------------------------------------

    async def _calculate_sli(
        self,
        prom: PrometheusQueryExecutor,
        sli: _SLI,
        start: datetime,
        end: datetime,
    ) -> tuple[float, float, float]:
        """Calculate a single SLI across chunked time windows.

        Returns ``(success_count, total_count, availability_pct)``.
        Numerator and denominator are summed across chunks before dividing.
        """
        chunks = self._chunker.chunk(start, end)

        success_values: list[float] = []
        total_values: list[float] = []

        for chunk in chunks:
            duration_seconds = int((chunk.end - chunk.start).total_seconds())
            range_str = f"{duration_seconds}s"

            success_query = sli.success_query.replace("{range}", range_str)
            total_query = sli.total_query.replace("{range}", range_str)

            success_val, total_val = await asyncio.gather(
                prom.get_metric_value(
                    success_query, chunk.start, chunk.end, default=0.0
                ),
                prom.get_metric_value(
                    total_query, chunk.start, chunk.end, default=0.0
                ),
            )

            success_values.append(success_val or 0.0)
            total_values.append(total_val or 0.0)

        total_success = sum(success_values)
        total_count = sum(total_values)
        availability_pct = self._safe_divide(total_success, total_count) * 100.0

        logger.info(
            "SLI %s/%s: %.4f%% (success=%.0f, total=%.0f, chunks=%d)",
            sli.pillar,
            sli.name,
            availability_pct,
            total_success,
            total_count,
            len(chunks),
        )

        return total_success, total_count, availability_pct
