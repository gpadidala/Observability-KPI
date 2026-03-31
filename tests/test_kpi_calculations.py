"""Tests for KPI calculation logic: DataLossRate, CostPerGB, Uptime.

Uses unittest.mock to mock the PrometheusQueryExecutor so that tests
exercise the calculation math without requiring a live Prometheus backend.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from kpis.data_loss_rate import DataLossRateCalculator
from kpis.cost_per_gb import CostPerGBCalculator
from kpis.uptime import UptimeCalculator
from time_window.chunker import TimeWindowChunker


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def short_start() -> datetime:
    """A start datetime within a single 30-day window."""
    return datetime(2025, 3, 1)


@pytest.fixture
def short_end(short_start: datetime) -> datetime:
    """An end datetime 7 days after short_start."""
    return short_start + timedelta(days=7)


@pytest.fixture
def chunker() -> TimeWindowChunker:
    return TimeWindowChunker()


def _make_prom_mock(**side_effects) -> AsyncMock:
    """Create a mock PrometheusQueryExecutor with configurable return values.

    By default, get_metric_value returns 0.0.
    Pass a list to ``get_metric_value`` to set sequential return values.
    """
    mock = AsyncMock()
    mock.get_metric_value = AsyncMock(
        **side_effects if side_effects else {"return_value": 0.0}
    )
    return mock


# ===========================================================================
# DataLossRateCalculator
# ===========================================================================

class TestDataLossRateCalculator:
    """Test the Data Loss Rate KPI calculation math."""

    @pytest.mark.asyncio
    async def test_basic_loss_rate(self, short_start, short_end, chunker):
        """10 dropped / 1000 total per pillar = 1.0% per pillar, 1.0% overall."""
        prom = AsyncMock()
        # For each pillar: first call = dropped (10), second call = total (1000)
        # 4 pillars x 1 chunk x 2 queries = 8 calls total
        prom.get_metric_value = AsyncMock(
            side_effect=[10, 1000] * 4
        )
        calc = DataLossRateCalculator(chunker=chunker)
        result = await calc.calculate(prom, short_start, short_end, "PROD")

        # Overall: total_dropped=40, total_events=4000 => 1.0%
        assert result["value"] == pytest.approx(1.0, abs=0.01)
        assert result["unit"] == "%"
        assert result["kpi_name"] == "Data Loss Rate"

    @pytest.mark.asyncio
    async def test_zero_drops(self, short_start, short_end, chunker):
        """0 dropped / 1000 total = 0.0% loss rate."""
        prom = AsyncMock()
        prom.get_metric_value = AsyncMock(
            side_effect=[0, 1000] * 4
        )
        calc = DataLossRateCalculator(chunker=chunker)
        result = await calc.calculate(prom, short_start, short_end, "PROD")

        assert result["value"] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_zero_total_no_error(self, short_start, short_end, chunker):
        """0 dropped / 0 total should return 0.0%, not raise an error.

        The _safe_divide helper returns 0.0 when the denominator is zero.
        """
        prom = AsyncMock()
        prom.get_metric_value = AsyncMock(return_value=0.0)
        calc = DataLossRateCalculator(chunker=chunker)
        result = await calc.calculate(prom, short_start, short_end, "PROD")

        assert result["value"] == pytest.approx(0.0)
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_high_loss_rate(self, short_start, short_end, chunker):
        """500 dropped / 1000 total = 50.0% loss rate."""
        prom = AsyncMock()
        prom.get_metric_value = AsyncMock(
            side_effect=[500, 1000] * 4
        )
        calc = DataLossRateCalculator(chunker=chunker)
        result = await calc.calculate(prom, short_start, short_end, "PROD")

        assert result["value"] == pytest.approx(50.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_pillar_breakdown_present(self, short_start, short_end, chunker):
        """Result should contain per-pillar breakdown."""
        prom = AsyncMock()
        prom.get_metric_value = AsyncMock(
            side_effect=[5, 100] * 4
        )
        calc = DataLossRateCalculator(chunker=chunker)
        result = await calc.calculate(prom, short_start, short_end, "PROD")

        breakdown = result["details"]["pillar_breakdown"]
        assert len(breakdown) == 4
        pillar_names = {p["pillar"] for p in breakdown}
        assert pillar_names == {"mimir", "loki", "tempo", "pyroscope"}

    @pytest.mark.asyncio
    async def test_kpi_name_and_unit(self, chunker):
        calc = DataLossRateCalculator(chunker=chunker)
        assert calc.kpi_name == "Data Loss Rate"
        assert calc.unit == "%"


# ===========================================================================
# CostPerGBCalculator
# ===========================================================================

class TestCostPerGBCalculator:
    """Test the Cost-per-GB KPI calculation math."""

    @pytest.mark.asyncio
    async def test_basic_cost_per_gb(self, short_start, short_end, chunker):
        """With known mock costs and ingestion volumes, verify the math.

        The mock Flexera costs for PROD over 7 days are scaled by 7/30.
        We set ingestion volumes and verify cost_per_gb = total_cost / total_gb.
        """
        prom = AsyncMock()
        # 4 pillars, each returns a large byte/sample count
        # loki (bytes): 1e12 => 1000 GB
        # mimir (samples): 5e11 => (5e11 * 2) / 1e9 = 1000 GB
        # tempo (bytes): 1e12 => 1000 GB
        # pyroscope (bytes): 1e12 => 1000 GB
        prom.get_metric_value = AsyncMock(
            side_effect=[1e12, 5e11, 1e12, 1e12]
        )
        calc = CostPerGBCalculator(chunker=chunker)
        result = await calc.calculate(prom, short_start, short_end, "PROD")

        assert result["kpi_name"] == "Cost per GB Ingested"
        assert result["unit"] == "$/GB"
        assert result["value"] > 0
        assert "pillar_breakdown" in result["details"]

    @pytest.mark.asyncio
    async def test_zero_ingestion_handled(self, short_start, short_end, chunker):
        """When all ingestion volumes are 0, cost_per_gb should be 0 (safe divide)."""
        prom = AsyncMock()
        prom.get_metric_value = AsyncMock(return_value=0.0)
        calc = CostPerGBCalculator(chunker=chunker)
        result = await calc.calculate(prom, short_start, short_end, "PROD")

        # safe_divide returns 0.0 when denominator is zero
        assert result["value"] == pytest.approx(0.0)
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_multiple_pillars_in_breakdown(self, short_start, short_end, chunker):
        """Result should contain per-pillar cost breakdown with 4 entries."""
        prom = AsyncMock()
        prom.get_metric_value = AsyncMock(return_value=1e9)  # 1 GB for each
        calc = CostPerGBCalculator(chunker=chunker)
        result = await calc.calculate(prom, short_start, short_end, "PROD")

        breakdown = result["details"]["pillar_breakdown"]
        assert len(breakdown) == 4
        pillar_names = {p["pillar"] for p in breakdown}
        assert pillar_names == {"loki", "mimir", "tempo", "pyroscope"}

    @pytest.mark.asyncio
    async def test_cost_source_is_flexera_mock(self, short_start, short_end, chunker):
        prom = AsyncMock()
        prom.get_metric_value = AsyncMock(return_value=1e9)
        calc = CostPerGBCalculator(chunker=chunker)
        result = await calc.calculate(prom, short_start, short_end, "PROD")

        assert result["details"]["cost_source"] == "flexera_mock"

    @pytest.mark.asyncio
    async def test_kpi_name_and_unit(self, chunker):
        calc = CostPerGBCalculator(chunker=chunker)
        assert calc.kpi_name == "Cost per GB Ingested"
        assert calc.unit == "$/GB"


# ===========================================================================
# UptimeCalculator
# ===========================================================================

class TestUptimeCalculator:
    """Test the Uptime / Availability KPI calculation math."""

    @pytest.mark.asyncio
    async def test_perfect_uptime(self, short_start, short_end, chunker):
        """1000 success / 1000 total for every SLI = 100% overall."""
        prom = AsyncMock()
        # 9 SLIs x 1 chunk x 2 queries (success, total) = 18 calls
        prom.get_metric_value = AsyncMock(
            side_effect=[1000, 1000] * 9
        )
        calc = UptimeCalculator(chunker=chunker)
        result = await calc.calculate(prom, short_start, short_end, "PROD")

        assert result["value"] == pytest.approx(100.0, abs=0.01)
        assert result["unit"] == "%"
        assert result["kpi_name"] == "Uptime"

    @pytest.mark.asyncio
    async def test_99_9_uptime(self, short_start, short_end, chunker):
        """999 success / 1000 total for every SLI = 99.9% overall."""
        prom = AsyncMock()
        prom.get_metric_value = AsyncMock(
            side_effect=[999, 1000] * 9
        )
        calc = UptimeCalculator(chunker=chunker)
        result = await calc.calculate(prom, short_start, short_end, "PROD")

        assert result["value"] == pytest.approx(99.9, abs=0.01)

    @pytest.mark.asyncio
    async def test_zero_requests_handled(self, short_start, short_end, chunker):
        """Zero success / zero total should give 0% (safe divide), not an error."""
        prom = AsyncMock()
        prom.get_metric_value = AsyncMock(return_value=0.0)
        calc = UptimeCalculator(chunker=chunker)
        result = await calc.calculate(prom, short_start, short_end, "PROD")

        assert result["value"] == pytest.approx(0.0)
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_pillar_breakdown_structure(self, short_start, short_end, chunker):
        """Result should have breakdown for all 5 pillars."""
        prom = AsyncMock()
        prom.get_metric_value = AsyncMock(return_value=1000.0)
        calc = UptimeCalculator(chunker=chunker)
        result = await calc.calculate(prom, short_start, short_end, "PROD")

        breakdown = result["details"]["pillar_breakdown"]
        assert len(breakdown) == 5
        pillar_names = [p["pillar"] for p in breakdown]
        assert pillar_names == ["grafana", "mimir", "loki", "tempo", "pyroscope"]

    @pytest.mark.asyncio
    async def test_sli_count(self, short_start, short_end, chunker):
        """Detail should include the total SLI count (9)."""
        prom = AsyncMock()
        prom.get_metric_value = AsyncMock(return_value=100.0)
        calc = UptimeCalculator(chunker=chunker)
        result = await calc.calculate(prom, short_start, short_end, "PROD")

        assert result["details"]["sli_count"] == 9

    @pytest.mark.asyncio
    async def test_kpi_name_and_unit(self, chunker):
        calc = UptimeCalculator(chunker=chunker)
        assert calc.kpi_name == "Uptime"
        assert calc.unit == "%"


# ===========================================================================
# BaseKPICalculator._safe_divide (tested indirectly through subclasses)
# ===========================================================================

class TestSafeDivide:
    """Test the _safe_divide helper inherited by all calculators."""

    def test_normal_division(self):
        calc = DataLossRateCalculator()
        assert calc._safe_divide(10, 100) == pytest.approx(0.1)

    def test_zero_denominator_returns_default(self):
        calc = DataLossRateCalculator()
        assert calc._safe_divide(10, 0) == 0.0

    def test_zero_denominator_custom_default(self):
        calc = DataLossRateCalculator()
        assert calc._safe_divide(10, 0, default=-1.0) == -1.0


# ===========================================================================
# BaseKPICalculator._build_result
# ===========================================================================

class TestBuildResult:
    """Test the _build_result helper."""

    def test_build_result_structure(self):
        calc = DataLossRateCalculator()
        result = calc._build_result(value=1.23456789, details={"foo": "bar"}, error=None)

        assert result["kpi_name"] == "Data Loss Rate"
        assert result["value"] == pytest.approx(1.234568, abs=1e-6)  # rounded to 6 dp
        assert result["unit"] == "%"
        assert result["details"] == {"foo": "bar"}
        assert result["error"] is None

    def test_build_result_with_error(self):
        calc = DataLossRateCalculator()
        result = calc._build_result(value=0.0, error="something went wrong")
        assert result["error"] == "something went wrong"
