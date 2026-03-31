"""KPI Calculator: Monthly Infrastructure Cost Split by Pillar.

Breaks down the total monthly infrastructure cost across observability
pillars and computes each pillar's percentage share:

    Pillar % = (Pillar Cost / Total Cost) x 100

Cost data is sourced from the Flexera Cost API (currently mocked) and can
be augmented with AKS resource cost estimates derived from namespace-level
resource consumption in Prometheus.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from clients.prometheus_client import PrometheusQueryExecutor
from kpis.base import BaseKPICalculator
from time_window.chunker import TimeWindowChunker

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pillar-to-category mapping
# ---------------------------------------------------------------------------

_PILLAR_CATEGORIES: list[dict[str, str]] = [
    {"pillar": "mimir", "label": "Metrics (Mimir)", "cost_key": "metrics"},
    {"pillar": "loki", "label": "Logs (Loki)", "cost_key": "logs"},
    {"pillar": "tempo", "label": "Traces (Tempo)", "cost_key": "traces"},
    {"pillar": "pyroscope", "label": "Profiles (Pyroscope)", "cost_key": "profiles"},
    {"pillar": "grafana", "label": "Grafana UI", "cost_key": "grafana_ui"},
]

# AKS resource cost query templates (namespace-based resource consumption)
_AKS_CPU_COST_QUERY: str = (
    'sum(avg_over_time(namespace:container_cpu_usage_seconds_total:sum_rate'
    '{{namespace=~".*{pillar}.*"}}[{range}]))'
)

_AKS_MEMORY_COST_QUERY: str = (
    'sum(avg_over_time(namespace:container_memory_working_set_bytes:sum'
    '{{namespace=~".*{pillar}.*"}}[{range}]))'
)

# Estimated cost rates for AKS resource-based costing
_CPU_COST_PER_CORE_HOUR: float = 0.048   # USD per core per hour (Azure D-series)
_MEMORY_COST_PER_GB_HOUR: float = 0.012  # USD per GB per hour


class InfraCostSplitCalculator(BaseKPICalculator):
    """Calculate the Infrastructure Cost Split KPI.

    Returns a breakdown of monthly infrastructure costs by observability
    pillar with both absolute USD values and percentage shares.

    Two cost estimation strategies are available:

    1. **Flexera** (default): Uses mock Flexera cost data for each category.
    2. **AKS resource-based**: Queries Prometheus for namespace-level CPU
       and memory consumption, then applies per-unit cost rates.

    The calculator can blend both sources or fall back gracefully if one
    is unavailable.
    """

    def __init__(
        self,
        chunker: TimeWindowChunker | None = None,
        *,
        use_aks_resource_costs: bool = False,
    ) -> None:
        self._chunker = chunker or TimeWindowChunker()
        self._use_aks_resource_costs = use_aks_resource_costs

    # ------------------------------------------------------------------
    # BaseKPICalculator interface
    # ------------------------------------------------------------------

    @property
    def kpi_name(self) -> str:
        return "Infrastructure Cost Split"

    @property
    def unit(self) -> str:
        return "USD"

    async def calculate(
        self,
        prometheus_client: PrometheusQueryExecutor,
        start: datetime,
        end: datetime,
        environment: str,
    ) -> dict[str, Any]:
        """Calculate the infrastructure cost split.

        Returns a result dict with:
        - ``value``: Total monthly infrastructure cost in USD.
        - ``details.pillar_breakdown``: Per-pillar cost, percentage, and trend.
        """
        errors: list[str] = []

        # ---- Flexera cost data ----
        flexera_costs = await self._get_flexera_cost(environment, start, end)

        # ---- Optional AKS resource cost augmentation ----
        aks_costs: dict[str, float] | None = None
        if self._use_aks_resource_costs:
            try:
                aks_costs = await self._estimate_aks_costs(
                    prometheus_client, start, end
                )
            except Exception as exc:
                error_msg = f"AKS cost estimation failed: {exc}"
                logger.error(error_msg)
                errors.append(error_msg)

        # ---- Build pillar breakdown ----
        pillar_breakdown: list[dict[str, Any]] = []
        total_cost: float = 0.0

        for cat in _PILLAR_CATEGORIES:
            pillar = cat["pillar"]
            label = cat["label"]
            cost_key = cat["cost_key"]

            flexera_cost = flexera_costs.get(cost_key, 0.0)
            aks_cost = aks_costs.get(pillar, 0.0) if aks_costs else None

            # Primary cost source is Flexera; AKS is supplementary
            effective_cost = flexera_cost

            pillar_breakdown.append({
                "pillar": pillar,
                "label": label,
                "cost_usd": round(effective_cost, 2),
                "flexera_cost_usd": round(flexera_cost, 2),
                "aks_estimated_cost_usd": round(aks_cost, 2) if aks_cost is not None else None,
                "percentage": 0.0,  # will be computed after totalling
            })
            total_cost += effective_cost

        # ---- Compute percentages ----
        for entry in pillar_breakdown:
            if total_cost > 0:
                entry["percentage"] = round(
                    (entry["cost_usd"] / total_cost) * 100.0, 2
                )

        # ---- Trend data (month-over-month mock) ----
        trend = self._compute_trend(flexera_costs, environment)

        return self._build_result(
            value=total_cost,
            details={
                "pillar_breakdown": pillar_breakdown,
                "total_cost_usd": round(total_cost, 2),
                "environment": environment,
                "cost_source": "flexera_mock",
                "aks_cost_available": aks_costs is not None,
                "trend": trend,
                "period": {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "days": round((end - start).total_seconds() / 86_400, 1),
                },
            },
            error="; ".join(errors) if errors else None,
        )

    # ------------------------------------------------------------------
    # Flexera cost data (mock)
    # ------------------------------------------------------------------

    @staticmethod
    async def _get_flexera_cost(
        environment: str,
        start: datetime,
        end: datetime,
    ) -> dict[str, float]:
        """Retrieve infrastructure cost data from the Flexera Cost API (mock).

        Returns monthly costs scaled to the reporting period.
        """
        base_costs: dict[str, float] = {
            "metrics": 15_000.0,
            "logs": 8_000.0,
            "traces": 5_000.0,
            "profiles": 2_000.0,
            "grafana_ui": 3_000.0,
        }

        env_multiplier: float = 1.0 if environment.upper() == "PROD" else 0.4
        period_days = (end - start).total_seconds() / 86_400.0
        period_multiplier = period_days / 30.0

        return {
            category: cost * env_multiplier * period_multiplier
            for category, cost in base_costs.items()
        }

    # ------------------------------------------------------------------
    # AKS resource-based cost estimation
    # ------------------------------------------------------------------

    async def _estimate_aks_costs(
        self,
        prom: PrometheusQueryExecutor,
        start: datetime,
        end: datetime,
    ) -> dict[str, float]:
        """Estimate per-pillar costs from AKS namespace resource consumption.

        Queries average CPU and memory usage per namespace and applies
        per-unit hourly cost rates.
        """
        period_hours = (end - start).total_seconds() / 3600.0
        chunks = self._chunker.chunk(start, end)
        pillar_costs: dict[str, float] = {}

        pillars = ["mimir", "loki", "tempo", "pyroscope", "grafana"]

        tasks = [
            self._query_pillar_aks_cost(prom, pillar, chunks)
            for pillar in pillars
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for pillar, result in zip(pillars, results):
            if isinstance(result, Exception):
                logger.warning(
                    "AKS cost estimation failed for %s: %s", pillar, result
                )
                pillar_costs[pillar] = 0.0
                continue

            avg_cpu_cores, avg_memory_bytes = result

            cpu_cost = avg_cpu_cores * _CPU_COST_PER_CORE_HOUR * period_hours
            memory_gb = avg_memory_bytes / 1e9
            memory_cost = memory_gb * _MEMORY_COST_PER_GB_HOUR * period_hours

            pillar_costs[pillar] = cpu_cost + memory_cost
            logger.info(
                "AKS cost for %s: $%.2f (CPU=$%.2f, Mem=$%.2f)",
                pillar,
                cpu_cost + memory_cost,
                cpu_cost,
                memory_cost,
            )

        return pillar_costs

    async def _query_pillar_aks_cost(
        self,
        prom: PrometheusQueryExecutor,
        pillar: str,
        chunks: list[Any],
    ) -> tuple[float, float]:
        """Query average CPU and memory for a pillar, returning (cpu_cores, mem_bytes)."""
        cpu_values: list[float] = []
        mem_values: list[float] = []

        for chunk in chunks:
            duration_seconds = int((chunk.end - chunk.start).total_seconds())
            range_str = f"{duration_seconds}s"

            cpu_query = _AKS_CPU_COST_QUERY.replace("{pillar}", pillar).replace(
                "{range}", range_str
            )
            mem_query = _AKS_MEMORY_COST_QUERY.replace("{pillar}", pillar).replace(
                "{range}", range_str
            )

            cpu_val, mem_val = await asyncio.gather(
                prom.get_metric_value(cpu_query, chunk.start, chunk.end, default=0.0),
                prom.get_metric_value(mem_query, chunk.start, chunk.end, default=0.0),
            )
            cpu_values.append(cpu_val or 0.0)
            mem_values.append(mem_val or 0.0)

        # Average across chunks (gauge-type metrics)
        avg_cpu = sum(cpu_values) / len(cpu_values) if cpu_values else 0.0
        avg_mem = sum(mem_values) / len(mem_values) if mem_values else 0.0
        return avg_cpu, avg_mem

    # ------------------------------------------------------------------
    # Trend computation (mock)
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_trend(
        current_costs: dict[str, float],
        environment: str,
    ) -> dict[str, Any]:
        """Compute month-over-month cost trend data (mock).

        Returns simulated trend showing a 5-8% monthly increase for PROD
        and 2-4% for PERF.
        """
        import random

        random.seed(42)  # deterministic for consistent reports

        if environment.upper() == "PROD":
            growth_range = (0.05, 0.08)
        else:
            growth_range = (0.02, 0.04)

        previous_month: dict[str, float] = {}
        for category, cost in current_costs.items():
            growth = random.uniform(*growth_range)
            previous_cost = cost / (1.0 + growth)
            previous_month[category] = round(previous_cost, 2)

        current_total = sum(current_costs.values())
        previous_total = sum(previous_month.values())
        mom_change_pct = (
            ((current_total - previous_total) / previous_total * 100.0)
            if previous_total > 0
            else 0.0
        )

        return {
            "previous_month_costs": previous_month,
            "previous_month_total_usd": round(previous_total, 2),
            "month_over_month_change_pct": round(mom_change_pct, 2),
            "trend_direction": "up" if mom_change_pct > 0 else "down",
        }
