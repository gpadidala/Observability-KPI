"""Tests for the Pydantic API models.

Covers EnvironmentConfig validation, TimeWindow, KPIResult serialisation,
and SecretStr protection.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from api.models import (
    EnvironmentConfig,
    KPIResult,
    TimeWindow,
)


# ---------------------------------------------------------------------------
# EnvironmentConfig
# ---------------------------------------------------------------------------

class TestEnvironmentConfig:
    """Test EnvironmentConfig validation rules."""

    _BASE_CONFIG = {
        "grafana_url": "https://grafana.example.com",
        "service_account_token": "secret-token-123",
        "datasource_uids": {
            "mimir": "uid1",
            "loki": "uid2",
            "tempo": "uid3",
            "pyroscope": "uid4",
            "grafana": "uid5",
        },
        "time_range_start": "2025-03-01T00:00:00",
        "time_range_end": "2025-03-08T00:00:00",
    }

    def test_accepts_prod(self):
        config = EnvironmentConfig(environment="PROD", **self._BASE_CONFIG)
        assert config.environment == "PROD"

    def test_accepts_perf(self):
        config = EnvironmentConfig(environment="PERF", **self._BASE_CONFIG)
        assert config.environment == "PERF"

    def test_rejects_invalid_environment(self):
        with pytest.raises(ValidationError) as exc_info:
            EnvironmentConfig(environment="DEV", **self._BASE_CONFIG)
        errors = exc_info.value.errors()
        assert any("environment" in str(e.get("loc", "")) for e in errors)

    def test_rejects_staging_environment(self):
        with pytest.raises(ValidationError):
            EnvironmentConfig(environment="STAGING", **self._BASE_CONFIG)

    def test_time_range_end_must_be_after_start(self):
        """time_range_end <= time_range_start should fail validation."""
        with pytest.raises(ValidationError, match="time_range_end"):
            EnvironmentConfig(
                environment="PROD",
                grafana_url="https://grafana.example.com",
                service_account_token="token",
                datasource_uids={
                    "mimir": "uid1",
                    "loki": "uid2",
                    "tempo": "uid3",
                    "pyroscope": "uid4",
                    "grafana": "uid5",
                },
                time_range_start="2025-03-08T00:00:00",
                time_range_end="2025-03-01T00:00:00",
            )

    def test_time_range_end_equals_start_fails(self):
        with pytest.raises(ValidationError, match="time_range_end"):
            EnvironmentConfig(
                environment="PROD",
                grafana_url="https://grafana.example.com",
                service_account_token="token",
                datasource_uids={
                    "mimir": "uid1",
                    "loki": "uid2",
                    "tempo": "uid3",
                    "pyroscope": "uid4",
                    "grafana": "uid5",
                },
                time_range_start="2025-03-08T00:00:00",
                time_range_end="2025-03-08T00:00:00",
            )

    def test_secret_token_not_exposed_in_serialization(self):
        """SecretStr should be masked in model_dump() and JSON serialisation."""
        config = EnvironmentConfig(environment="PROD", **self._BASE_CONFIG)

        # model_dump should mask the secret
        dumped = config.model_dump()
        token_value = dumped["service_account_token"]
        assert "secret-token-123" not in str(token_value)

        # Direct access to .get_secret_value() should reveal it
        assert config.service_account_token.get_secret_value() == "secret-token-123"

    def test_secret_token_not_in_json(self):
        """JSON serialisation should not contain the raw token."""
        config = EnvironmentConfig(environment="PROD", **self._BASE_CONFIG)
        json_str = config.model_dump_json()
        assert "secret-token-123" not in json_str

    def test_grafana_url_trailing_slash_stripped(self):
        config = EnvironmentConfig(
            environment="PROD",
            grafana_url="https://grafana.example.com/",
            service_account_token="token",
            datasource_uids={
                "mimir": "uid1",
                "loki": "uid2",
                "tempo": "uid3",
                "pyroscope": "uid4",
                "grafana": "uid5",
            },
            time_range_start="2025-03-01T00:00:00",
            time_range_end="2025-03-08T00:00:00",
        )
        assert config.grafana_url == "https://grafana.example.com"


# ---------------------------------------------------------------------------
# TimeWindow
# ---------------------------------------------------------------------------

class TestTimeWindow:
    """Test the TimeWindow model validation."""

    def test_valid_window(self):
        tw = TimeWindow(
            start=datetime(2025, 3, 1),
            end=datetime(2025, 3, 8),
        )
        assert tw.start == datetime(2025, 3, 1)
        assert tw.end == datetime(2025, 3, 8)

    def test_end_before_start_fails(self):
        with pytest.raises(ValidationError, match="end.*after.*start"):
            TimeWindow(
                start=datetime(2025, 3, 8),
                end=datetime(2025, 3, 1),
            )

    def test_end_equals_start_fails(self):
        with pytest.raises(ValidationError, match="end.*after.*start"):
            TimeWindow(
                start=datetime(2025, 3, 1),
                end=datetime(2025, 3, 1),
            )

    def test_serialization_roundtrip(self):
        tw = TimeWindow(
            start=datetime(2025, 3, 1),
            end=datetime(2025, 3, 8),
        )
        dumped = tw.model_dump()
        assert "start" in dumped
        assert "end" in dumped
        # Should be able to reconstruct
        tw2 = TimeWindow(**dumped)
        assert tw2.start == tw.start
        assert tw2.end == tw.end


# ---------------------------------------------------------------------------
# KPIResult
# ---------------------------------------------------------------------------

class TestKPIResult:
    """Test KPIResult serialisation and field defaults."""

    def test_basic_serialization(self):
        result = KPIResult(
            kpi_name="Data Loss Rate",
            value=0.05,
            unit="%",
            pillar="mimir",
            environment="PROD",
        )
        dumped = result.model_dump()
        assert dumped["kpi_name"] == "Data Loss Rate"
        assert dumped["value"] == 0.05
        assert dumped["unit"] == "%"
        assert dumped["pillar"] == "mimir"
        assert dumped["environment"] == "PROD"
        assert dumped["time_windows"] == []
        assert dumped["details"] == {}

    def test_with_details(self):
        result = KPIResult(
            kpi_name="Uptime",
            value=99.95,
            unit="%",
            pillar="loki",
            environment="PROD",
            details={"breakdown": [1, 2, 3]},
        )
        assert result.details == {"breakdown": [1, 2, 3]}

    def test_with_time_windows(self):
        result = KPIResult(
            kpi_name="Cost per GB",
            value=150.0,
            unit="$/GB",
            pillar="mimir",
            environment="PROD",
            time_windows=[
                TimeWindow(start=datetime(2025, 3, 1), end=datetime(2025, 3, 8)),
            ],
        )
        assert len(result.time_windows) == 1

    def test_json_roundtrip(self):
        result = KPIResult(
            kpi_name="Data Loss Rate",
            value=1.5,
            unit="%",
            pillar="tempo",
            environment="PERF",
        )
        json_str = result.model_dump_json()
        restored = KPIResult.model_validate_json(json_str)
        assert restored.kpi_name == result.kpi_name
        assert restored.value == result.value
        assert restored.pillar == result.pillar
