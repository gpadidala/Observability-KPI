"""Tests for the ReportGenerator (JSON, CSV, PDF output formats).

Uses sample report data structures matching the shape produced by
``ReportResponse.model_dump()``.
"""

from __future__ import annotations

import csv
import io
import json

import pytest

from reports.generator import ReportGenerator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def generator() -> ReportGenerator:
    return ReportGenerator()


@pytest.fixture
def sample_report_data() -> dict:
    """Minimal valid report data matching ReportResponse structure."""
    return {
        "environment": "PROD",
        "time_range": {
            "start": "2025-03-01T00:00:00",
            "end": "2025-03-08T00:00:00",
        },
        "effective_query_windows": [
            {
                "start": "2025-03-01T00:00:00",
                "end": "2025-03-08T00:00:00",
            }
        ],
        "kpis": [
            {
                "pillar": "mimir",
                "kpis": [
                    {
                        "kpi_name": "Data Loss Rate",
                        "value": 0.05,
                        "unit": "%",
                        "pillar": "mimir",
                        "environment": "PROD",
                        "time_windows": [],
                        "details": {},
                    },
                    {
                        "kpi_name": "Cost per GB Ingested",
                        "value": 150.0,
                        "unit": "$/GB",
                        "pillar": "mimir",
                        "environment": "PROD",
                        "time_windows": [],
                        "details": {},
                    },
                ],
            },
            {
                "pillar": "loki",
                "kpis": [
                    {
                        "kpi_name": "Uptime",
                        "value": 99.95,
                        "unit": "%",
                        "pillar": "loki",
                        "environment": "PROD",
                        "time_windows": [],
                        "details": {},
                    },
                ],
            },
        ],
        "generated_at": "2025-03-08T12:00:00",
    }


@pytest.fixture
def empty_report_data() -> dict:
    """Report data with no KPI results."""
    return {
        "environment": "PERF",
        "time_range": {
            "start": "2025-03-01T00:00:00",
            "end": "2025-03-08T00:00:00",
        },
        "effective_query_windows": [],
        "kpis": [],
        "generated_at": "2025-03-08T12:00:00",
    }


# ---------------------------------------------------------------------------
# JSON generation
# ---------------------------------------------------------------------------

class TestJSONGeneration:
    """Test JSON report output."""

    def test_valid_json_output(self, generator: ReportGenerator, sample_report_data: dict):
        file_bytes, content_type, filename = generator.generate(sample_report_data, "json")

        assert content_type == "application/json"
        assert isinstance(file_bytes, bytes)
        assert len(file_bytes) > 0

        # Must parse as valid JSON
        parsed = json.loads(file_bytes.decode("utf-8"))
        assert isinstance(parsed, dict)

    def test_json_contains_environment(self, generator: ReportGenerator, sample_report_data: dict):
        file_bytes, _, _ = generator.generate(sample_report_data, "json")
        parsed = json.loads(file_bytes.decode("utf-8"))
        assert parsed["environment"] == "PROD"

    def test_json_contains_kpis(self, generator: ReportGenerator, sample_report_data: dict):
        file_bytes, _, _ = generator.generate(sample_report_data, "json")
        parsed = json.loads(file_bytes.decode("utf-8"))
        assert "kpis" in parsed
        assert len(parsed["kpis"]) == 2  # mimir + loki

    def test_json_filename_format(self, generator: ReportGenerator, sample_report_data: dict):
        _, _, filename = generator.generate(sample_report_data, "json")
        assert filename.startswith("observability_kpi_report_PROD_")
        assert filename.endswith(".json")

    def test_json_empty_kpis(self, generator: ReportGenerator, empty_report_data: dict):
        file_bytes, content_type, filename = generator.generate(empty_report_data, "json")
        parsed = json.loads(file_bytes.decode("utf-8"))
        assert parsed["kpis"] == []
        assert content_type == "application/json"


# ---------------------------------------------------------------------------
# CSV generation
# ---------------------------------------------------------------------------

class TestCSVGeneration:
    """Test CSV report output."""

    def test_valid_csv_output(self, generator: ReportGenerator, sample_report_data: dict):
        file_bytes, content_type, filename = generator.generate(sample_report_data, "csv")

        assert content_type == "text/csv"
        assert isinstance(file_bytes, bytes)
        assert len(file_bytes) > 0

    def test_csv_headers(self, generator: ReportGenerator, sample_report_data: dict):
        file_bytes, _, _ = generator.generate(sample_report_data, "csv")
        text = file_bytes.decode("utf-8")
        reader = csv.reader(io.StringIO(text))
        headers = next(reader)

        assert "Environment" in headers
        assert "Pillar" in headers
        assert "KPI Name" in headers
        assert "Value" in headers
        assert "Unit" in headers

    def test_csv_row_count(self, generator: ReportGenerator, sample_report_data: dict):
        """3 KPIs across 2 pillars = 3 data rows + 1 header = 4 rows total."""
        file_bytes, _, _ = generator.generate(sample_report_data, "csv")
        text = file_bytes.decode("utf-8")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        # 1 header + 3 data rows (2 mimir KPIs + 1 loki KPI)
        assert len(rows) == 4

    def test_csv_filename_format(self, generator: ReportGenerator, sample_report_data: dict):
        _, _, filename = generator.generate(sample_report_data, "csv")
        assert filename.startswith("observability_kpi_report_PROD_")
        assert filename.endswith(".csv")

    def test_csv_empty_kpis(self, generator: ReportGenerator, empty_report_data: dict):
        """Empty KPI list should produce a sentinel row."""
        file_bytes, _, _ = generator.generate(empty_report_data, "csv")
        text = file_bytes.decode("utf-8")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        # Header + 1 sentinel row
        assert len(rows) == 2
        assert "No KPI data available" in rows[1][2]


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

class TestPDFGeneration:
    """Test PDF report output."""

    def test_produces_non_empty_bytes(self, generator: ReportGenerator, sample_report_data: dict):
        file_bytes, content_type, filename = generator.generate(sample_report_data, "pdf")

        assert content_type == "application/pdf"
        assert isinstance(file_bytes, bytes)
        assert len(file_bytes) > 0

    def test_pdf_starts_with_magic_bytes(self, generator: ReportGenerator, sample_report_data: dict):
        """A valid PDF starts with '%PDF'."""
        file_bytes, _, _ = generator.generate(sample_report_data, "pdf")
        assert file_bytes[:4] == b"%PDF"

    def test_pdf_filename_format(self, generator: ReportGenerator, sample_report_data: dict):
        _, _, filename = generator.generate(sample_report_data, "pdf")
        assert filename.startswith("observability_kpi_report_PROD_")
        assert filename.endswith(".pdf")

    def test_pdf_empty_kpis(self, generator: ReportGenerator, empty_report_data: dict):
        """PDF generation should not crash on empty KPI data."""
        file_bytes, content_type, _ = generator.generate(empty_report_data, "pdf")
        assert content_type == "application/pdf"
        assert len(file_bytes) > 0


# ---------------------------------------------------------------------------
# Invalid format
# ---------------------------------------------------------------------------

class TestInvalidFormat:
    """Test that unsupported formats are rejected."""

    def test_raises_value_error(self, generator: ReportGenerator, sample_report_data: dict):
        with pytest.raises(ValueError, match="Unsupported report format"):
            generator.generate(sample_report_data, "xlsx")

    def test_raises_for_empty_string(self, generator: ReportGenerator, sample_report_data: dict):
        with pytest.raises(ValueError, match="Unsupported report format"):
            generator.generate(sample_report_data, "")

    def test_case_insensitive_format(self, generator: ReportGenerator, sample_report_data: dict):
        """JSON, Json, JSON should all work."""
        for fmt in ["JSON", "Json", "  json  "]:
            file_bytes, content_type, _ = generator.generate(sample_report_data, fmt)
            assert content_type == "application/json"


# ---------------------------------------------------------------------------
# Filename consistency
# ---------------------------------------------------------------------------

class TestFilenameFormat:
    """Verify filename conventions across formats."""

    @pytest.mark.parametrize("fmt,ext", [("json", ".json"), ("csv", ".csv"), ("pdf", ".pdf")])
    def test_filename_contains_env_and_extension(
        self, generator: ReportGenerator, sample_report_data: dict, fmt: str, ext: str
    ):
        _, _, filename = generator.generate(sample_report_data, fmt)
        assert "PROD" in filename
        assert filename.endswith(ext)
        assert filename.startswith("observability_kpi_report_")
