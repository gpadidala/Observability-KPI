"""Prometheus query executor that operates through the Grafana datasource proxy.

All PromQL queries are routed via the Grafana unified query API so that
authentication, TLS, and datasource routing are handled centrally by
the :class:`GrafanaClient`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from clients.grafana_client import GrafanaAPIError, GrafanaClient
from time_window.chunker import TimeWindowChunker

logger = logging.getLogger(__name__)

# Maximum span (in days) per query chunk to avoid Prometheus / Grafana
# timeouts or memory pressure on large range queries.
_CHUNK_DAYS = 30


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _to_epoch_ms(dt: datetime) -> int:
    """Convert a datetime to Unix epoch milliseconds (UTC)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _parse_step_to_seconds(step: str) -> int:
    """Convert a Prometheus-style step string (e.g. ``'5m'``, ``'1h'``) to seconds."""
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    step = step.strip().lower()
    if step and step[-1] in multipliers:
        try:
            return int(step[:-1]) * multipliers[step[-1]]
        except ValueError:
            pass
    try:
        return int(step)
    except ValueError:
        return 3600  # default 1 hour


def _safe_float(value: Any) -> float:
    """Convert a Prometheus sample value to ``float``.

    Prometheus encodes numeric values as strings (e.g. ``"1.23"``).  Special
    values ``NaN``, ``+Inf``, ``-Inf`` are preserved by ``float()``.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# ------------------------------------------------------------------
# Exception
# ------------------------------------------------------------------

class PrometheusQueryError(Exception):
    """Raised when a Prometheus query fails or returns an unexpected format."""


# ------------------------------------------------------------------
# Executor
# ------------------------------------------------------------------

class PrometheusQueryExecutor:
    """Execute PromQL queries against a Prometheus datasource via Grafana.

    The executor delegates every HTTP call to a :class:`GrafanaClient`, which
    must already be initialised (used inside its async context manager).

    Usage::

        async with GrafanaClient(url, token) as gf:
            prom = PrometheusQueryExecutor(gf, datasource_uid="prometheus-1")
            value = await prom.get_metric_value("up", start, end)
    """

    def __init__(self, grafana_client: GrafanaClient, datasource_uid: str) -> None:
        self._grafana = grafana_client
        self._datasource_uid = datasource_uid

    # ------------------------------------------------------------------
    # Query payload builders
    # ------------------------------------------------------------------

    def _build_instant_payload(
        self,
        query: str,
        time: datetime,
        ref_id: str = "A",
    ) -> dict[str, Any]:
        """Build the full Grafana ``/api/ds/query`` payload for an instant query."""
        epoch_ms = str(_to_epoch_ms(time))
        return {
            "from": epoch_ms,
            "to": epoch_ms,
            "queries": [
                {
                    "refId": ref_id,
                    "expr": query,
                    "instant": True,
                    "range": False,
                    "utcOffsetSec": 0,
                    "intervalMs": 1000,
                    "maxDataPoints": 1,
                    "datasource": {
                        "uid": self._datasource_uid,
                        "type": "prometheus",
                    },
                }
            ],
        }

    def _build_range_payload(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "1h",
        ref_id: str = "A",
    ) -> dict[str, Any]:
        """Build the full Grafana ``/api/ds/query`` payload for a range query."""
        start_ms = _to_epoch_ms(start)
        end_ms = _to_epoch_ms(end)
        step_seconds = _parse_step_to_seconds(step)
        step_ms = step_seconds * 1000
        max_data_points = max(int((end_ms - start_ms) / step_ms), 1)

        return {
            "from": str(start_ms),
            "to": str(end_ms),
            "queries": [
                {
                    "refId": ref_id,
                    "expr": query,
                    "instant": False,
                    "range": True,
                    "utcOffsetSec": 0,
                    "intervalMs": step_ms,
                    "maxDataPoints": max_data_points,
                    "datasource": {
                        "uid": self._datasource_uid,
                        "type": "prometheus",
                    },
                }
            ],
        }

    # ------------------------------------------------------------------
    # Public query methods
    # ------------------------------------------------------------------

    async def instant_query(self, query: str, time: datetime) -> dict[str, Any]:
        """Execute a Prometheus instant query at a specific point in time.

        Args:
            query: PromQL expression.
            time: Evaluation timestamp.

        Returns:
            Parsed Prometheus result with ``resultType`` and ``result`` keys.

        Raises:
            PrometheusQueryError: On query failure or unexpected response shape.
        """
        payload = self._build_instant_payload(query, time)
        try:
            raw = await self._grafana._request(
                "POST", "/api/ds/query", json_body=payload
            )
        except GrafanaAPIError as exc:
            raise PrometheusQueryError(
                f"Instant query failed for expr={query!r}: {exc.message}"
            ) from exc

        return self._parse_response(raw)

    async def range_query(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "1h",
    ) -> dict[str, Any]:
        """Execute a Prometheus range query.

        Args:
            query: PromQL expression.
            start: Range start (inclusive).
            end: Range end (inclusive).
            step: Resolution step (e.g. ``"1h"``, ``"5m"``, ``"30s"``).

        Returns:
            Parsed Prometheus result with ``resultType`` and ``result`` keys.

        Raises:
            PrometheusQueryError: On failure.
        """
        payload = self._build_range_payload(query, start, end, step)
        try:
            raw = await self._grafana._request(
                "POST", "/api/ds/query", json_body=payload
            )
        except GrafanaAPIError as exc:
            raise PrometheusQueryError(
                f"Range query failed for expr={query!r}: {exc.message}"
            ) from exc

        return self._parse_response(raw)

    async def query_with_chunking(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "1h",
    ) -> list[dict[str, Any]]:
        """Execute a range query with automatic time-window chunking.

        Large time ranges are split into chunks of up to 30 days each using
        :class:`TimeWindowChunker`.  Results from every chunk are aggregated
        into a single list.

        Args:
            query: PromQL expression.
            start: Overall range start.
            end: Overall range end.
            step: Resolution step.

        Returns:
            Aggregated list of Prometheus result entries across all chunks.

        Raises:
            PrometheusQueryError: If any chunk query fails.
        """
        chunker = TimeWindowChunker(chunk_days=_CHUNK_DAYS)
        chunks = chunker.chunk(start, end)

        aggregated_results: list[dict[str, Any]] = []

        for chunk_start, chunk_end in chunks:
            logger.debug(
                "Querying chunk %s -> %s for expr=%s",
                chunk_start.isoformat(),
                chunk_end.isoformat(),
                query,
            )
            result = await self.range_query(query, chunk_start, chunk_end, step)
            result_entries = result.get("result", [])
            if isinstance(result_entries, list):
                aggregated_results.extend(result_entries)

        return aggregated_results

    async def get_metric_value(
        self,
        query: str,
        start: datetime,
        end: datetime,
    ) -> float:
        """Execute a query and return a single scalar value.

        The value is computed as the **sum** of the latest sample across all
        returned series / vectors.  This is useful for summary KPI queries
        that are expected to yield a single number.

        Args:
            query: PromQL expression.
            start: Range start.
            end: Range end.

        Returns:
            Aggregated scalar float (sum of all result values).

        Raises:
            PrometheusQueryError: On failure or when no data is returned.
        """
        result = await self.range_query(query, start, end, step="1h")
        result_type = result.get("resultType", "")
        entries = result.get("result", [])

        if not entries:
            raise PrometheusQueryError(
                f"No data returned for expr={query!r} "
                f"({start.isoformat()} - {end.isoformat()})"
            )

        total = 0.0

        if result_type == "scalar":
            # Scalar result: entries is [timestamp, "value"]
            total = _safe_float(entries)
        elif result_type in ("vector", "matrix"):
            for entry in entries:
                values = entry.get("values", [])
                value_pair = entry.get("value")
                if values:
                    # Matrix: take the last sample in each series.
                    _, val = values[-1]
                    total += _safe_float(val)
                elif value_pair is not None:
                    # Vector: single [timestamp, "value"].
                    _, val = value_pair
                    total += _safe_float(val)
        else:
            # Best-effort fallback for unknown result types.
            for entry in entries:
                values = entry.get("values", [])
                value_pair = entry.get("value")
                if values:
                    _, val = values[-1]
                    total += _safe_float(val)
                elif value_pair is not None:
                    _, val = value_pair
                    total += _safe_float(val)

        return total

    async def get_metric_series(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "1h",
    ) -> list[dict[str, Any]]:
        """Return time-series data points for a PromQL query.

        Each returned dict contains:

        - ``metric`` -- label-set dictionary
        - ``values`` -- list of ``{"timestamp": float, "value": float}`` dicts

        Args:
            query: PromQL expression.
            start: Range start.
            end: Range end.
            step: Resolution step.

        Returns:
            List of series dicts.

        Raises:
            PrometheusQueryError: On failure.
        """
        result = await self.range_query(query, start, end, step)
        entries = result.get("result", [])

        series_list: list[dict[str, Any]] = []
        for entry in entries:
            metric_labels: dict[str, str] = entry.get("metric", {})
            raw_values: list[Any] = entry.get("values", [])
            # Handle instant-vector shape where only ``value`` is present.
            if not raw_values and entry.get("value"):
                raw_values = [entry["value"]]

            data_points = [
                {"timestamp": float(ts), "value": _safe_float(val)}
                for ts, val in raw_values
            ]
            series_list.append({"metric": metric_labels, "values": data_points})

        return series_list

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(raw: dict[str, Any]) -> dict[str, Any]:
        """Extract the Prometheus result from a Grafana ``/api/ds/query`` envelope.

        Grafana wraps datasource results per ``refId`` using data-frame encoding.
        This method unwraps the first result and normalises it into the standard
        Prometheus ``{"resultType": ..., "result": ...}`` shape.

        Raises:
            PrometheusQueryError: If the response cannot be parsed.
        """
        # Top-level error reported by Grafana.
        if raw.get("error"):
            raise PrometheusQueryError(f"Grafana query error: {raw['error']}")

        results = raw.get("results", {})
        if not results:
            raise PrometheusQueryError(
                "Empty results envelope from Grafana datasource query"
            )

        # Grab the first refId result (we always use "A").
        ref_result: dict[str, Any] | None = None
        for _ref_id, ref_data in results.items():
            ref_result = ref_data
            break

        if ref_result is None:
            raise PrometheusQueryError("No ref result found in Grafana response")

        # Per-query error.
        if ref_result.get("error"):
            raise PrometheusQueryError(
                f"Datasource query error: {ref_result['error']}"
            )

        frames: list[dict[str, Any]] = ref_result.get("frames", [])
        if not frames:
            return {"resultType": "matrix", "result": []}

        # Convert Grafana data-frames back to Prometheus-style result entries.
        parsed_results: list[dict[str, Any]] = []
        result_type = "matrix"

        for frame in frames:
            schema = frame.get("schema", {})
            data = frame.get("data", {})
            fields: list[dict[str, Any]] = schema.get("fields", [])
            values_columns: list[list[Any]] = data.get("values", [])

            # Extract metric labels from the last field's labels (Grafana convention).
            metric_labels: dict[str, str] = {}
            for field in fields:
                labels = field.get("labels")
                if labels:
                    metric_labels = dict(labels)
                    break

            # Typically: values_columns[0] = timestamps, values_columns[1] = values.
            if len(values_columns) >= 2:
                timestamps = values_columns[0]
                vals = values_columns[1]
                paired = list(zip(timestamps, vals))
                if len(paired) == 1:
                    result_type = "vector"
                    parsed_results.append(
                        {"metric": metric_labels, "value": paired[0]}
                    )
                else:
                    parsed_results.append(
                        {"metric": metric_labels, "values": paired}
                    )
            elif len(values_columns) == 1:
                result_type = "scalar"
                scalar_val = values_columns[0][0] if values_columns[0] else 0
                parsed_results.append(
                    {"metric": metric_labels, "value": [0, scalar_val]}
                )

        return {"resultType": result_type, "result": parsed_results}
