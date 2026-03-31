"""KPI Calculator: Cost per GB Ingested.

Computes the effective cost of ingesting one gigabyte of observability data,
broken down by pillar:

    Cost per GB = Total Monthly Infrastructure Cost / Total GB Ingested

Ingestion volume is derived from Prometheus counters.  Infrastructure cost
is currently sourced from a mock Flexera API (see :meth:`_get_flexera_cost`);
this will be replaced with a live integration once Flexera API access is
provisioned.
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

_BYTES_PER_GB: float = 1_000_000_000.0  # 1e9
_BYTES_PER_SAMPLE: float = 2.0  # conservative estimate for Mimir/Cortex samples


# ---------------------------------------------------------------------------
# Per-pillar ingestion queries
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class _PillarIngestion:
    """Describes how to compute ingested GB for a single pillar."""

    pillar: str
    query_template: str
    conversion: str  # "bytes" or "samples"


_PILLAR_INGESTION: list[_PillarIngestion] = [
    _PillarIngestion(
        pillar="loki",
        query_template="sum(increase(loki_distributor_bytes_received_total[{range}]))",
        conversion="bytes",
    ),
    _PillarIngestion(
        pillar="mimir",
        query_template="sum(increase(cortex_ingester_ingested_samples_total[{range}]))",
        conversion="samples",
    ),
    _PillarIngestion(
        pillar="tempo",
        query_template="sum(increase(tempo_distributor_bytes_received_total[{range}]))",
        conversion="bytes",
    ),
    _PillarIngestion(
        pillar="pyroscope",
        query_template="sum(increase(pyroscope_distributor_bytes_received_total[{range}]))",
        conversion="bytes",
    ),
]

# Mapping from pillar name to the Flexera cost category key
_PILLAR_COST_KEY: dict[str, str] = {
    "mimir": "metrics",
    "loki": "logs",
    "tempo": "traces",
    "pyroscope": "profiles",
}


class CostPerGBCalculator(BaseKPICalculator):
    """Calculate the Cost-per-GB KPI for each observability pillar.

    Ingestion volume is queried from Prometheus (via
    :class:`~clients.prometheus_client.PrometheusQueryExecutor`) and costs
    are retrieved from the Flexera cost API (currently mocked).

    For time ranges exceeding 30 days, ingestion bytes/samples are summed
    across :class:`TimeWindowChunker` windows before computing the final
    cost ratio.
    """

    def __init__(self, chunker: TimeWindowChunker | None = None) -> None:
        self._chunker = chunker or TimeWindowChunker()

    # ------------------------------------------------------------------
    # BaseKPICalculator interface
    # ------------------------------------------------------------------

    @property
    def kpi_name(self) -> str:
        return "Cost per GB Ingested"

    @property
    def unit(self) -> str:
        return "$/GB"

    async def calculate(
        self,
        prometheus_client: PrometheusQueryExecutor,
        start: datetime,
        end: datetime,
        environment: str,
    ) -> dict[str, Any]:
        """Calculate cost-per-GB for each pillar and overall.

        Returns a result dict with:
        - ``value``: Overall blended cost per GB across all pillars.
        - ``details.pillar_breakdown``: Per-pillar cost, GB, and cost/GB.
        """
        # Fetch cost data (async-ready for future live integration)
        cost_data = await self._get_flexera_cost(environment, start, end)

        # Query ingestion volumes in parallel
        tasks = [
            self._query_pillar_gb(prometheus_client, pi, start, end)
            for pi in _PILLAR_INGESTION
        ]
        gb_results = await asyncio.gather(*tasks, return_exceptions=True)

        pillar_breakdown: list[dict[str, Any]] = []
        total_cost: float = 0.0
        total_gb: float = 0.0
        errors: list[str] = []

        for pi, gb_result in zip(_PILLAR_INGESTION, gb_results):
            cost_key = _PILLAR_COST_KEY[pi.pillar]
            pillar_cost = cost_data.get(cost_key, 0.0)

            if isinstance(gb_result, Exception):
                error_msg = f"{pi.pillar}: {gb_result}"
                logger.error("Ingestion query failed for %s: %s", pi.pillar, gb_result)
                errors.append(error_msg)
                pillar_breakdown.append({
                    "pillar": pi.pillar,
                    "cost_usd": round(pillar_cost, 2),
                    "ingested_gb": None,
                    "cost_per_gb": None,
                    "error": error_msg,
                })
                total_cost += pillar_cost
                continue

            ingested_gb = gb_result
            cost_per_gb = self._safe_divide(pillar_cost, ingested_gb)

            pillar_breakdown.append({
                "pillar": pi.pillar,
                "cost_usd": round(pillar_cost, 2),
                "ingested_gb": round(ingested_gb, 4),
                "cost_per_gb": round(cost_per_gb, 4),
                "error": None,
            })
            total_cost += pillar_cost
            total_gb += ingested_gb

        # Include Grafana UI cost (no ingestion volume associated)
        grafana_cost = cost_data.get("grafana_ui", 0.0)
        total_cost += grafana_cost

        overall_cost_per_gb = self._safe_divide(total_cost, total_gb)

        return self._build_result(
            value=overall_cost_per_gb,
            details={
                "pillar_breakdown": pillar_breakdown,
                "grafana_ui_cost_usd": round(grafana_cost, 2),
                "total_cost_usd": round(total_cost, 2),
                "total_ingested_gb": round(total_gb, 4),
                "environment": environment,
                "cost_source": "flexera_mock",
                "chunked": self._chunker.needs_chunking(start, end),
            },
            error="; ".join(errors) if errors else None,
        )

    # ------------------------------------------------------------------
    # Ingestion volume queries
    # ------------------------------------------------------------------

    async def _query_pillar_gb(
        self,
        prom: PrometheusQueryExecutor,
        pi: _PillarIngestion,
        start: datetime,
        end: datetime,
    ) -> float:
        """Query and sum ingestion volume for a pillar, returning GB."""
        chunks = self._chunker.chunk(start, end)
        raw_values: list[float] = []

        for chunk in chunks:
            duration_seconds = int((chunk.end - chunk.start).total_seconds())
            range_str = f"{duration_seconds}s"
            query = pi.query_template.replace("{range}", range_str)

            value = await prom.get_metric_value(query, chunk.start, chunk.end, default=0.0)
            raw_values.append(value or 0.0)

        total_raw = sum(raw_values)

        # Convert to GB
        if pi.conversion == "bytes":
            gb = total_raw / _BYTES_PER_GB
        elif pi.conversion == "samples":
            # Mimir: estimate bytes from sample count
            gb = (total_raw * _BYTES_PER_SAMPLE) / _BYTES_PER_GB
        else:
            gb = total_raw / _BYTES_PER_GB

        logger.info(
            "Ingestion for %s: %.4f GB (raw=%.0f, conversion=%s, chunks=%d)",
            pi.pillar,
            gb,
            total_raw,
            pi.conversion,
            len(chunks),
        )
        return gb

    # ------------------------------------------------------------------
    # Flexera cost data (mock)
    # ------------------------------------------------------------------

    @staticmethod
    async def _get_flexera_cost(
        environment: str,
        start: datetime,
        end: datetime,
    ) -> dict[str, float]:
        """Retrieve infrastructure cost data from the Flexera Cost API.

        .. note::
           This is currently a **mock implementation** returning realistic
           cost figures.  The real Flexera integration will replace this
           method once API credentials are provisioned.

        The costs are scaled proportionally if the requested period is not
        exactly one month (30 days).

        Parameters
        ----------
        environment : str
            Target environment (``"PROD"`` costs are higher than ``"PERF"``).
        start : datetime
            Cost period start.
        end : datetime
            Cost period end.

        Returns
        -------
        dict[str, float]
            Monthly cost in USD keyed by category:
            ``metrics``, ``logs``, ``traces``, ``profiles``, ``grafana_ui``.
        """
        # Base monthly costs for PROD
        base_costs: dict[str, float] = {
            "metrics": 15_000.0,   # Mimir / metrics pipeline
            "logs": 8_000.0,       # Loki / logs pipeline
            "traces": 5_000.0,     # Tempo / traces pipeline
            "profiles": 2_000.0,   # Pyroscope / profiles pipeline
            "grafana_ui": 3_000.0, # Grafana UI and dashboarding
        }

        # PERF environment typically costs ~40% of PROD
        env_multiplier: float = 1.0 if environment.upper() == "PROD" else 0.4

        # Scale costs proportionally to the reporting period
        period_days = (end - start).total_seconds() / 86_400.0
        period_multiplier = period_days / 30.0

        scaled_costs: dict[str, float] = {
            category: cost * env_multiplier * period_multiplier
            for category, cost in base_costs.items()
        }

        logger.info(
            "Flexera cost data (mock) for %s over %.1f days: total=$%.2f",
            environment,
            period_days,
            sum(scaled_costs.values()),
        )
        return scaled_costs
