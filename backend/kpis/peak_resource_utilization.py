"""KPI Calculator: Peak Resource Utilization.

Computes monthly peak and P95 resource utilisation for the observability
platform across CPU, memory, and disk dimensions.

Metrics are queried per namespace selector (Mimir, Loki, Tempo, Pyroscope,
Grafana) and aggregated across 30-day query chunks where necessary.
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
# Namespace selector used for container-level metrics
# ---------------------------------------------------------------------------

_NAMESPACE_SELECTOR: str = (
    'namespace=~".*mimir.*|.*loki.*|.*tempo.*|.*pyroscope.*|.*grafana.*"'
)


# ---------------------------------------------------------------------------
# Resource metric definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class _ResourceMetric:
    """A single resource metric to query."""

    name: str
    query_template: str
    aggregation: str  # "max" or "p95"
    unit: str


def _build_cpu_max() -> _ResourceMetric:
    return _ResourceMetric(
        name="cpu_max_cores",
        query_template=(
            "max_over_time("
            "sum(rate(container_cpu_usage_seconds_total"
            "{{{ns}}}[5m]))[{range}:1h])"
        ),
        aggregation="max",
        unit="cores",
    )


def _build_cpu_p95() -> _ResourceMetric:
    return _ResourceMetric(
        name="cpu_p95_cores",
        query_template=(
            "quantile_over_time(0.95, "
            "sum(rate(container_cpu_usage_seconds_total"
            "{{{ns}}}[5m]))[{range}:1h])"
        ),
        aggregation="p95",
        unit="cores",
    )


def _build_memory_max() -> _ResourceMetric:
    return _ResourceMetric(
        name="memory_max_bytes",
        query_template=(
            "max_over_time("
            "sum(container_memory_working_set_bytes"
            "{{{ns}}})[{range}:1h])"
        ),
        aggregation="max",
        unit="bytes",
    )


def _build_memory_p95() -> _ResourceMetric:
    return _ResourceMetric(
        name="memory_p95_bytes",
        query_template=(
            "quantile_over_time(0.95, "
            "sum(container_memory_working_set_bytes"
            "{{{ns}}})[{range}:1h])"
        ),
        aggregation="p95",
        unit="bytes",
    )


def _build_disk_metric(pillar: str) -> _ResourceMetric:
    return _ResourceMetric(
        name=f"disk_max_bytes_{pillar}",
        query_template=(
            "max_over_time("
            'sum(kubelet_volume_stats_used_bytes{{namespace=~".*{pillar}.*"}})'
            "[{range}:1h])"
        ),
        aggregation="max",
        unit="bytes",
    )


# Pre-built metric list
_RESOURCE_METRICS: list[_ResourceMetric] = [
    _build_cpu_max(),
    _build_cpu_p95(),
    _build_memory_max(),
    _build_memory_p95(),
]

_DISK_PILLARS: list[str] = ["loki", "mimir", "tempo", "pyroscope"]


class PeakResourceUtilizationCalculator(BaseKPICalculator):
    """Calculate the Peak Resource Utilization KPI.

    Queries container-level CPU, memory, and disk metrics across all
    observability namespaces.  Uses 30-day chunked queries and aggregates
    with ``max`` for peak values and ``max`` of per-chunk P95 as a
    conservative P95 estimate.

    Returns a structured breakdown with CPU (max, P95), memory (max, P95),
    and per-pillar disk usage.
    """

    def __init__(self, chunker: TimeWindowChunker | None = None) -> None:
        self._chunker = chunker or TimeWindowChunker()

    # ------------------------------------------------------------------
    # BaseKPICalculator interface
    # ------------------------------------------------------------------

    @property
    def kpi_name(self) -> str:
        return "Peak Resource Utilization"

    @property
    def unit(self) -> str:
        return "mixed"

    async def calculate(
        self,
        prometheus_client: PrometheusQueryExecutor,
        start: datetime,
        end: datetime,
        environment: str,
    ) -> dict[str, Any]:
        """Calculate peak resource utilisation.

        Returns a result dict with:
        - ``value``: Peak CPU utilisation in cores (headline metric).
        - ``details``: Full breakdown of CPU, memory, and disk.
        """
        errors: list[str] = []

        # ------ CPU and Memory metrics (shared namespace selector) ------
        compute_tasks = [
            self._query_resource_metric(prometheus_client, rm, start, end)
            for rm in _RESOURCE_METRICS
        ]
        # ------ Disk metrics per pillar ------
        disk_metrics = [_build_disk_metric(p) for p in _DISK_PILLARS]
        disk_tasks = [
            self._query_resource_metric(prometheus_client, dm, start, end)
            for dm in disk_metrics
        ]

        all_results = await asyncio.gather(
            *(compute_tasks + disk_tasks), return_exceptions=True
        )

        compute_results = all_results[: len(compute_tasks)]
        disk_results = all_results[len(compute_tasks) :]

        # ------ Parse compute results ------
        compute_breakdown: dict[str, Any] = {}
        for rm, result in zip(_RESOURCE_METRICS, compute_results):
            if isinstance(result, Exception):
                error_msg = f"{rm.name}: {result}"
                errors.append(error_msg)
                logger.error("Resource metric failed for %s: %s", rm.name, result)
                compute_breakdown[rm.name] = {"value": None, "unit": rm.unit, "error": error_msg}
            else:
                compute_breakdown[rm.name] = {
                    "value": round(result, 4) if result is not None else None,
                    "unit": rm.unit,
                    "error": None,
                }

        # ------ Parse disk results ------
        disk_breakdown: dict[str, Any] = {}
        for pillar, dm, result in zip(_DISK_PILLARS, disk_metrics, disk_results):
            if isinstance(result, Exception):
                error_msg = f"disk_{pillar}: {result}"
                errors.append(error_msg)
                logger.error("Disk metric failed for %s: %s", pillar, result)
                disk_breakdown[pillar] = {"value": None, "unit": "bytes", "error": error_msg}
            else:
                disk_breakdown[pillar] = {
                    "value": round(result, 2) if result is not None else None,
                    "unit": "bytes",
                    "value_gb": round(result / 1e9, 4) if result is not None else None,
                    "error": None,
                }

        # Headline value: peak CPU cores (or 0 if unavailable)
        cpu_max_val = compute_breakdown.get("cpu_max_cores", {}).get("value")
        headline = cpu_max_val if cpu_max_val is not None else 0.0

        # Human-readable summary
        cpu_p95_val = compute_breakdown.get("cpu_p95_cores", {}).get("value")
        mem_max_val = compute_breakdown.get("memory_max_bytes", {}).get("value")
        mem_p95_val = compute_breakdown.get("memory_p95_bytes", {}).get("value")

        summary = {
            "cpu_max_cores": cpu_max_val,
            "cpu_p95_cores": cpu_p95_val,
            "memory_max_gb": round(mem_max_val / 1e9, 4) if mem_max_val else None,
            "memory_p95_gb": round(mem_p95_val / 1e9, 4) if mem_p95_val else None,
            "total_disk_gb": round(
                sum(
                    d["value"] / 1e9
                    for d in disk_breakdown.values()
                    if d.get("value") is not None
                ),
                4,
            ),
        }

        return self._build_result(
            value=headline,
            details={
                "summary": summary,
                "compute": compute_breakdown,
                "disk": disk_breakdown,
                "environment": environment,
                "namespace_selector": _NAMESPACE_SELECTOR,
                "chunked": self._chunker.needs_chunking(start, end),
            },
            error="; ".join(errors) if errors else None,
        )

    # ------------------------------------------------------------------
    # Internal query helper
    # ------------------------------------------------------------------

    async def _query_resource_metric(
        self,
        prom: PrometheusQueryExecutor,
        metric: _ResourceMetric,
        start: datetime,
        end: datetime,
    ) -> float | None:
        """Query a resource metric across chunked windows and aggregate.

        For ``max`` metrics: take the maximum across chunks.
        For ``p95`` metrics: take the maximum of per-chunk P95 values
        (conservative upper bound).
        """
        chunks = self._chunker.chunk(start, end)
        chunk_values: list[float] = []

        for chunk in chunks:
            duration_seconds = int((chunk.end - chunk.start).total_seconds())
            range_str = f"{duration_seconds}s"

            # Substitute placeholders
            query = metric.query_template.replace("{range}", range_str)
            query = query.replace("{ns}", _NAMESPACE_SELECTOR)
            # For disk metrics with per-pillar selector
            for pillar in _DISK_PILLARS:
                query = query.replace("{pillar}", pillar)

            value = await prom.get_metric_value(
                query, chunk.start, chunk.end, default=None
            )
            if value is not None:
                chunk_values.append(value)

        if not chunk_values:
            logger.warning("No data returned for resource metric: %s", metric.name)
            return None

        # Aggregate across chunks
        if metric.aggregation == "max":
            result = max(chunk_values)
        elif metric.aggregation == "p95":
            # Conservative: take max of per-chunk P95 values
            result = max(chunk_values)
        else:
            result = max(chunk_values)

        logger.info(
            "Resource metric %s: %.4f %s (chunks=%d, agg=%s)",
            metric.name,
            result,
            metric.unit,
            len(chunks),
            metric.aggregation,
        )
        return result
