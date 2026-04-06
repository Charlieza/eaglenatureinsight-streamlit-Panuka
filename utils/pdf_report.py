# pdf_report_panuka_v6.py
# Client-facing TNFD-aligned report generator
# Updated to:
# - Remove any reference to client discussions
# - Integrate TNFD Matrix (portfolio of metrics)
# - Replace explicit numerical nature score with narrative risk interpretation

from __future__ import annotations
import io
import math
from typing import Any, Dict, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)

PAGE_WIDTH, PAGE_HEIGHT = A4

BRAND = {
    "primary": colors.HexColor("#163d63"),
    "border": colors.HexColor("#e5e7eb"),
    "text": colors.HexColor("#111827"),
    "subtext": colors.HexColor("#4b5563"),
}

def _styles():
    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="TitleBrand",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=BRAND["primary"],
            spaceAfter=8,
        )
    )

    styles.add(
        ParagraphStyle(
            name="SectionBrand",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=BRAND["primary"],
            spaceBefore=10,
            spaceAfter=6,
        )
    )

    styles.add(
        ParagraphStyle(
            name="BodyBrand",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=BRAND["text"],
            spaceAfter=6,
        )
    )

    styles.add(
        ParagraphStyle(
            name="MutedBrand",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=BRAND["subtext"],
            spaceAfter=5,
        )
    )

    return styles

_STYLES = _styles()


def _safe(value: Any) -> str:
    if value is None:
        return "Not available"
    text = str(value).strip()
    return text if text else "Not available"


def fmt_num(value: Any, digits: int = 2, suffix: str = "") -> str:
    try:
        num = float(value)
        return f"{num:.{digits}f}{suffix}"
    except Exception:
        return "Not available"


def _rule(story):
    story.append(Spacer(1, 0.1 * cm))
    story.append(HRFlowable(width="100%", thickness=0.7, color=BRAND["border"]))
    story.append(Spacer(1, 0.15 * cm))


def _metric_table(items: List[Tuple[str, str]]):

    tbl = Table(items, colWidths=[7 * cm, 10 * cm])

    tbl.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, BRAND["border"]),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, BRAND["border"]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )

    return tbl


def _interpretation(metrics):

    statements = []

    try:
        rain = float(metrics.get("rain_anom_pct"))
        if rain < -10:
            statements.append(
                f"Rainfall is {abs(rain):.1f}% below the long-term baseline, indicating increased irrigation demand."
            )
    except Exception:
        pass

    try:
        temp = float(metrics.get("lst_mean"))
        if temp >= 30:
            statements.append(
                f"Average surface temperature of {temp:.1f}°C indicates elevated heat stress conditions."
            )
    except Exception:
        pass

    try:
        ndvi = float(metrics.get("ndvi_current"))
        if ndvi < 0.35:
            statements.append(
                f"Vegetation condition index of {ndvi:.2f} suggests moderate vegetation stress."
            )
    except Exception:
        pass

    if not statements:

        statements.append(
            "Environmental conditions appear generally stable within the current observation period."
        )

    return statements


def _tnfd_matrix(metrics):

    matrix_rows = [
        ("Water availability", fmt_num(metrics.get("water_occ"), 1)),
        ("Vegetation condition", fmt_num(metrics.get("ndvi_current"), 2)),
        ("Temperature exposure", fmt_num(metrics.get("lst_mean"), 1, " °C")),
        ("Rainfall variability", fmt_num(metrics.get("rain_anom_pct"), 1, "%")),
        ("Land-use pressure", fmt_num(metrics.get("forest_loss_pct"), 1, "%")),
    ]

    return matrix_rows


def build_pdf_report(
    preset: str,
    category: str,
    hist_start: int,
    hist_end: int,
    metrics: Dict[str, Any],
    risk: Dict[str, Any],
    **kwargs,
):

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.5 * cm,
    )

    story = []

    story.append(
        Paragraph(
            "EagleNatureInsight Environmental Screening Report",
            _STYLES["TitleBrand"],
        )
    )

    story.append(
        Paragraph(
            f"Site: {_safe(preset)}",
            _STYLES["BodyBrand"],
        )
    )

    story.append(
        Paragraph(
            f"Assessment period: {hist_start} to {hist_end}",
            _STYLES["BodyBrand"],
        )
    )

    _rule(story)

    story.append(
        Paragraph(
            "Environmental indicator interpretation",
            _STYLES["SectionBrand"],
        )
    )

    for line in _interpretation(metrics):

        story.append(
            Paragraph(line, _STYLES["BodyBrand"])
        )

    _rule(story)

    story.append(
        Paragraph(
            "TNFD environmental risk matrix",
            _STYLES["SectionBrand"],
        )
    )

    story.append(
        Paragraph(
            "The matrix below presents a portfolio view of environmental conditions relevant to operational planning and resilience.",
            _STYLES["BodyBrand"],
        )
    )

    matrix_data = [["Indicator", "Observed condition"]]

    for row in _tnfd_matrix(metrics):

        matrix_data.append(row)

    story.append(_metric_table(matrix_data))

    _rule(story)

    story.append(
        Paragraph(
            "Operational interpretation",
            _STYLES["SectionBrand"],
        )
    )

    story.append(
        Paragraph(
            "Environmental conditions should be monitored regularly. Changes in rainfall, temperature, or vegetation may affect production reliability, irrigation demand, and operational planning.",
            _STYLES["BodyBrand"],
        )
    )

    story.append(
        Paragraph(
            "Recommended monitoring frequency: seasonal review, and additional review before major planting or infrastructure decisions.",
            _STYLES["BodyBrand"],
        )
    )

    doc.build(story)

    return buffer.getvalue()
