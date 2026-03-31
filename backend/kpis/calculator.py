"""KPI Orchestrator: coordinates all KPI calculators and aggregates results.

The :class:`KPIOrchestrator` is the single entry point for the API layer.
It instantiates and runs every KPI calculator, collects the results into
:class:`~api.models.PillarKPIs` structures, and handles individual calculator
failures gracefully so that a single broken KPI never blocks the entire
report.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime
from typing import Any

from api.models import KPIResult, PillarKPIs, TimeWindow
from clients.prometheus_client import PrometheusQueryExecutor
from kpis.base import BaseKPICalculator
from kpis.cost_per_gb import CostPerGBCalculator
from kpis.data_loss_rate import DataLossRateCalculator
from kpis.infra_cost_split import InfraCostSplitCalculator
from kpis.peak_resource_utilization import PeakResourceUtilizationCalculator
from kpis.uptime import UptimeCalculator
from time_window.chunker import TimeWindowChunker

logger = logging.getLogger(__name__)

# Ordered list of pillars for consistent output
_PILLARS: list[str] = ["mimir", "loki", "tempo", "pyroscope", "grafana"]


class KPIOrchestrator:
    """Orchestrates all KPI calculations and aggregates results by pillar.

    Usage::

        async with GrafanaClient(url, token) as gc:
            prom = PrometheusQueryExecutor(gc, datasource_uid="abc123")
            orchestrator = KPIOrchestrator(prom)
            report = await orchestrator.calculate_all_kpis(start, end, "PROD")
    """

    def __init__(
        self,
        prometheus_client: PrometheusQueryExecutor,
        *,
        chunker: TimeWindowChunker | None = None,
    ) -> None:
        self._prom = prometheus_client
        self._chunker = chunker or TimeWindowChunker()

        # Instantiate all KPI calculators
        self._calculators: list[BaseKPICalculator] = [
            DataLossRateCalculator(chunker=self._chunker),
            CostPerGBCalculator(chunker=self._chunker),
            PeakResourceUtilizationCalculator(chunker=self._chunker),
            InfraCostSplitCalculator(chunker=self._chunker),
            UptimeCalculator(chunker=self._chunker),
        ]

    @property
    def calculator_names(self) -> list[str]:
        """Return the names of all registered KPI calculators."""
        return [c.kpi_name for c in self._calculators]

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def calculate_all_kpis(
        self,
        start: datetime,
        end: datetime,
        environment: str,
    ) -> list[PillarKPIs]:
        """Run all KPI calculators and aggregate results by pillar.

        Parameters
        ----------
        start : datetime
            Inclusive start of the reporting period.
        end : datetime
            Exclusive end of the reporting period.
        environment : str
            Target environment label (e.g. ``"PROD"``).

        Returns
        -------
        list[PillarKPIs]
            One :class:`PillarKPIs` per pillar, each containing all computed
            :class:`KPIResult` entries.  If a calculator fails, the error is
            captured inside the individual ``KPIResult.details`` and the
            remaining KPIs are still returned.
        """
        logger.info(
            "Starting KPI calculation: %s to %s, env=%s, calculators=%d",
            start.isoformat(),
            end.isoformat(),
            environment,
            len(self._calculators),
        )

        # Run all calculators concurrently
        tasks = [
            self._run_calculator(calc, start, end, environment)
            for calc in self._calculators
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=False)

        # raw_results is list[dict[str, Any]] -- one per calculator
        # Aggregate into per-pillar structure
        pillar_kpis = self._aggregate_results(raw_results, start, end, environment)

        logger.info(
            "KPI calculation complete: %d pillars, %d total KPIs",
            len(pillar_kpis),
            sum(len(p.kpis) for p in pillar_kpis),
        )
        return pillar_kpis

    async def calculate_pillar_kpis(
        self,
        pillar: str,
        start: datetime,
        end: datetime,
        environment: str,
    ) -> PillarKPIs:
        """Run all KPI calculators and return results for a single pillar.

        Parameters
        ----------
        pillar : str
            Target pillar name (e.g. ``"mimir"``, ``"loki"``).
        start : datetime
            Inclusive start of the reporting period.
        end : datetime
            Exclusive end of the reporting period.
        environment : str
            Target environment label.

        Returns
        -------
        PillarKPIs
            The KPI results for the requested pillar only.

        Raises
        ------
        ValueError
            If *pillar* is not a recognised pillar name.
        """
        pillar_lower = pillar.lower()
        if pillar_lower not in _PILLARS:
            raise ValueError(
                f"Unknown pillar '{pillar}'. "
                f"Valid pillars: {', '.join(_PILLARS)}"
            )

        all_results = await self.calculate_all_kpis(start, end, environment)

        for result in all_results:
            if result.pillar == pillar_lower:
                return result

        # Should not happen, but return an empty structure if it does
        return PillarKPIs(pillar=pillar_lower, kpis=[])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_calculator(
        self,
        calculator: BaseKPICalculator,
        start: datetime,
        end: datetime,
        environment: str,
    ) -> dict[str, Any]:
        """Run a single calculator with error isolation.

        Never raises; returns an error result dict on failure.
        """
        try:
            logger.debug("Running calculator: %s", calculator.kpi_name)
            result = await calculator.calculate(
                self._prom, start, end, environment
            )
            logger.debug(
                "Calculator %s completed: value=%s",
                calculator.kpi_name,
                result.get("value"),
            )
            return result

        except Exception as exc:
            error_msg = f"{calculator.kpi_name} failed: {exc}"
            logger.error(
                "KPI calculator failed: %s\n%s",
                error_msg,
                traceback.format_exc(),
            )
            return {
                "kpi_name": calculator.kpi_name,
                "value": 0.0,
                "unit": calculator.unit,
                "details": {
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "traceback": traceback.format_exc(),
                },
                "error": error_msg,
            }

    def _aggregate_results(
        self,
        raw_results: list[dict[str, Any]],
        start: datetime,
        end: datetime,
        environment: str,
    ) -> list[PillarKPIs]:
        """Aggregate raw calculator results into per-pillar PillarKPIs structures.

        Each calculator returns a cross-pillar result.  This method distributes
        the per-pillar breakdown data into the correct PillarKPIs bucket and
        creates one :class:`KPIResult` per KPI per pillar.
        """
        time_windows = [TimeWindow(start=start, end=end)]

        # Initialize empty pillar buckets
        pillar_map: dict[str, list[KPIResult]] = {p: [] for p in _PILLARS}

        for result in raw_results:
            kpi_name = result.get("kpi_name", "unknown")
            unit = result.get("unit", "")
            overall_value = result.get("value", 0.0)
            details = result.get("details", {})
            error = result.get("error")

            # Extract per-pillar breakdown if available
            pillar_breakdown = details.get("pillar_breakdown", [])

            if pillar_breakdown:
                # Distribute per-pillar results
                for pb in pillar_breakdown:
                    pillar = pb.get("pillar", "").lower()
                    if pillar not in pillar_map:
                        continue

                    # Determine the pillar-specific value
                    pillar_value = self._extract_pillar_value(pb, kpi_name)

                    pillar_map[pillar].append(
                        KPIResult(
                            kpi_name=kpi_name,
                            value=pillar_value,
                            unit=unit,
                            pillar=pillar,
                            environment=environment,
                            time_windows=time_windows,
                            details={
                                "pillar_detail": pb,
                                "overall_value": overall_value,
                                "error": pb.get("error") or error,
                            },
                        )
                    )
            else:
                # Cross-cutting KPI (e.g. Peak Resource Utilization):
                # assign to all pillars with the overall value
                for pillar in _PILLARS:
                    pillar_map[pillar].append(
                        KPIResult(
                            kpi_name=kpi_name,
                            value=overall_value,
                            unit=unit,
                            pillar=pillar,
                            environment=environment,
                            time_windows=time_windows,
                            details={
                                "full_details": details,
                                "error": error,
                            },
                        )
                    )

        return [
            PillarKPIs(pillar=pillar, kpis=kpis)
            for pillar, kpis in pillar_map.items()
        ]

    @staticmethod
    def _extract_pillar_value(
        pillar_breakdown: dict[str, Any], kpi_name: str
    ) -> float:
        """Extract the primary numeric value for a pillar from its breakdown dict.

        Different KPIs store their pillar value under different keys.
        This method normalises the lookup.
        """
        # Try common keys in order of specificity
        key_candidates = [
            "loss_rate_pct",       # Data Loss Rate
            "cost_per_gb",         # Cost per GB
            "cost_usd",            # Infra Cost Split
            "uptime_pct",          # Uptime
            "availability_pct",    # Alternative availability key
            "value",               # Generic fallback
        ]

        for key in key_candidates:
            val = pillar_breakdown.get(key)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue

        return 0.0
