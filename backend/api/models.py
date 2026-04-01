"""Pydantic models for the Observability KPI Reporting API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, SecretStr, field_validator


# ---------------------------------------------------------------------------
# Shared / primitive models
# ---------------------------------------------------------------------------

class TimeWindow(BaseModel):
    """A discrete time window used for querying or reporting."""

    start: datetime = Field(..., description="Window start (inclusive), ISO-8601")
    end: datetime = Field(..., description="Window end (exclusive), ISO-8601")

    @field_validator("end")
    @classmethod
    def end_after_start(cls, v: datetime, info: Any) -> datetime:
        start = info.data.get("start")
        if start is not None and v <= start:
            raise ValueError("'end' must be strictly after 'start'")
        return v


# ---------------------------------------------------------------------------
# Configuration supplied at runtime by the caller
# ---------------------------------------------------------------------------

class EnvironmentConfig(BaseModel):
    """Runtime configuration for a single Grafana environment.

    All connection details are provided per-request -- nothing is hard-coded.
    """

    environment: Literal["PERF", "PROD"] = Field(
        ..., description="Target environment label"
    )
    grafana_url: str = Field(
        ...,
        description="Base URL of the Grafana instance (e.g. https://grafana.example.com)",
        examples=["https://grafana.example.com"],
    )
    service_account_token: SecretStr = Field(
        ..., description="Grafana service-account token (never logged)"
    )
    datasource_uids: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of observability pillar to Grafana datasource UID (partial is OK)",
        examples=[{
            "mimir": "abc123",
            "loki": "def456",
            "tempo": "ghi789",
            "pyroscope": "jkl012",
            "grafana": "mno345",
        }],
    )
    time_range_start: datetime = Field(
        ..., description="Report period start (inclusive), ISO-8601"
    )
    time_range_end: datetime = Field(
        ..., description="Report period end (exclusive), ISO-8601"
    )

    @field_validator("grafana_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("time_range_end")
    @classmethod
    def end_after_start(cls, v: datetime, info: Any) -> datetime:
        start = info.data.get("time_range_start")
        if start is not None and v <= start:
            raise ValueError("'time_range_end' must be after 'time_range_start'")
        return v


# ---------------------------------------------------------------------------
# KPI result models
# ---------------------------------------------------------------------------

class KPIResult(BaseModel):
    """A single computed KPI value."""

    kpi_name: str = Field(..., description="Human-readable KPI name")
    value: float = Field(..., description="Computed numeric value")
    unit: str = Field(..., description="Unit of measurement (%, req/s, ms, etc.)")
    pillar: str = Field(..., description="Observability pillar this KPI belongs to")
    environment: str = Field(..., description="Environment the KPI was computed for")
    time_windows: list[TimeWindow] = Field(
        default_factory=list,
        description="Time windows that were queried to compute this KPI",
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary detail payload (breakdown, thresholds, etc.)",
    )


class PillarKPIs(BaseModel):
    """All KPI results for a single observability pillar."""

    pillar: str = Field(..., description="Pillar name (mimir, loki, tempo, ...)")
    kpis: list[KPIResult] = Field(
        default_factory=list, description="Computed KPIs for this pillar"
    )


# ---------------------------------------------------------------------------
# Request / response envelopes
# ---------------------------------------------------------------------------

class ReportRequest(BaseModel):
    """Request body for generating a downloadable report."""

    config: EnvironmentConfig
    format: Literal["pdf", "csv", "json"] = Field(
        "json", description="Desired output format"
    )


class ReportResponse(BaseModel):
    """Top-level response for KPI computation."""

    environment: str = Field(..., description="Environment label")
    time_range: dict[str, str] = Field(
        ..., description="Requested time range as {start, end} ISO strings"
    )
    effective_query_windows: list[TimeWindow] = Field(
        default_factory=list,
        description="Actual windows used after chunking long ranges",
    )
    kpis: list[PillarKPIs] = Field(
        default_factory=list, description="KPI results grouped by pillar"
    )
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the report was generated",
    )


class HealthResponse(BaseModel):
    """Response body for the health-check endpoint."""

    status: str = Field("ok", description="Service health status")
    version: str = Field(..., description="Application version string")
