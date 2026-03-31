"""
Time Window Chunking Engine for Observability KPI Reporting.

Grafana Cloud data sources impose query-window limits (typically 30 days).
This module splits arbitrary time ranges into compliant windows and provides
aggregation helpers so that KPI calculations can transparently span months
or even years of data.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Tuple

MAX_QUERY_WINDOW_DAYS: int = 30


@dataclass
class TimeWindow:
    """A single contiguous time range used for one platform query."""

    start: datetime
    end: datetime

    @property
    def duration_days(self) -> float:
        """Duration of this window expressed in fractional days."""
        return (self.end - self.start).total_seconds() / 86400

    def __str__(self) -> str:
        return (
            f"{self.start.isoformat()} \u2192 {self.end.isoformat()} "
            f"({self.duration_days:.1f}d)"
        )

    def __repr__(self) -> str:
        return (
            f"TimeWindow(start={self.start.isoformat()!r}, "
            f"end={self.end.isoformat()!r})"
        )


class TimeWindowChunker:
    """Engine that splits time ranges into <=30-day windows for Grafana/Prometheus queries.

    Platform retention and performance constraints require:
    - Logs (Loki):              max 30 days per query
    - Metrics (Mimir/Prometheus): max 30 days per query
    - Traces (Tempo):           max 30 days per query
    - Profiles (Pyroscope):     max 30 days per query

    Usage::

        chunker = TimeWindowChunker()
        windows = chunker.chunk(start_dt, end_dt)
        for w in windows:
            results.append(query_datasource(w.start, w.end))
        total = TimeWindowChunker.aggregate_counter_results(results)
    """

    def __init__(self, max_window_days: int = MAX_QUERY_WINDOW_DAYS) -> None:
        if max_window_days <= 0:
            raise ValueError(
                f"max_window_days must be a positive integer, got {max_window_days}"
            )
        self.max_window_days: int = max_window_days
        self.max_window_delta: timedelta = timedelta(days=max_window_days)

    # ------------------------------------------------------------------
    # Core chunking
    # ------------------------------------------------------------------

    def chunk(self, start: datetime, end: datetime) -> List[TimeWindow]:
        """Split a time range into consecutive windows of at most *max_window_days*.

        If the range is <= max_window_days, a single-element list is returned.
        If the range is longer, consecutive non-overlapping windows are created;
        the last window may be shorter than max_window_days.

        Parameters
        ----------
        start : datetime
            Inclusive start of the overall time range.
        end : datetime
            Exclusive end of the overall time range.

        Returns
        -------
        list[TimeWindow]
            Ordered list of contiguous, non-overlapping windows covering
            [start, end).

        Raises
        ------
        ValueError
            If *start* >= *end* or either value is ``None``.
        TypeError
            If *start* or *end* are not ``datetime`` instances.
        """
        self._validate_range(start, end)

        windows: List[TimeWindow] = []
        cursor = start

        while cursor < end:
            window_end = min(cursor + self.max_window_delta, end)
            windows.append(TimeWindow(start=cursor, end=window_end))
            cursor = window_end

        return windows

    def needs_chunking(self, start: datetime, end: datetime) -> bool:
        """Return ``True`` if the time range exceeds the maximum query window.

        Parameters
        ----------
        start : datetime
            Inclusive start of the range.
        end : datetime
            Exclusive end of the range.

        Returns
        -------
        bool
        """
        self._validate_range(start, end)
        return (end - start) > self.max_window_delta

    def get_effective_windows_description(
        self, start: datetime, end: datetime
    ) -> dict:
        """Return a human-/machine-readable description of the chunking strategy.

        Useful for embedding in generated reports so that readers can see
        exactly how the original time range was sliced.

        Parameters
        ----------
        start : datetime
            Inclusive start of the range.
        end : datetime
            Exclusive end of the range.

        Returns
        -------
        dict
            Keys:
            - ``original_range``: ``{start, end, duration_days}``
            - ``chunked``: bool indicating whether chunking was applied
            - ``num_windows``: number of windows produced
            - ``windows``: list of ``{start, end, duration_days}`` dicts
            - ``max_window_days``: configured maximum window size
        """
        self._validate_range(start, end)

        windows = self.chunk(start, end)
        total_duration = (end - start).total_seconds() / 86400

        return {
            "original_range": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "duration_days": round(total_duration, 2),
            },
            "chunked": len(windows) > 1,
            "num_windows": len(windows),
            "windows": [
                {
                    "start": w.start.isoformat(),
                    "end": w.end.isoformat(),
                    "duration_days": round(w.duration_days, 2),
                }
                for w in windows
            ],
            "max_window_days": self.max_window_days,
        }

    # ------------------------------------------------------------------
    # Aggregation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def aggregate_counter_results(chunked_results: List[float]) -> float:
        """Aggregate counter-type metric results across chunks by summing.

        Counters are monotonically increasing values (e.g. total requests,
        total errors).  The correct cross-chunk aggregation is a simple sum.

        Parameters
        ----------
        chunked_results : list[float]
            One value per chunk window.

        Returns
        -------
        float
            Sum of all chunk values.

        Raises
        ------
        ValueError
            If *chunked_results* is empty.
        """
        if not chunked_results:
            raise ValueError("chunked_results must not be empty")
        return sum(chunked_results)

    @staticmethod
    def aggregate_gauge_max(chunked_results: List[float]) -> float:
        """Aggregate gauge-type metric results across chunks by taking the max.

        Useful for peak utilisation metrics (e.g. max CPU %, max memory).

        Parameters
        ----------
        chunked_results : list[float]
            One value per chunk window.

        Returns
        -------
        float
            Maximum value across all chunks.

        Raises
        ------
        ValueError
            If *chunked_results* is empty.
        """
        if not chunked_results:
            raise ValueError("chunked_results must not be empty")
        return max(chunked_results)

    @staticmethod
    def aggregate_gauge_avg(chunked_results: List[float]) -> float:
        """Aggregate gauge-type metric results across chunks by averaging.

        Computes the simple arithmetic mean.  For duration-weighted averages
        use :meth:`aggregate_rate_results` with ``(value * duration, duration)``
        tuples instead.

        Parameters
        ----------
        chunked_results : list[float]
            One value per chunk window.

        Returns
        -------
        float
            Arithmetic mean of all chunk values.

        Raises
        ------
        ValueError
            If *chunked_results* is empty.
        """
        if not chunked_results:
            raise ValueError("chunked_results must not be empty")
        return sum(chunked_results) / len(chunked_results)

    @staticmethod
    def aggregate_rate_results(
        chunked_results: List[Tuple[float, float]],
    ) -> float:
        """Aggregate rate / ratio results across chunks.

        Each element is a ``(numerator_sum, denominator_sum)`` pair collected
        from one chunk window.  The overall rate is computed as::

            total_numerator / total_denominator

        This is the correct way to combine rates such as error-rate, success-rate,
        or availability percentages.

        Parameters
        ----------
        chunked_results : list[tuple[float, float]]
            One ``(numerator, denominator)`` pair per chunk.

        Returns
        -------
        float
            Combined rate across all chunks.

        Raises
        ------
        ValueError
            If *chunked_results* is empty or if the total denominator is zero.
        """
        if not chunked_results:
            raise ValueError("chunked_results must not be empty")

        total_numerator = sum(n for n, _ in chunked_results)
        total_denominator = sum(d for _, d in chunked_results)

        if total_denominator == 0:
            raise ValueError(
                "Total denominator across all chunks is zero; cannot compute rate"
            )

        return total_numerator / total_denominator

    @staticmethod
    def aggregate_percentile(
        chunked_series: List[List[float]], percentile: float
    ) -> float:
        """Approximate a percentile across chunks by merging raw values.

        All per-chunk sample lists are concatenated and the requested percentile
        is computed on the combined dataset using the *nearest-rank* method.

        .. note::
           This gives an exact result only when every raw sample is available.
           If individual chunks already returned a pre-computed percentile
           rather than raw samples, the result is an approximation.

        Parameters
        ----------
        chunked_series : list[list[float]]
            One list of sample values per chunk.
        percentile : float
            Desired percentile in the range ``[0, 100]``.

        Returns
        -------
        float
            The computed percentile value.

        Raises
        ------
        ValueError
            If no samples are available or if *percentile* is outside [0, 100].
        """
        if not (0 <= percentile <= 100):
            raise ValueError(
                f"percentile must be between 0 and 100, got {percentile}"
            )

        merged: List[float] = []
        for series in chunked_series:
            merged.extend(series)

        if not merged:
            raise ValueError(
                "No sample values available across chunks to compute percentile"
            )

        merged.sort()
        n = len(merged)

        if percentile == 0:
            return merged[0]
        if percentile == 100:
            return merged[-1]

        # Nearest-rank method: index = ceil(percentile/100 * n) - 1
        rank = math.ceil(percentile / 100 * n)
        # Clamp to valid range (handles floating-point edge cases)
        index = max(0, min(rank - 1, n - 1))
        return merged[index]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_range(start: datetime, end: datetime) -> None:
        """Validate that *start* and *end* form a legal time range.

        Raises
        ------
        TypeError
            If either argument is not a ``datetime``.
        ValueError
            If *start* >= *end*.
        """
        if not isinstance(start, datetime):
            raise TypeError(
                f"start must be a datetime instance, got {type(start).__name__}"
            )
        if not isinstance(end, datetime):
            raise TypeError(
                f"end must be a datetime instance, got {type(end).__name__}"
            )
        if start >= end:
            raise ValueError(
                f"start ({start.isoformat()}) must be strictly before "
                f"end ({end.isoformat()})"
            )
