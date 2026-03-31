"""Report Generator for the Observability KPI Reporting Application.

Generates leadership-ready reports in PDF, CSV, and JSON formats from
computed KPI data.  Each format preserves full fidelity of the underlying
data while optimising for its intended audience:

- **JSON** -- machine-readable, ideal for downstream automation.
- **CSV**  -- flat tabular view, suitable for spreadsheet analysis.
- **PDF**  -- professionally formatted document for executive review.
"""

from __future__ import annotations

import io
import csv
import json
import logging
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PILLAR_DISPLAY_NAMES: dict[str, str] = {
    "mimir": "Mimir (Metrics)",
    "loki": "Loki (Logs)",
    "tempo": "Tempo (Traces)",
    "pyroscope": "Pyroscope (Profiles)",
    "grafana": "Grafana UI",
}

_PILLAR_ORDER: list[str] = ["mimir", "loki", "tempo", "pyroscope", "grafana"]

# Colour palette -- professional, company-neutral blues/greys
_COLOR_PRIMARY = colors.HexColor("#1A3A5C")
_COLOR_SECONDARY = colors.HexColor("#2E6EA6")
_COLOR_HEADER_BG = colors.HexColor("#1A3A5C")
_COLOR_HEADER_TEXT = colors.white
_COLOR_ROW_EVEN = colors.HexColor("#F2F6FA")
_COLOR_ROW_ODD = colors.white
_COLOR_SECTION_BG = colors.HexColor("#E8EEF4")
_COLOR_BORDER = colors.HexColor("#B0BEC5")
_COLOR_ACCENT = colors.HexColor("#00897B")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_pct(value: float | None) -> str:
    """Format a numeric value as a percentage string with two decimal places."""
    if value is None:
        return "N/A"
    return f"{value:.2f}%"


def _fmt_currency(value: float | None) -> str:
    """Format a numeric value as a USD currency string with commas."""
    if value is None:
        return "N/A"
    return f"${value:,.2f}"


def _fmt_number(value: float | None, unit: str = "") -> str:
    """Format a numeric value with appropriate precision based on its unit."""
    if value is None:
        return "N/A"
    unit_lower = unit.lower().strip()
    if unit_lower in ("%", "percent", "percentage"):
        return _fmt_pct(value)
    if unit_lower in ("$", "usd", "$/gb", "cost"):
        return _fmt_currency(value)
    if unit_lower in ("ms", "milliseconds"):
        return f"{value:,.2f} ms"
    if unit_lower in ("s", "seconds"):
        return f"{value:,.2f} s"
    if unit_lower in ("req/s", "requests/s"):
        return f"{value:,.2f} req/s"
    if unit_lower in ("gb", "mb", "tb", "kb"):
        return f"{value:,.2f} {unit}"
    # Fallback: use two decimal places for floats, integer display for whole numbers
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,.2f}"


def _safe_get_kpis(report_data: dict) -> list[dict]:
    """Safely extract the list of PillarKPIs dicts from report_data."""
    kpis = report_data.get("kpis", [])
    if kpis is None:
        return []
    return list(kpis)


def _safe_get_pillar_kpis(pillar_data: dict) -> list[dict]:
    """Safely extract the list of KPIResult dicts from a PillarKPIs dict."""
    kpis = pillar_data.get("kpis", [])
    if kpis is None:
        return []
    return list(kpis)


def _generate_timestamp_slug() -> str:
    """Return a filesystem-safe timestamp string for filenames."""
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def _get_env_label(report_data: dict) -> str:
    """Extract the environment label, defaulting to 'UNKNOWN'."""
    return report_data.get("environment", "UNKNOWN").upper()


def _get_time_range(report_data: dict) -> dict[str, str]:
    """Extract the time_range dict, defaulting to empty strings."""
    tr = report_data.get("time_range", {})
    if tr is None:
        tr = {}
    return {
        "start": tr.get("start", "N/A"),
        "end": tr.get("end", "N/A"),
    }


def _get_effective_query_windows(report_data: dict) -> list[dict]:
    """Extract the effective_query_windows list."""
    windows = report_data.get("effective_query_windows", [])
    if windows is None:
        return []
    return list(windows)


def _find_kpi_by_name(kpis: list[dict], name_fragment: str) -> dict | None:
    """Find a KPI whose name contains the given fragment (case-insensitive)."""
    name_fragment_lower = name_fragment.lower()
    for kpi in kpis:
        kpi_name = kpi.get("kpi_name", "")
        if name_fragment_lower in kpi_name.lower():
            return kpi
    return None


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class ReportGenerator:
    """Generates leadership-ready Observability KPI reports in multiple formats.

    Supported formats: ``pdf``, ``csv``, ``json``.

    Usage::

        generator = ReportGenerator()
        file_bytes, content_type, filename = generator.generate(report_data, "pdf")
    """

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def generate(
        self,
        report_data: dict,
        format: str,  # noqa: A002  (shadows builtin deliberately for API clarity)
    ) -> tuple[bytes, str, str]:
        """Generate a report in the requested format.

        Parameters
        ----------
        report_data : dict
            Full report payload as produced by ``ReportResponse.model_dump()``.
            Expected top-level keys: ``environment``, ``time_range``,
            ``effective_query_windows``, ``kpis``, and optionally
            ``generated_at``.
        format : str
            One of ``"pdf"``, ``"csv"``, ``"json"``.

        Returns
        -------
        tuple[bytes, str, str]
            ``(file_bytes, content_type, filename)``

        Raises
        ------
        ValueError
            If *format* is not one of the supported values.
        """
        fmt = format.strip().lower()
        if fmt == "json":
            return self._generate_json(report_data)
        if fmt == "csv":
            return self._generate_csv(report_data)
        if fmt == "pdf":
            return self._generate_pdf(report_data)
        raise ValueError(
            f"Unsupported report format '{format}'. "
            f"Supported formats: pdf, csv, json"
        )

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def _generate_json(self, report_data: dict) -> tuple[bytes, str, str]:
        """Generate a pretty-printed JSON report with full KPI data.

        Returns
        -------
        tuple[bytes, str, str]
            ``(file_bytes, "application/json", filename)``
        """
        env = _get_env_label(report_data)
        ts = _generate_timestamp_slug()
        filename = f"observability_kpi_report_{env}_{ts}.json"

        payload = json.dumps(
            report_data, indent=2, default=str, ensure_ascii=False
        )
        return payload.encode("utf-8"), "application/json", filename

    # ------------------------------------------------------------------
    # CSV
    # ------------------------------------------------------------------

    def _generate_csv(self, report_data: dict) -> tuple[bytes, str, str]:
        """Generate a flat CSV report with one row per KPI per pillar.

        Columns
        -------
        Environment, Pillar, KPI Name, Value, Unit, Time Range Start,
        Time Range End, Query Windows Used

        Returns
        -------
        tuple[bytes, str, str]
            ``(file_bytes, "text/csv", filename)``
        """
        env = _get_env_label(report_data)
        ts = _generate_timestamp_slug()
        filename = f"observability_kpi_report_{env}_{ts}.csv"

        time_range = _get_time_range(report_data)
        effective_windows = _get_effective_query_windows(report_data)
        num_windows = len(effective_windows)

        buf = io.StringIO()
        writer = csv.writer(buf)

        # Header row
        writer.writerow([
            "Environment",
            "Pillar",
            "KPI Name",
            "Value",
            "Unit",
            "Time Range Start",
            "Time Range End",
            "Query Windows Used",
        ])

        pillar_kpis_list = _safe_get_kpis(report_data)

        if not pillar_kpis_list:
            # Write a single sentinel row so consumers know the report was empty
            writer.writerow([
                env,
                "N/A",
                "No KPI data available",
                "",
                "",
                time_range["start"],
                time_range["end"],
                num_windows,
            ])
        else:
            for pillar_data in pillar_kpis_list:
                pillar_name = pillar_data.get("pillar", "unknown")
                display_name = _PILLAR_DISPLAY_NAMES.get(
                    pillar_name.lower(), pillar_name
                )
                kpis = _safe_get_pillar_kpis(pillar_data)

                if not kpis:
                    writer.writerow([
                        env,
                        display_name,
                        "No KPIs computed",
                        "",
                        "",
                        time_range["start"],
                        time_range["end"],
                        num_windows,
                    ])
                    continue

                for kpi in kpis:
                    value = kpi.get("value")
                    unit = kpi.get("unit", "")
                    writer.writerow([
                        env,
                        display_name,
                        kpi.get("kpi_name", "Unnamed KPI"),
                        value if value is not None else "",
                        unit,
                        time_range["start"],
                        time_range["end"],
                        num_windows,
                    ])

        csv_bytes = buf.getvalue().encode("utf-8")
        return csv_bytes, "text/csv", filename

    # ------------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------------

    def _generate_pdf(self, report_data: dict) -> tuple[bytes, str, str]:
        """Generate a professionally formatted PDF report.

        The PDF contains:

        1. Title page (environment, timestamp, time range)
        2. Executive summary (availability, data loss, cost/GB, highlights)
        3. Query transparency section (windows used)
        4. Per-pillar KPI tables (Mimir, Loki, Tempo, Pyroscope, Grafana)
        5. Cost breakdown section
        6. Page numbers in the footer

        Returns
        -------
        tuple[bytes, str, str]
            ``(file_bytes, "application/pdf", filename)``
        """
        env = _get_env_label(report_data)
        ts = _generate_timestamp_slug()
        filename = f"observability_kpi_report_{env}_{ts}.pdf"

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=letter,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            rightMargin=0.75 * inch,
            title="Observability KPI Report",
            author="Observability KPI Reporting Platform",
        )

        styles = self._build_pdf_styles()
        story: list[Any] = []

        # -- 1. Title page ------------------------------------------------
        self._add_title_page(story, styles, report_data)

        # -- 2. Executive summary -----------------------------------------
        self._add_executive_summary(story, styles, report_data)

        # -- 3. Query transparency ----------------------------------------
        self._add_query_transparency(story, styles, report_data)

        # -- 4. Per-pillar KPI tables -------------------------------------
        self._add_pillar_tables(story, styles, report_data)

        # -- 5. Cost breakdown --------------------------------------------
        self._add_cost_breakdown(story, styles, report_data)

        # Build the PDF with page-number footers
        doc.build(story, onFirstPage=self._page_footer, onLaterPages=self._page_footer)

        pdf_bytes = buf.getvalue()
        buf.close()
        return pdf_bytes, "application/pdf", filename

    # ------------------------------------------------------------------
    # PDF style helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_pdf_styles() -> dict[str, ParagraphStyle]:
        """Create the paragraph style dictionary used throughout the PDF."""
        base = getSampleStyleSheet()

        custom: dict[str, ParagraphStyle] = {}

        custom["Title"] = ParagraphStyle(
            "CustomTitle",
            parent=base["Title"],
            fontSize=28,
            leading=34,
            textColor=_COLOR_PRIMARY,
            spaceAfter=6,
            alignment=TA_CENTER,
        )
        custom["Subtitle"] = ParagraphStyle(
            "CustomSubtitle",
            parent=base["Title"],
            fontSize=16,
            leading=20,
            textColor=_COLOR_SECONDARY,
            spaceAfter=4,
            alignment=TA_CENTER,
        )
        custom["SectionHeader"] = ParagraphStyle(
            "SectionHeader",
            parent=base["Heading1"],
            fontSize=18,
            leading=22,
            textColor=_COLOR_PRIMARY,
            spaceBefore=20,
            spaceAfter=10,
            borderWidth=0,
            borderPadding=0,
        )
        custom["SubSectionHeader"] = ParagraphStyle(
            "SubSectionHeader",
            parent=base["Heading2"],
            fontSize=14,
            leading=18,
            textColor=_COLOR_SECONDARY,
            spaceBefore=14,
            spaceAfter=6,
        )
        custom["Body"] = ParagraphStyle(
            "CustomBody",
            parent=base["Normal"],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#333333"),
            spaceAfter=4,
        )
        custom["BodyBold"] = ParagraphStyle(
            "BodyBold",
            parent=base["Normal"],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#333333"),
            spaceAfter=4,
            fontName="Helvetica-Bold",
        )
        custom["Small"] = ParagraphStyle(
            "Small",
            parent=base["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#666666"),
        )
        custom["HighlightGreen"] = ParagraphStyle(
            "HighlightGreen",
            parent=base["Normal"],
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#2E7D32"),
            fontName="Helvetica-Bold",
        )
        custom["HighlightRed"] = ParagraphStyle(
            "HighlightRed",
            parent=base["Normal"],
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#C62828"),
            fontName="Helvetica-Bold",
        )
        custom["MetricValue"] = ParagraphStyle(
            "MetricValue",
            parent=base["Normal"],
            fontSize=22,
            leading=26,
            textColor=_COLOR_PRIMARY,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
        )
        custom["MetricLabel"] = ParagraphStyle(
            "MetricLabel",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#666666"),
            alignment=TA_CENTER,
        )
        custom["Footer"] = ParagraphStyle(
            "Footer",
            parent=base["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#999999"),
            alignment=TA_CENTER,
        )

        return custom

    # ------------------------------------------------------------------
    # PDF page footer
    # ------------------------------------------------------------------

    @staticmethod
    def _page_footer(canvas: Any, doc: Any) -> None:
        """Draw footer with page number on every page."""
        canvas.saveState()

        page_num = canvas.getPageNumber()
        page_width = doc.pagesize[0]

        # Thin horizontal rule above footer
        y_line = 0.55 * inch
        canvas.setStrokeColor(_COLOR_BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(
            doc.leftMargin,
            y_line,
            page_width - doc.rightMargin,
            y_line,
        )

        # Page number -- centred
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#999999"))
        canvas.drawCentredString(
            page_width / 2,
            0.4 * inch,
            f"Page {page_num}",
        )

        # Report label -- left
        canvas.drawString(
            doc.leftMargin,
            0.4 * inch,
            "Observability KPI Report",
        )

        # Timestamp -- right
        canvas.drawRightString(
            page_width - doc.rightMargin,
            0.4 * inch,
            datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        )

        canvas.restoreState()

    # ------------------------------------------------------------------
    # PDF section builders
    # ------------------------------------------------------------------

    def _add_title_page(
        self, story: list, styles: dict, report_data: dict
    ) -> None:
        """Add the title page to the PDF story."""
        env = _get_env_label(report_data)
        time_range = _get_time_range(report_data)
        generated_at = report_data.get("generated_at", datetime.utcnow().isoformat())

        # Vertical spacing to push title towards centre
        story.append(Spacer(1, 1.5 * inch))

        # Title
        story.append(Paragraph("Observability KPI Report", styles["Title"]))
        story.append(Spacer(1, 0.15 * inch))

        # Horizontal rule under title
        rule_data = [["" ]]
        rule_table = Table(rule_data, colWidths=[5 * inch])
        rule_table.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 2, _COLOR_SECONDARY),
        ]))
        # Centre the rule
        story.append(rule_table)
        story.append(Spacer(1, 0.3 * inch))

        # Environment badge
        env_style = ParagraphStyle(
            "EnvBadge",
            parent=styles["Subtitle"],
            fontSize=20,
            textColor=_COLOR_ACCENT,
            fontName="Helvetica-Bold",
        )
        story.append(
            Paragraph(f"Environment: {env}", env_style)
        )
        story.append(Spacer(1, 0.25 * inch))

        # Time range
        story.append(
            Paragraph(
                f"Report Period: {time_range['start']}  to  {time_range['end']}",
                styles["Subtitle"],
            )
        )
        story.append(Spacer(1, 0.15 * inch))

        # Generation timestamp
        if isinstance(generated_at, str):
            gen_display = generated_at
        else:
            gen_display = str(generated_at)
        story.append(
            Paragraph(
                f"Generated: {gen_display}",
                styles["Subtitle"],
            )
        )

        story.append(Spacer(1, 1.0 * inch))

        # Confidentiality notice
        notice_style = ParagraphStyle(
            "Notice",
            parent=styles["Small"],
            alignment=TA_CENTER,
            textColor=colors.HexColor("#999999"),
            fontSize=9,
        )
        story.append(
            Paragraph(
                "This report is generated automatically by the Observability KPI "
                "Reporting Platform. Data is sourced from Grafana Cloud datasources "
                "and may be subject to platform query-window limitations.",
                notice_style,
            )
        )

        story.append(PageBreak())

    def _add_executive_summary(
        self, story: list, styles: dict, report_data: dict
    ) -> None:
        """Add the executive summary section."""
        story.append(Paragraph("Executive Summary", styles["SectionHeader"]))

        # Gather summary KPIs from all pillars
        all_kpis = self._flatten_kpis(report_data)
        availability_kpi = _find_kpi_by_name(all_kpis, "availability")
        data_loss_kpi = _find_kpi_by_name(all_kpis, "data loss")
        cost_per_gb_kpi = _find_kpi_by_name(all_kpis, "cost per gb")

        # Summary metrics cards as a table
        cards: list[list[Any]] = []
        card_labels: list[list[Any]] = []

        if availability_kpi:
            cards.append(Paragraph(
                _fmt_pct(availability_kpi.get("value")),
                styles["MetricValue"],
            ))
            card_labels.append(Paragraph(
                "Overall Platform Availability", styles["MetricLabel"]
            ))
        else:
            cards.append(Paragraph("N/A", styles["MetricValue"]))
            card_labels.append(Paragraph(
                "Overall Platform Availability", styles["MetricLabel"]
            ))

        if data_loss_kpi:
            cards.append(Paragraph(
                _fmt_pct(data_loss_kpi.get("value")),
                styles["MetricValue"],
            ))
            card_labels.append(Paragraph(
                "Overall Data Loss Rate", styles["MetricLabel"]
            ))
        else:
            cards.append(Paragraph("N/A", styles["MetricValue"]))
            card_labels.append(Paragraph(
                "Overall Data Loss Rate", styles["MetricLabel"]
            ))

        if cost_per_gb_kpi:
            cards.append(Paragraph(
                _fmt_currency(cost_per_gb_kpi.get("value")),
                styles["MetricValue"],
            ))
            card_labels.append(Paragraph(
                "Total Cost per GB", styles["MetricLabel"]
            ))
        else:
            cards.append(Paragraph("N/A", styles["MetricValue"]))
            card_labels.append(Paragraph(
                "Total Cost per GB", styles["MetricLabel"]
            ))

        # Build metric cards table (3 columns)
        card_table_data = [cards, card_labels]
        col_width = 2.2 * inch
        card_table = Table(card_table_data, colWidths=[col_width] * 3)
        card_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (0, -1), 1, _COLOR_BORDER),
            ("BOX", (1, 0), (1, -1), 1, _COLOR_BORDER),
            ("BOX", (2, 0), (2, -1), 1, _COLOR_BORDER),
            ("TOPPADDING", (0, 0), (-1, 0), 12),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 12),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FAFBFC")),
        ]))
        story.append(card_table)
        story.append(Spacer(1, 0.25 * inch))

        # Key highlights
        story.append(
            Paragraph("Key Highlights", styles["SubSectionHeader"])
        )
        highlights = self._compute_highlights(all_kpis)
        if highlights:
            for highlight in highlights:
                story.append(Paragraph(f"\u2022  {highlight}", styles["Body"]))
        else:
            story.append(
                Paragraph(
                    "No KPI data is available for this report period.",
                    styles["Body"],
                )
            )

        story.append(Spacer(1, 0.3 * inch))

    def _add_query_transparency(
        self, story: list, styles: dict, report_data: dict
    ) -> None:
        """Add the query transparency section showing time windows used."""
        story.append(
            Paragraph("Query Transparency", styles["SectionHeader"])
        )

        time_range = _get_time_range(report_data)
        effective_windows = _get_effective_query_windows(report_data)

        story.append(
            Paragraph(
                f"<b>Selected Time Range:</b>  {time_range['start']}  to  "
                f"{time_range['end']}",
                styles["Body"],
            )
        )
        story.append(
            Paragraph(
                f"<b>Number of Query Windows Used:</b>  {len(effective_windows)}",
                styles["Body"],
            )
        )
        story.append(Spacer(1, 0.1 * inch))

        if effective_windows:
            story.append(
                Paragraph(
                    "Effective Query Windows",
                    styles["SubSectionHeader"],
                )
            )

            header = ["#", "Start", "End", "Duration (days)"]
            rows = [header]
            for idx, window in enumerate(effective_windows, start=1):
                w_start = window.get("start", "N/A")
                w_end = window.get("end", "N/A")
                duration = window.get("duration_days", "N/A")
                if isinstance(duration, (int, float)):
                    duration = f"{duration:.1f}"
                rows.append([str(idx), str(w_start), str(w_end), str(duration)])

            col_widths = [0.5 * inch, 2.5 * inch, 2.5 * inch, 1.2 * inch]
            table = Table(rows, colWidths=col_widths, repeatRows=1)
            table.setStyle(self._standard_table_style(len(rows)))
            story.append(table)
        else:
            story.append(
                Paragraph(
                    "No effective query window information is available.",
                    styles["Body"],
                )
            )

        story.append(Spacer(1, 0.3 * inch))

    def _add_pillar_tables(
        self, story: list, styles: dict, report_data: dict
    ) -> None:
        """Add per-pillar KPI tables (one sub-section per pillar)."""
        story.append(PageBreak())
        story.append(
            Paragraph("KPI Results by Pillar", styles["SectionHeader"])
        )

        pillar_kpis_list = _safe_get_kpis(report_data)

        # Build a lookup: pillar_name_lower -> pillar_data
        pillar_lookup: dict[str, dict] = {}
        for pillar_data in pillar_kpis_list:
            p_name = pillar_data.get("pillar", "unknown").lower()
            pillar_lookup[p_name] = pillar_data

        for pillar_key in _PILLAR_ORDER:
            display_name = _PILLAR_DISPLAY_NAMES.get(pillar_key, pillar_key)
            story.append(
                Paragraph(display_name, styles["SubSectionHeader"])
            )

            pillar_data = pillar_lookup.get(pillar_key)
            if pillar_data is None:
                story.append(
                    Paragraph(
                        "No data available for this pillar.",
                        styles["Body"],
                    )
                )
                story.append(Spacer(1, 0.15 * inch))
                continue

            kpis = _safe_get_pillar_kpis(pillar_data)
            if not kpis:
                story.append(
                    Paragraph(
                        "No KPIs computed for this pillar.",
                        styles["Body"],
                    )
                )
                story.append(Spacer(1, 0.15 * inch))
                continue

            header = ["KPI Name", "Value", "Unit"]
            rows = [header]
            for kpi in kpis:
                kpi_name = kpi.get("kpi_name", "Unnamed KPI")
                value = kpi.get("value")
                unit = kpi.get("unit", "")
                formatted_value = _fmt_number(value, unit)
                rows.append([kpi_name, formatted_value, unit])

            col_widths = [3.0 * inch, 2.2 * inch, 1.5 * inch]
            table = Table(rows, colWidths=col_widths, repeatRows=1)
            table.setStyle(self._standard_table_style(len(rows)))
            story.append(table)
            story.append(Spacer(1, 0.25 * inch))

        # Include any extra pillars not in the predefined order
        extra_pillars = set(pillar_lookup.keys()) - set(_PILLAR_ORDER)
        for pillar_key in sorted(extra_pillars):
            pillar_data = pillar_lookup[pillar_key]
            display_name = _PILLAR_DISPLAY_NAMES.get(pillar_key, pillar_key.title())
            story.append(
                Paragraph(display_name, styles["SubSectionHeader"])
            )

            kpis = _safe_get_pillar_kpis(pillar_data)
            if not kpis:
                story.append(
                    Paragraph(
                        "No KPIs computed for this pillar.",
                        styles["Body"],
                    )
                )
                story.append(Spacer(1, 0.15 * inch))
                continue

            header = ["KPI Name", "Value", "Unit"]
            rows = [header]
            for kpi in kpis:
                kpi_name = kpi.get("kpi_name", "Unnamed KPI")
                value = kpi.get("value")
                unit = kpi.get("unit", "")
                formatted_value = _fmt_number(value, unit)
                rows.append([kpi_name, formatted_value, unit])

            col_widths = [3.0 * inch, 2.2 * inch, 1.5 * inch]
            table = Table(rows, colWidths=col_widths, repeatRows=1)
            table.setStyle(self._standard_table_style(len(rows)))
            story.append(table)
            story.append(Spacer(1, 0.25 * inch))

    def _add_cost_breakdown(
        self, story: list, styles: dict, report_data: dict
    ) -> None:
        """Add the cost breakdown section with per-pillar costs."""
        story.append(PageBreak())
        story.append(
            Paragraph("Cost Breakdown", styles["SectionHeader"])
        )

        # Collect cost KPIs from all pillars
        pillar_kpis_list = _safe_get_kpis(report_data)
        cost_rows: list[dict[str, Any]] = []
        total_cost: float = 0.0

        for pillar_data in pillar_kpis_list:
            pillar_name = pillar_data.get("pillar", "unknown")
            display_name = _PILLAR_DISPLAY_NAMES.get(
                pillar_name.lower(), pillar_name.title()
            )
            kpis = _safe_get_pillar_kpis(pillar_data)

            # Look for cost-related KPIs
            pillar_cost: float = 0.0
            for kpi in kpis:
                kpi_name = kpi.get("kpi_name", "").lower()
                unit = kpi.get("unit", "").lower()
                value = kpi.get("value")
                if value is None:
                    continue
                # Match cost KPIs by name or unit
                if any(
                    keyword in kpi_name
                    for keyword in ("cost", "spend", "billing", "expense")
                ) or unit in ("$", "usd"):
                    pillar_cost += value

            cost_rows.append({
                "pillar": display_name,
                "cost": pillar_cost,
            })
            total_cost += pillar_cost

        if not cost_rows or total_cost == 0:
            story.append(
                Paragraph(
                    "No cost data is available for this report period.",
                    styles["Body"],
                )
            )
            return

        # Build cost breakdown table
        header = ["Pillar", "Monthly Cost", "Percentage"]
        rows = [header]
        for row in cost_rows:
            pct = (row["cost"] / total_cost * 100) if total_cost > 0 else 0.0
            rows.append([
                row["pillar"],
                _fmt_currency(row["cost"]),
                _fmt_pct(pct),
            ])

        # Total row
        rows.append([
            "TOTAL",
            _fmt_currency(total_cost),
            "100.00%",
        ])

        col_widths = [3.0 * inch, 2.0 * inch, 1.7 * inch]
        table = Table(rows, colWidths=col_widths, repeatRows=1)

        # Extended style with a bold total row
        num_rows = len(rows)
        style_commands = self._standard_table_style_commands(num_rows)
        # Bold total row
        style_commands.extend([
            ("FONTNAME", (0, num_rows - 1), (-1, num_rows - 1), "Helvetica-Bold"),
            ("LINEABOVE", (0, num_rows - 1), (-1, num_rows - 1), 1.5, _COLOR_PRIMARY),
            ("BACKGROUND", (0, num_rows - 1), (-1, num_rows - 1), _COLOR_SECTION_BG),
        ])
        table.setStyle(TableStyle(style_commands))

        story.append(table)
        story.append(Spacer(1, 0.2 * inch))

        # Total monthly cost callout
        story.append(
            Paragraph(
                f"<b>Total Estimated Monthly Cost:</b>  {_fmt_currency(total_cost)}",
                styles["Body"],
            )
        )

    # ------------------------------------------------------------------
    # PDF table style helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _standard_table_style_commands(num_rows: int) -> list:
        """Return a list of TableStyle commands for a professional-looking table.

        Parameters
        ----------
        num_rows : int
            Total number of rows including the header row.
        """
        commands: list = [
            # Header styling
            ("BACKGROUND", (0, 0), (-1, 0), _COLOR_HEADER_BG),
            ("TEXTCOLOR", (0, 0), (-1, 0), _COLOR_HEADER_TEXT),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
            # Body styling
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("TOPPADDING", (0, 1), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
            # Grid
            ("GRID", (0, 0), (-1, -1), 0.5, _COLOR_BORDER),
            # Alignment
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("ALIGN", (0, 1), (0, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]

        # Alternating row colours for data rows
        for row_idx in range(1, num_rows):
            bg = _COLOR_ROW_EVEN if row_idx % 2 == 0 else _COLOR_ROW_ODD
            commands.append(
                ("BACKGROUND", (0, row_idx), (-1, row_idx), bg)
            )

        return commands

    def _standard_table_style(self, num_rows: int) -> TableStyle:
        """Return a ``TableStyle`` with professional formatting."""
        return TableStyle(self._standard_table_style_commands(num_rows))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _flatten_kpis(report_data: dict) -> list[dict]:
        """Flatten all KPIs across all pillars into a single list."""
        all_kpis: list[dict] = []
        for pillar_data in _safe_get_kpis(report_data):
            for kpi in _safe_get_pillar_kpis(pillar_data):
                all_kpis.append(kpi)
        return all_kpis

    @staticmethod
    def _compute_highlights(all_kpis: list[dict]) -> list[str]:
        """Derive key highlight bullet points from the KPI data."""
        highlights: list[str] = []

        if not all_kpis:
            return highlights

        # Availability highlight
        avail = _find_kpi_by_name(all_kpis, "availability")
        if avail and avail.get("value") is not None:
            val = avail["value"]
            if val >= 99.9:
                highlights.append(
                    f"Platform availability is excellent at {_fmt_pct(val)}."
                )
            elif val >= 99.0:
                highlights.append(
                    f"Platform availability is {_fmt_pct(val)} "
                    f"-- within acceptable thresholds."
                )
            else:
                highlights.append(
                    f"Platform availability is {_fmt_pct(val)} "
                    f"-- below the 99.0% target. Investigation recommended."
                )

        # Data loss highlight
        data_loss = _find_kpi_by_name(all_kpis, "data loss")
        if data_loss and data_loss.get("value") is not None:
            val = data_loss["value"]
            if val == 0:
                highlights.append("Zero data loss recorded during the report period.")
            elif val < 0.1:
                highlights.append(
                    f"Data loss rate is minimal at {_fmt_pct(val)}."
                )
            else:
                highlights.append(
                    f"Data loss rate of {_fmt_pct(val)} detected. "
                    f"Review ingestion pipeline health."
                )

        # Query performance highlight
        query_perf = _find_kpi_by_name(all_kpis, "query performance")
        if query_perf is None:
            query_perf = _find_kpi_by_name(all_kpis, "p99")
        if query_perf is None:
            query_perf = _find_kpi_by_name(all_kpis, "latency")
        if query_perf and query_perf.get("value") is not None:
            val = query_perf["value"]
            unit = query_perf.get("unit", "ms")
            highlights.append(
                f"Query performance: {_fmt_number(val, unit)}."
            )

        # Cost highlight
        cost_kpi = _find_kpi_by_name(all_kpis, "cost")
        if cost_kpi and cost_kpi.get("value") is not None:
            val = cost_kpi["value"]
            highlights.append(
                f"Cost metric: {_fmt_number(val, cost_kpi.get('unit', '$'))}."
            )

        # Throughput / ingestion rate highlight
        throughput = _find_kpi_by_name(all_kpis, "throughput")
        if throughput is None:
            throughput = _find_kpi_by_name(all_kpis, "ingestion")
        if throughput and throughput.get("value") is not None:
            val = throughput["value"]
            unit = throughput.get("unit", "")
            highlights.append(
                f"Ingestion/throughput: {_fmt_number(val, unit)}."
            )

        # If we could not extract any specific highlights, give a generic one
        if not highlights:
            highlights.append(
                f"{len(all_kpis)} KPI(s) computed across all pillars."
            )

        return highlights
