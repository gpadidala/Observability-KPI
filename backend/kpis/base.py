"""Abstract base class for all KPI calculators.

Every KPI calculator in the Observability KPI Reporting Application inherits
from :class:`BaseKPICalculator`.  This guarantees a uniform interface for the
orchestrator (:mod:`kpis.calculator`) and simplifies testing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class BaseKPICalculator(ABC):
    """Base class for all KPI calculators.

    Subclasses must implement :pyattr:`kpi_name`, :pyattr:`unit`, and the
    :pymeth:`calculate` coroutine.  The orchestrator calls ``calculate`` with a
    :class:`~clients.prometheus_client.PrometheusQueryExecutor`, a time range,
    and an environment label, expecting a standardised result ``dict``.
    """

    @property
    @abstractmethod
    def kpi_name(self) -> str:
        """Human-readable name of this KPI (e.g. ``'Data Loss Rate'``)."""
        ...

    @property
    @abstractmethod
    def unit(self) -> str:
        """Unit of the primary KPI value (e.g. ``'%'``, ``'$/GB'``, ``'cores'``)."""
        ...

    @abstractmethod
    async def calculate(
        self,
        prometheus_client: Any,
        start: datetime,
        end: datetime,
        environment: str,
    ) -> dict[str, Any]:
        """Calculate the KPI over the given time range.

        Parameters
        ----------
        prometheus_client
            A :class:`~clients.prometheus_client.PrometheusQueryExecutor`
            instance configured for the target datasource.
        start : datetime
            Inclusive start of the reporting period.
        end : datetime
            Exclusive end of the reporting period.
        environment : str
            Environment label (e.g. ``"PROD"``, ``"PERF"``).

        Returns
        -------
        dict[str, Any]
            A dictionary containing at minimum:

            - ``value`` (``float``): The primary KPI value.
            - ``unit`` (``str``): Unit of measurement.
            - ``details`` (``dict``): Arbitrary detail payload such as
              per-pillar breakdown, thresholds, or trend data.
            - ``error`` (``str | None``): Error message if calculation
              partially failed; ``None`` on full success.
        """
        ...

    # ------------------------------------------------------------------
    # Shared helpers available to all subclasses
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_divide(numerator: float, denominator: float, *, default: float = 0.0) -> float:
        """Divide *numerator* by *denominator*, returning *default* on zero denominator."""
        if denominator == 0.0:
            return default
        return numerator / denominator

    def _build_result(
        self,
        value: float,
        details: dict[str, Any] | None = None,
        *,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Construct a standardised result dictionary."""
        return {
            "kpi_name": self.kpi_name,
            "value": round(value, 6),
            "unit": self.unit,
            "details": details or {},
            "error": error,
        }
