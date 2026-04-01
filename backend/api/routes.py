"""API route definitions for the Observability KPI Reporting service."""

from __future__ import annotations

import io
import json
import logging
from datetime import datetime, timedelta
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from api.models import (
    EnvironmentConfig,
    HealthResponse,
    KPIResult,
    PillarKPIs,
    ReportRequest,
    ReportResponse,
    TimeWindow,
)

logger = logging.getLogger("observability_kpi.routes")

APP_VERSION = "1.0.0"

router = APIRouter(prefix="/api/v1", tags=["kpi"])

# ---------------------------------------------------------------------------
# Time-window chunking helpers
# ---------------------------------------------------------------------------

MAX_WINDOW_DAYS = 30


def chunk_time_range(start: datetime, end: datetime) -> list[TimeWindow]:
    """Split a time range into <= 30-day windows.

    Grafana datasources often impose query-duration limits.  This helper
    ensures every window fits within those constraints.
    """
    windows: list[TimeWindow] = []
    cursor = start
    while cursor < end:
        window_end = min(cursor + timedelta(days=MAX_WINDOW_DAYS), end)
        windows.append(TimeWindow(start=cursor, end=window_end))
        cursor = window_end
    return windows


# ---------------------------------------------------------------------------
# Grafana client helpers
# ---------------------------------------------------------------------------

def _build_headers(config: EnvironmentConfig) -> dict[str, str]:
    """Build HTTP headers for Grafana API calls.

    The token is extracted via SecretStr.get_secret_value() and is never
    written to logs.
    """
    return {
        "Authorization": f"Bearer {config.service_account_token.get_secret_value()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def _query_datasource(
    config: EnvironmentConfig,
    datasource_uid: str,
    query_body: dict,
    window: TimeWindow,
) -> dict:
    """Execute a single datasource query against Grafana's unified query API.

    Returns the parsed JSON response or raises HTTPException on failure.
    """
    url = f"{config.grafana_url}/api/ds/query"
    payload = {
        "queries": [
            {
                "datasource": {"uid": datasource_uid},
                "refId": "A",
                **query_body,
            }
        ],
        "from": str(int(window.start.timestamp() * 1000)),
        "to": str(int(window.end.timestamp() * 1000)),
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(
                url, headers=_build_headers(config), json=payload
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Grafana query failed: %s %s", exc.response.status_code, url
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Grafana returned {exc.response.status_code}: {exc.response.text[:500]}",
            ) from exc
        except httpx.RequestError as exc:
            logger.error("Grafana connection error: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Cannot reach Grafana at {config.grafana_url}: {exc}",
            ) from exc


# ---------------------------------------------------------------------------
# KPI computation per pillar
# ---------------------------------------------------------------------------

PILLARS: list[str] = ["mimir", "loki", "tempo", "pyroscope", "grafana"]


async def _compute_pillar_kpis(
    config: EnvironmentConfig,
    pillar: str,
    windows: list[TimeWindow],
) -> PillarKPIs:
    """Compute all KPIs for a single observability pillar.

    Each pillar defines its own set of metrics/queries.  The results from
    all time windows are aggregated into a single KPIResult per metric.
    """
    datasource_uid = config.datasource_uids.get(pillar)  # type: ignore[arg-type]
    if not datasource_uid:
        logger.warning("No datasource UID configured for pillar '%s'; skipping", pillar)
        return PillarKPIs(pillar=pillar, kpis=[])

    kpi_definitions = _get_kpi_definitions(pillar)
    results: list[KPIResult] = []

    for kpi_def in kpi_definitions:
        aggregated_values: list[float] = []

        for window in windows:
            try:
                resp = await _query_datasource(
                    config, datasource_uid, kpi_def["query"], window
                )
                value = _extract_value(resp, kpi_def.get("extractor", "mean"))
                if value is not None:
                    aggregated_values.append(value)
            except HTTPException:
                logger.warning(
                    "Query failed for KPI '%s' in window %s-%s; skipping window",
                    kpi_def["name"],
                    window.start.isoformat(),
                    window.end.isoformat(),
                )

        final_value = _aggregate(aggregated_values, kpi_def.get("aggregation", "mean"))
        results.append(
            KPIResult(
                kpi_name=kpi_def["name"],
                value=final_value,
                unit=kpi_def["unit"],
                pillar=pillar,
                environment=config.environment,
                time_windows=windows,
                details={
                    "window_count": len(windows),
                    "successful_windows": len(aggregated_values),
                    "raw_values": aggregated_values,
                },
            )
        )

    return PillarKPIs(pillar=pillar, kpis=results)


def _make_avail_kpis(metric: str, ingest_re: str, read_re: str) -> list[dict]:
    """Generate availability KPI definitions (overall, ingest-path, read-path)."""
    ok_all = "sum(rate(%s{status_code=~'2..'}[5m]))" % metric
    total_all = "sum(rate(%s[5m]))" % metric
    ok_ingest = "sum(rate(%s{status_code=~'2..', route=~'%s'}[5m]))" % (metric, ingest_re)
    total_ingest = "sum(rate(%s{route=~'%s'}[5m]))" % (metric, ingest_re)
    ok_read = "sum(rate(%s{status_code=~'2..', route=~'%s'}[5m]))" % (metric, read_re)
    total_read = "sum(rate(%s{route=~'%s'}[5m]))" % (metric, read_re)
    return [
        {
            "name": "Uptime / Availability",
            "query": {"expr": "clamp_max(%s / %s * 100, 100)" % (ok_all, total_all), "instant": True},
            "unit": "%", "extractor": "single", "aggregation": "mean",
        },
        {
            "name": "Availability (Ingest)",
            "query": {"expr": "clamp_max(%s / %s * 100, 100)" % (ok_ingest, total_ingest), "instant": True},
            "unit": "%", "extractor": "single", "aggregation": "mean",
        },
        {
            "name": "Availability (Read)",
            "query": {"expr": "clamp_max(%s / %s * 100, 100)" % (ok_read, total_read), "instant": True},
            "unit": "%", "extractor": "single", "aggregation": "mean",
        },
    ]


def _make_resource_kpis(ns: str) -> list[dict]:
    """Generate CPU / Memory peak-utilization KPI definitions."""
    return [
        {
            "name": "Peak CPU Utilization",
            "query": {
                "expr": "max(rate(container_cpu_usage_seconds_total{namespace=~'%s'}[5m])) * 100" % ns,
                "instant": True,
            },
            "unit": "%", "extractor": "single", "aggregation": "max",
        },
        {
            "name": "Peak Memory Utilization",
            "query": {
                "expr": (
                    "max(container_memory_working_set_bytes{namespace=~'%s'}) / "
                    "scalar(sum(machine_memory_bytes) / count(machine_memory_bytes)) * 100"
                ) % ns,
                "instant": True,
            },
            "unit": "%", "extractor": "single", "aggregation": "max",
        },
    ]


def _make_cost_kpis(ns: str, volume_expr: str) -> list[dict]:
    """Generate cost KPI definitions (monthly cost, cost-per-GB)."""
    return [
        {
            "name": "Total Monthly Cost",
            "query": {
                "expr": "sum(namespace_cost_per_month{namespace=~'%s'}) or vector(0)" % ns,
                "instant": True,
            },
            "unit": "$", "extractor": "single", "aggregation": "sum",
        },
        {
            "name": "Cost per GB Ingested",
            "query": {
                "expr": (
                    "(sum(namespace_cost_per_month{namespace=~'%s'}) or vector(0)) / "
                    "clamp_min(%s / 1e9, 0.001)"
                ) % (ns, volume_expr),
                "instant": True,
            },
            "unit": "$/GB", "extractor": "single", "aggregation": "mean",
        },
    ]


def _get_kpi_definitions(pillar: str) -> list[dict]:
    """Return KPI definitions for a pillar.

    KPI names are aligned with frontend page search fragments:
    availability/uptime, ingest+avail, read+avail, loss, cpu, memory,
    monthly cost, cost per gb, ingest (volume), latency.
    """
    definitions: dict[str, list[dict]] = {
        "mimir": [
            *_make_avail_kpis(
                "cortex_request_duration_seconds_count",
                "/distributor.Distributor/Push|api_v1_push|.*write.*",
                "api_prom_api_v1_query.*|api_prom_api_v1_labels|.*read.*",
            ),
            {
                "name": "Data Loss Rate",
                "query": {
                    "expr": (
                        "clamp_min(sum(rate(cortex_discarded_samples_total[5m])) / "
                        "sum(rate(cortex_ingester_ingested_samples_total[5m])) * 100, 0)"
                    ),
                    "instant": True,
                },
                "unit": "%", "extractor": "single", "aggregation": "mean",
            },
            {
                "name": "Ingestion Volume",
                "query": {
                    "expr": "sum(increase(cortex_ingester_ingested_samples_total[24h])) * 2",
                    "instant": True,
                },
                "unit": "bytes", "extractor": "single", "aggregation": "sum",
            },
            *_make_resource_kpis(".*mimir.*|.*cortex.*"),
            {
                "name": "P99 Query Latency",
                "query": {
                    "expr": "histogram_quantile(0.99, sum(rate(cortex_request_duration_seconds_bucket{route=~'api_prom_api_v1_query.*'}[5m])) by (le))",
                    "instant": True,
                },
                "unit": "s", "extractor": "single", "aggregation": "max",
            },
            *_make_cost_kpis(
                ".*mimir.*|.*cortex.*",
                "sum(increase(cortex_ingester_ingested_samples_total[30d])) * 2",
            ),
        ],
        "loki": [
            *_make_avail_kpis(
                "loki_request_duration_seconds_count",
                ".*push.*|.*distributor.*|/loki.Pusher/Push",
                ".*query.*|.*tail.*|loki_api_v1.*",
            ),
            {
                "name": "Data Loss Rate",
                "query": {
                    "expr": (
                        "clamp_min(sum(rate(loki_distributor_lines_dropped_total[5m])) / "
                        "sum(rate(loki_distributor_lines_received_total[5m])) * 100, 0)"
                    ),
                    "instant": True,
                },
                "unit": "%", "extractor": "single", "aggregation": "mean",
            },
            {
                "name": "Ingestion Volume",
                "query": {
                    "expr": "sum(increase(loki_distributor_bytes_received_total[24h]))",
                    "instant": True,
                },
                "unit": "bytes", "extractor": "single", "aggregation": "sum",
            },
            *_make_resource_kpis(".*loki.*"),
            {
                "name": "P99 Query Latency",
                "query": {
                    "expr": "histogram_quantile(0.99, sum(rate(loki_request_duration_seconds_bucket[5m])) by (le))",
                    "instant": True,
                },
                "unit": "s", "extractor": "single", "aggregation": "max",
            },
            *_make_cost_kpis(
                ".*loki.*",
                "sum(increase(loki_distributor_bytes_received_total[30d]))",
            ),
        ],
        "tempo": [
            *_make_avail_kpis(
                "tempo_request_duration_seconds_count",
                ".*push.*|.*distributor.*|/tempo.Pusher/Push",
                ".*query.*|.*traces.*|/tempo.Querier/.*",
            ),
            {
                "name": "Data Loss Rate",
                "query": {
                    "expr": (
                        "clamp_min(sum(rate(tempo_discarded_spans_total[5m])) / "
                        "sum(rate(tempo_distributor_spans_received_total[5m])) * 100, 0)"
                    ),
                    "instant": True,
                },
                "unit": "%", "extractor": "single", "aggregation": "mean",
            },
            {
                "name": "Ingestion Volume",
                "query": {
                    "expr": "sum(increase(tempo_distributor_bytes_received_total[24h]))",
                    "instant": True,
                },
                "unit": "bytes", "extractor": "single", "aggregation": "sum",
            },
            *_make_resource_kpis(".*tempo.*"),
            {
                "name": "P99 Query Latency",
                "query": {
                    "expr": "histogram_quantile(0.99, sum(rate(tempo_request_duration_seconds_bucket[5m])) by (le))",
                    "instant": True,
                },
                "unit": "s", "extractor": "single", "aggregation": "max",
            },
            *_make_cost_kpis(
                ".*tempo.*",
                "sum(increase(tempo_distributor_bytes_received_total[30d]))",
            ),
        ],
        "pyroscope": [
            *_make_avail_kpis(
                "pyroscope_request_duration_seconds_count",
                ".*push.*|.*ingest.*",
                ".*query.*|.*render.*|.*select.*",
            ),
            {
                "name": "Data Loss Rate",
                "query": {
                    "expr": (
                        "clamp_min(sum(rate(pyroscope_discarded_samples_total[5m])) / "
                        "sum(rate(pyroscope_ingestion_total[5m])) * 100, 0)"
                    ),
                    "instant": True,
                },
                "unit": "%", "extractor": "single", "aggregation": "mean",
            },
            {
                "name": "Ingestion Volume",
                "query": {
                    "expr": "sum(increase(pyroscope_ingested_bytes_total[24h]))",
                    "instant": True,
                },
                "unit": "bytes", "extractor": "single", "aggregation": "sum",
            },
            *_make_resource_kpis(".*pyroscope.*"),
            {
                "name": "P99 Query Latency",
                "query": {
                    "expr": "histogram_quantile(0.99, sum(rate(pyroscope_request_duration_seconds_bucket[5m])) by (le))",
                    "instant": True,
                },
                "unit": "s", "extractor": "single", "aggregation": "max",
            },
            *_make_cost_kpis(
                ".*pyroscope.*",
                "sum(increase(pyroscope_ingested_bytes_total[30d]))",
            ),
        ],
        "grafana": [
            *_make_avail_kpis(
                "grafana_http_request_duration_seconds_count",
                ".*POST.*|.*PUT.*|.*save.*",
                ".*GET.*|.*dashboard.*|.*search.*",
            ),
            {
                "name": "Data Loss Rate",
                "query": {"expr": "vector(0)", "instant": True},
                "unit": "%", "extractor": "single", "aggregation": "mean",
            },
            *_make_resource_kpis(".*grafana.*"),
            {
                "name": "P99 API Latency",
                "query": {
                    "expr": "histogram_quantile(0.99, sum(rate(grafana_http_request_duration_seconds_bucket[5m])) by (le))",
                    "instant": True,
                },
                "unit": "s", "extractor": "single", "aggregation": "max",
            },
            {
                "name": "Total Monthly Cost",
                "query": {
                    "expr": "sum(namespace_cost_per_month{namespace=~'.*grafana.*'}) or vector(0)",
                    "instant": True,
                },
                "unit": "$", "extractor": "single", "aggregation": "sum",
            },
        ],
    }
    return definitions.get(pillar, [])


def _extract_value(response: dict, extractor: str) -> float | None:
    """Pull a scalar value out of a Grafana datasource query response.

    Returns None when the response has no usable data.
    """
    try:
        results = response.get("results", {})
        for _ref_id, result in results.items():
            frames = result.get("frames", [])
            for frame in frames:
                values_field = frame.get("data", {}).get("values", [])
                if len(values_field) >= 2:
                    numeric_values = values_field[1]
                    if numeric_values:
                        if extractor == "single":
                            return float(numeric_values[-1])
                        if extractor == "mean":
                            return float(sum(numeric_values) / len(numeric_values))
        return None
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        logger.debug("Value extraction failed: %s", exc)
        return None


def _aggregate(values: list[float], method: str) -> float:
    """Aggregate a list of per-window values into a single KPI value."""
    if not values:
        return 0.0
    if method == "sum":
        return sum(values)
    if method == "max":
        return max(values)
    if method == "min":
        return min(values)
    # default: mean
    return sum(values) / len(values)


# ---------------------------------------------------------------------------
# Report generation helpers
# ---------------------------------------------------------------------------

def _generate_json_report(report: ReportResponse) -> StreamingResponse:
    """Serialize the report to JSON and return as a downloadable file."""
    content = report.model_dump_json(indent=2)
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=kpi_report.json"},
    )


def _generate_csv_report(report: ReportResponse) -> StreamingResponse:
    """Flatten KPI data into CSV rows and return as a downloadable file."""
    lines: list[str] = [
        "environment,pillar,kpi_name,value,unit,window_count,generated_at"
    ]
    for pillar_kpis in report.kpis:
        for kpi in pillar_kpis.kpis:
            lines.append(
                ",".join([
                    report.environment,
                    kpi.pillar,
                    f'"{kpi.kpi_name}"',
                    f"{kpi.value:.6f}",
                    kpi.unit,
                    str(kpi.details.get("window_count", 0)),
                    report.generated_at.isoformat(),
                ])
            )
    csv_content = "\n".join(lines) + "\n"
    return StreamingResponse(
        io.BytesIO(csv_content.encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=kpi_report.csv"},
    )


def _generate_pdf_report(report: ReportResponse) -> StreamingResponse:
    """Build a simple PDF report using ReportLab and return as a download."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="PDF generation requires reportlab; install it to enable PDF reports.",
        ) from exc

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm)
    styles = getSampleStyleSheet()
    elements: list = []

    # Title
    elements.append(Paragraph(f"Observability KPI Report -- {report.environment}", styles["Title"]))
    elements.append(Spacer(1, 6 * mm))
    elements.append(
        Paragraph(
            f"Period: {report.time_range.get('start', 'N/A')} to {report.time_range.get('end', 'N/A')}",
            styles["Normal"],
        )
    )
    elements.append(
        Paragraph(f"Generated: {report.generated_at.isoformat()}", styles["Normal"])
    )
    elements.append(Spacer(1, 8 * mm))

    # KPI table per pillar
    for pillar_kpis in report.kpis:
        elements.append(Paragraph(f"Pillar: {pillar_kpis.pillar.upper()}", styles["Heading2"]))
        table_data = [["KPI", "Value", "Unit"]]
        for kpi in pillar_kpis.kpis:
            table_data.append([kpi.kpi_name, f"{kpi.value:.4f}", kpi.unit])

        tbl = Table(table_data, hAlign="LEFT")
        tbl.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4A90D9")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
            ])
        )
        elements.append(tbl)
        elements.append(Spacer(1, 6 * mm))

    doc.build(elements)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=kpi_report.pdf"},
    )


# ---------------------------------------------------------------------------
# Route: Compute all KPIs
# ---------------------------------------------------------------------------

@router.post(
    "/kpis",
    response_model=ReportResponse,
    summary="Compute all observability KPIs",
    status_code=status.HTTP_200_OK,
)
async def compute_all_kpis(config: EnvironmentConfig) -> ReportResponse:
    """Compute KPIs for every configured pillar and return the results."""
    logger.info(
        "Computing all KPIs for env=%s range=%s..%s",
        config.environment,
        config.time_range_start.isoformat(),
        config.time_range_end.isoformat(),
    )

    windows = chunk_time_range(config.time_range_start, config.time_range_end)

    pillar_results: list[PillarKPIs] = []
    for pillar in PILLARS:
        result = await _compute_pillar_kpis(config, pillar, windows)
        pillar_results.append(result)

    return ReportResponse(
        environment=config.environment,
        time_range={
            "start": config.time_range_start.isoformat(),
            "end": config.time_range_end.isoformat(),
        },
        effective_query_windows=windows,
        kpis=pillar_results,
        generated_at=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# Route: Compute KPIs for a single pillar
# ---------------------------------------------------------------------------

@router.post(
    "/kpis/{pillar}",
    response_model=ReportResponse,
    summary="Compute KPIs for a specific observability pillar",
    status_code=status.HTTP_200_OK,
)
async def compute_pillar_kpis(
    pillar: Literal["mimir", "loki", "tempo", "pyroscope", "grafana"],
    config: EnvironmentConfig,
) -> ReportResponse:
    """Compute KPIs for a single pillar (mimir, loki, tempo, pyroscope, grafana)."""
    logger.info(
        "Computing KPIs for pillar=%s env=%s range=%s..%s",
        pillar,
        config.environment,
        config.time_range_start.isoformat(),
        config.time_range_end.isoformat(),
    )

    windows = chunk_time_range(config.time_range_start, config.time_range_end)
    result = await _compute_pillar_kpis(config, pillar, windows)

    return ReportResponse(
        environment=config.environment,
        time_range={
            "start": config.time_range_start.isoformat(),
            "end": config.time_range_end.isoformat(),
        },
        effective_query_windows=windows,
        kpis=[result],
        generated_at=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# Route: Generate downloadable report
# ---------------------------------------------------------------------------

@router.post(
    "/report",
    summary="Generate a downloadable KPI report",
    status_code=status.HTTP_200_OK,
)
async def generate_report(request: ReportRequest) -> StreamingResponse:
    """Compute all KPIs and return the results in the requested format (pdf, csv, json)."""
    logger.info(
        "Generating %s report for env=%s",
        request.format,
        request.config.environment,
    )

    # Re-use the KPI computation logic
    report = await compute_all_kpis(request.config)

    if request.format == "csv":
        return _generate_csv_report(report)
    if request.format == "pdf":
        return _generate_pdf_report(report)
    return _generate_json_report(report)


# ---------------------------------------------------------------------------
# Route: Validate Grafana connection
# ---------------------------------------------------------------------------

@router.post(
    "/validate-connection",
    summary="Test connectivity to the configured Grafana instance",
    status_code=status.HTTP_200_OK,
)
async def validate_connection(config: EnvironmentConfig) -> dict:
    """Attempt to reach the Grafana health endpoint and report the result."""
    url = f"{config.grafana_url}/api/health"
    logger.info(
        "Validating connection to Grafana at %s for env=%s",
        config.grafana_url,
        config.environment,
    )

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(url, headers=_build_headers(config))
            resp.raise_for_status()
            body = resp.json()

            # List configured datasource UIDs
            configured_ds = [
                f"{pillar}:{uid}"
                for pillar, uid in config.datasource_uids.items()
                if uid
            ]

            return {
                "success": True,
                "message": (
                    f"Connected to Grafana {body.get('version', 'unknown')} "
                    f"({config.environment})"
                ),
                "datasources": configured_ds,
            }
        except httpx.HTTPStatusError as exc:
            logger.error("Grafana health check failed: %s", exc.response.status_code)
            return {
                "success": False,
                "message": f"Grafana returned HTTP {exc.response.status_code}",
            }
        except httpx.RequestError as exc:
            logger.error("Cannot reach Grafana: %s", exc)
            return {
                "success": False,
                "message": f"Cannot reach Grafana at {config.grafana_url}: {exc}",
            }


# ---------------------------------------------------------------------------
# Route: Health check
# ---------------------------------------------------------------------------

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health check",
    status_code=status.HTTP_200_OK,
)
async def health_check() -> HealthResponse:
    """Return service health and version info."""
    return HealthResponse(status="ok", version=APP_VERSION)
