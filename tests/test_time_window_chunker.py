"""Tests for the TimeWindowChunker and its aggregation helpers.

Covers chunking logic, boundary conditions, validation, and all
aggregation methods (counter, gauge-max, gauge-avg, rate, percentile).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest

from time_window.chunker import TimeWindow, TimeWindowChunker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def chunker() -> TimeWindowChunker:
    """Default chunker with 30-day max window."""
    return TimeWindowChunker()


@pytest.fixture
def base_start() -> datetime:
    return datetime(2025, 1, 1)


# ---------------------------------------------------------------------------
# Single-window scenarios (range <= 30 days)
# ---------------------------------------------------------------------------

class TestSingleWindow:
    """Ranges that fit within one 30-day window."""

    def test_single_window_short_range(self, chunker: TimeWindowChunker, base_start: datetime):
        """A 7-day range should produce exactly 1 window."""
        end = base_start + timedelta(days=7)
        windows = chunker.chunk(base_start, end)
        assert len(windows) == 1
        assert windows[0].start == base_start
        assert windows[0].end == end

    def test_exact_30_day_boundary(self, chunker: TimeWindowChunker, base_start: datetime):
        """Exactly 30 days should still fit in 1 window (<=30)."""
        end = base_start + timedelta(days=30)
        windows = chunker.chunk(base_start, end)
        assert len(windows) == 1
        assert windows[0].start == base_start
        assert windows[0].end == end

    def test_1_day_range(self, chunker: TimeWindowChunker, base_start: datetime):
        """A single day should produce 1 window."""
        end = base_start + timedelta(days=1)
        windows = chunker.chunk(base_start, end)
        assert len(windows) == 1
        assert windows[0].duration_days == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Multi-window scenarios (range > 30 days)
# ---------------------------------------------------------------------------

class TestMultipleWindows:
    """Ranges that must be split into multiple windows."""

    def test_31_days_produces_2_windows(self, chunker: TimeWindowChunker, base_start: datetime):
        """31 days = 30-day window + 1-day window."""
        end = base_start + timedelta(days=31)
        windows = chunker.chunk(base_start, end)
        assert len(windows) == 2
        assert windows[0].duration_days == pytest.approx(30.0)
        assert windows[1].duration_days == pytest.approx(1.0)

    def test_60_days_produces_2_windows(self, chunker: TimeWindowChunker, base_start: datetime):
        """60 days = two exact 30-day windows."""
        end = base_start + timedelta(days=60)
        windows = chunker.chunk(base_start, end)
        assert len(windows) == 2
        assert windows[0].duration_days == pytest.approx(30.0)
        assert windows[1].duration_days == pytest.approx(30.0)

    def test_90_days_produces_3_windows(self, chunker: TimeWindowChunker, base_start: datetime):
        """90 days = three exact 30-day windows."""
        end = base_start + timedelta(days=90)
        windows = chunker.chunk(base_start, end)
        assert len(windows) == 3

    def test_91_days_produces_4_windows(self, chunker: TimeWindowChunker, base_start: datetime):
        """91 days = 30 + 30 + 30 + 1 = 4 windows."""
        end = base_start + timedelta(days=91)
        windows = chunker.chunk(base_start, end)
        assert len(windows) == 4
        assert windows[-1].duration_days == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Window contiguity and coverage
# ---------------------------------------------------------------------------

class TestWindowContiguityAndCoverage:
    """Windows must be contiguous and cover the entire original range."""

    @pytest.mark.parametrize("days", [1, 15, 30, 31, 60, 90, 91, 120, 365])
    def test_windows_are_contiguous(self, chunker: TimeWindowChunker, base_start: datetime, days: int):
        """End of window N must equal start of window N+1."""
        end = base_start + timedelta(days=days)
        windows = chunker.chunk(base_start, end)
        for i in range(len(windows) - 1):
            assert windows[i].end == windows[i + 1].start, (
                f"Gap between window {i} and {i+1}"
            )

    @pytest.mark.parametrize("days", [1, 15, 30, 31, 60, 90, 91, 120, 365])
    def test_windows_cover_entire_range(self, chunker: TimeWindowChunker, base_start: datetime, days: int):
        """First window starts at start; last window ends at end."""
        end = base_start + timedelta(days=days)
        windows = chunker.chunk(base_start, end)
        assert windows[0].start == base_start
        assert windows[-1].end == end


# ---------------------------------------------------------------------------
# needs_chunking
# ---------------------------------------------------------------------------

class TestNeedsChunking:
    """Test the needs_chunking predicate."""

    def test_false_for_30_days(self, chunker: TimeWindowChunker, base_start: datetime):
        """Exactly 30 days should NOT need chunking."""
        end = base_start + timedelta(days=30)
        assert chunker.needs_chunking(base_start, end) is False

    def test_false_for_short_range(self, chunker: TimeWindowChunker, base_start: datetime):
        """7-day range should NOT need chunking."""
        end = base_start + timedelta(days=7)
        assert chunker.needs_chunking(base_start, end) is False

    def test_true_for_31_days(self, chunker: TimeWindowChunker, base_start: datetime):
        """31 days should need chunking."""
        end = base_start + timedelta(days=31)
        assert chunker.needs_chunking(base_start, end) is True

    def test_true_for_90_days(self, chunker: TimeWindowChunker, base_start: datetime):
        end = base_start + timedelta(days=90)
        assert chunker.needs_chunking(base_start, end) is True


# ---------------------------------------------------------------------------
# get_effective_windows_description
# ---------------------------------------------------------------------------

class TestEffectiveWindowsDescription:
    """Test the human-/machine-readable description method."""

    def test_description_structure_single_window(self, chunker: TimeWindowChunker, base_start: datetime):
        end = base_start + timedelta(days=10)
        desc = chunker.get_effective_windows_description(base_start, end)

        assert "original_range" in desc
        assert "chunked" in desc
        assert "num_windows" in desc
        assert "windows" in desc
        assert "max_window_days" in desc

        assert desc["chunked"] is False
        assert desc["num_windows"] == 1
        assert desc["max_window_days"] == 30
        assert len(desc["windows"]) == 1

    def test_description_structure_multi_window(self, chunker: TimeWindowChunker, base_start: datetime):
        end = base_start + timedelta(days=61)
        desc = chunker.get_effective_windows_description(base_start, end)

        assert desc["chunked"] is True
        assert desc["num_windows"] == 3
        assert len(desc["windows"]) == 3

    def test_description_original_range(self, chunker: TimeWindowChunker, base_start: datetime):
        end = base_start + timedelta(days=45)
        desc = chunker.get_effective_windows_description(base_start, end)

        orig = desc["original_range"]
        assert orig["start"] == base_start.isoformat()
        assert orig["end"] == end.isoformat()
        assert orig["duration_days"] == 45.0


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    """Test that invalid inputs are rejected."""

    def test_start_after_end_raises(self, chunker: TimeWindowChunker):
        start = datetime(2025, 2, 1)
        end = datetime(2025, 1, 1)
        with pytest.raises(ValueError, match="must be strictly before"):
            chunker.chunk(start, end)

    def test_start_equals_end_raises(self, chunker: TimeWindowChunker):
        dt = datetime(2025, 1, 1)
        with pytest.raises(ValueError, match="must be strictly before"):
            chunker.chunk(dt, dt)

    def test_non_datetime_start_raises(self, chunker: TimeWindowChunker):
        with pytest.raises(TypeError, match="must be a datetime"):
            chunker.chunk("2025-01-01", datetime(2025, 2, 1))  # type: ignore

    def test_non_datetime_end_raises(self, chunker: TimeWindowChunker):
        with pytest.raises(TypeError, match="must be a datetime"):
            chunker.chunk(datetime(2025, 1, 1), "2025-02-01")  # type: ignore

    def test_max_window_days_zero_raises(self):
        with pytest.raises(ValueError, match="positive integer"):
            TimeWindowChunker(max_window_days=0)

    def test_max_window_days_negative_raises(self):
        with pytest.raises(ValueError, match="positive integer"):
            TimeWindowChunker(max_window_days=-5)


# ---------------------------------------------------------------------------
# Aggregation: counter (sum)
# ---------------------------------------------------------------------------

class TestAggregateCounter:
    def test_sum_of_values(self):
        assert TimeWindowChunker.aggregate_counter_results([10, 20, 30]) == 60

    def test_single_value(self):
        assert TimeWindowChunker.aggregate_counter_results([42.5]) == 42.5

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            TimeWindowChunker.aggregate_counter_results([])


# ---------------------------------------------------------------------------
# Aggregation: gauge max
# ---------------------------------------------------------------------------

class TestAggregateGaugeMax:
    def test_max_of_values(self):
        assert TimeWindowChunker.aggregate_gauge_max([10, 50, 30]) == 50

    def test_single_value(self):
        assert TimeWindowChunker.aggregate_gauge_max([99.9]) == 99.9

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            TimeWindowChunker.aggregate_gauge_max([])


# ---------------------------------------------------------------------------
# Aggregation: gauge avg
# ---------------------------------------------------------------------------

class TestAggregateGaugeAvg:
    def test_avg_of_values(self):
        assert TimeWindowChunker.aggregate_gauge_avg([10, 20, 30]) == pytest.approx(20.0)

    def test_single_value(self):
        assert TimeWindowChunker.aggregate_gauge_avg([7.0]) == pytest.approx(7.0)

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            TimeWindowChunker.aggregate_gauge_avg([])


# ---------------------------------------------------------------------------
# Aggregation: rate (numerator/denominator pairs)
# ---------------------------------------------------------------------------

class TestAggregateRate:
    def test_basic_rate(self):
        """(10+20+30) / (100+200+300) = 60/600 = 0.1"""
        result = TimeWindowChunker.aggregate_rate_results(
            [(10, 100), (20, 200), (30, 300)]
        )
        assert result == pytest.approx(0.1)

    def test_single_pair(self):
        result = TimeWindowChunker.aggregate_rate_results([(5, 100)])
        assert result == pytest.approx(0.05)

    def test_zero_denominator_raises(self):
        with pytest.raises(ValueError, match="zero"):
            TimeWindowChunker.aggregate_rate_results([(10, 0), (20, 0)])

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            TimeWindowChunker.aggregate_rate_results([])


# ---------------------------------------------------------------------------
# Aggregation: percentile
# ---------------------------------------------------------------------------

class TestAggregatePercentile:
    def test_p95_basic(self):
        """P95 of [1..100] should be 95 (nearest-rank method)."""
        series = [list(range(1, 101))]
        result = TimeWindowChunker.aggregate_percentile(series, 95)
        assert result == 95

    def test_p50_basic(self):
        """P50 (median) of [1..100] should be 50."""
        series = [list(range(1, 101))]
        result = TimeWindowChunker.aggregate_percentile(series, 50)
        assert result == 50

    def test_p0_returns_min(self):
        series = [[5, 10, 15, 20]]
        result = TimeWindowChunker.aggregate_percentile(series, 0)
        assert result == 5

    def test_p100_returns_max(self):
        series = [[5, 10, 15, 20]]
        result = TimeWindowChunker.aggregate_percentile(series, 100)
        assert result == 20

    def test_multiple_chunks_merged(self):
        """Samples from multiple chunks are merged before computing percentile."""
        series1 = [1, 2, 3, 4, 5]
        series2 = [6, 7, 8, 9, 10]
        result = TimeWindowChunker.aggregate_percentile([series1, series2], 50)
        assert result == 5  # P50 of [1..10] by nearest-rank = ceil(0.5*10)=5 => index 4 => value 5

    def test_empty_series_raises(self):
        with pytest.raises(ValueError, match="No sample values"):
            TimeWindowChunker.aggregate_percentile([[]], 50)

    def test_invalid_percentile_raises(self):
        with pytest.raises(ValueError, match="between 0 and 100"):
            TimeWindowChunker.aggregate_percentile([[1, 2, 3]], 101)

        with pytest.raises(ValueError, match="between 0 and 100"):
            TimeWindowChunker.aggregate_percentile([[1, 2, 3]], -1)


# ---------------------------------------------------------------------------
# TimeWindow dataclass
# ---------------------------------------------------------------------------

class TestTimeWindowDataclass:
    def test_duration_days(self):
        w = TimeWindow(start=datetime(2025, 1, 1), end=datetime(2025, 1, 11))
        assert w.duration_days == pytest.approx(10.0)

    def test_str_representation(self):
        w = TimeWindow(start=datetime(2025, 1, 1), end=datetime(2025, 1, 2))
        s = str(w)
        assert "2025-01-01" in s
        assert "2025-01-02" in s
        assert "1.0d" in s

    def test_repr_representation(self):
        w = TimeWindow(start=datetime(2025, 1, 1), end=datetime(2025, 1, 2))
        r = repr(w)
        assert "TimeWindow" in r
        assert "2025-01-01" in r
