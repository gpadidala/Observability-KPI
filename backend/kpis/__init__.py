"""KPI calculation engines for the Observability KPI Reporting Application.

This package contains:

- :mod:`kpis.base` -- Abstract base class for all KPI calculators.
- :mod:`kpis.data_loss_rate` -- Data Loss Rate KPI.
- :mod:`kpis.cost_per_gb` -- Cost per GB Ingested KPI.
- :mod:`kpis.peak_resource_utilization` -- Peak Resource Utilization KPI.
- :mod:`kpis.infra_cost_split` -- Infrastructure Cost Split KPI.
- :mod:`kpis.uptime` -- Uptime / Availability KPI.
- :mod:`kpis.calculator` -- Orchestrator that runs all calculators.
"""

from kpis.base import BaseKPICalculator
from kpis.calculator import KPIOrchestrator
from kpis.cost_per_gb import CostPerGBCalculator
from kpis.data_loss_rate import DataLossRateCalculator
from kpis.infra_cost_split import InfraCostSplitCalculator
from kpis.peak_resource_utilization import PeakResourceUtilizationCalculator
from kpis.uptime import UptimeCalculator

__all__ = [
    "BaseKPICalculator",
    "CostPerGBCalculator",
    "DataLossRateCalculator",
    "InfraCostSplitCalculator",
    "KPIOrchestrator",
    "PeakResourceUtilizationCalculator",
    "UptimeCalculator",
]
