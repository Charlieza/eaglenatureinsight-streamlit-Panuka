from __future__ import annotations

import io
import math
from typing import Any, Dict, Iterable, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

PAGE_WIDTH, PAGE_HEIGHT = A4

BRAND = {
    "primary": colors.HexColor("#163d63"),
    "accent": colors.HexColor("#1f8f5f"),
    "warn": colors.HexColor("#d9911a"),
    "danger": colors.HexColor("#c0392b"),
    "muted": colors.HexColor("#6b7280"),
    "bg": colors.HexColor("#f6f8fb"),
    "card": colors.white,
    "border": colors.HexColor("#e5e7eb"),
    "text": colors.HexColor("#111827"),
    "subtext": colors.HexColor("#4b5563"),
}

ABBREVIATIONS = {
    "AOI": "Area of interest",
    "CHIRPS": "Climate Hazards Group InfraRed Precipitation with Station data",
    "EE": "Google Earth Engine",
    "GHG": "Greenhouse gas",
    "ISSB": "International Sustainability Standards Board",
    "JRC": "Joint Research Centre",
    "LEAP": "Locate, Evaluate, Assess and Prepare",
    "LST": "Land surface temperature",
    "MODIS": "Moderate Resolution Imaging Spectroradiometer",
    "NDVI": "Normalized Difference Vegetation Index",
    "PDF": "Portable Document Format",
    "SME": "Small and medium-sized enterprise",
    "TNFD": "Taskforce on Nature-related Financial Disclosures",
}

def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="TitleBrand",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=BRAND["primary"],
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="SubBrand",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=BRAND["subtext"],
        spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        name="SectionBrand",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=BRAND["primary"],
        spaceBefore=8,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="SmallBrand",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=BRAND["text"],
        spaceBefore=6,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="BodyBrand",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=BRAND["text"],
        spaceAfter=6,
        alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        name="MutedBrand",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=BRAND["subtext"],
        spaceAfter=5,
    ))
    return styles

_STYLES = _styles()

def _safe_text(value: Any, fallback: str = "Not available") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback

def fmt_num(value: Any, digits: int = 2, suffix: str = "") -> str:
    if value is None or value == "":
        return "Not available"
    try:
        num = float(value)
    except Exception:
        return str(value)
    if math.isnan(num):
        return "Not available"
    return f"{num:.{digits}f}{suffix}"

def _fit_image(source: Any, max_width: float, max_height: float) -> Optional[Image]:
    try:
        img = Image(source)
        img._restrictSize(max_width, max_height)
        return img
    except Exception:
        return None

def _normalize_image_input(img: Any) -> Optional[io.BytesIO]:
    if img is None:
        return None
    if isinstance(img, io.BytesIO):
        img.seek(0)
        return img
    if isinstance(img, (bytes, bytearray)):
        return io.BytesIO(img)
    return None

def _metric_table(items: List[Tuple[str, str]], col_widths: Tuple[float, float]) -> Table:
    data = [[Paragraph(f"<b>{k}</b>", _STYLES["BodyBrand"]), Paragraph(v, _STYLES["BodyBrand"])] for k, v in items]
    tbl = Table(data, colWidths=col_widths, hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BRAND["card"]),
        ("BOX", (0, 0), (-1, -1), 0.5, BRAND["border"]),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, BRAND["border"]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return tbl

def _matrix_table(rows: List[List[str]], col_widths: Tuple[float, float, float, float]) -> Table:
    tbl = Table(rows, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND["primary"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.35, BRAND["border"]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return tbl

def _add_bullets(story: List[Any], items: Iterable[str]) -> None:
    for item in items:
        story.append(Paragraph(f"• {_safe_text(item)}", _STYLES["BodyBrand"]))

def _section_rule(story: List[Any]) -> None:
    story.append(Spacer(1, 0.1 * cm))
    story.append(HRFlowable(width="100%", thickness=0.7, color=BRAND["border"]))
    story.append(Spacer(1, 0.15 * cm))

def _page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(BRAND["muted"])
    canvas.drawRightString(PAGE_WIDTH - 1.6 * cm, 1.2 * cm, f"Page {doc.page}")
    canvas.restoreState()

def _water_exposure(metrics: Dict[str, Any]) -> str:
    val = metrics.get("water_occ")
    if val is None:
        return "Unknown"
    try:
        v = float(val)
    except Exception:
        return "Unknown"
    if v <= 5:
        return "High"
    if v <= 15:
        return "Moderate"
    return "Low"

def _heat_exposure(metrics: Dict[str, Any]) -> str:
    val = metrics.get("lst_mean")
    if val is None:
        return "Unknown"
    try:
        v = float(val)
    except Exception:
        return "Unknown"
    if v >= 30:
        return "High"
    if v >= 28:
        return "Moderate"
    return "Low"

def _vegetation_exposure(metrics: Dict[str, Any]) -> str:
    ndvi = metrics.get("ndvi_current")
    trend = metrics.get("ndvi_trend")
    try:
        nd = None if ndvi is None else float(ndvi)
        tr = None if trend is None else float(trend)
    except Exception:
        return "Unknown"
    if (nd is not None and nd < 0.25) or (tr is not None and tr < -0.03):
        return "High"
    if (nd is not None and nd < 0.45) or (tr is not None and tr < -0.01):
        return "Moderate"
    if nd is None and tr is None:
        return "Unknown"
    return "Low"

def _derive_findings(metrics: Dict[str, Any]) -> List[str]:
    findings: List[str] = []
    try:
        ra = metrics.get("rain_anom_pct")
        if ra is not None and float(ra) < -10:
            findings.append(
                f"Recent rainfall is {fmt_num(ra, 1, '%')} relative to the baseline trend, which may increase irrigation pressure and water uncertainty."
            )
    except Exception:
        pass
    try:
        nd = metrics.get("ndvi_trend")
        if nd is not None and float(nd) < -0.03:
            findings.append(
                f"Vegetation trend is {fmt_num(nd, 3)}, which suggests weakening vegetation conditions in parts of the production landscape."
            )
    except Exception:
        pass
    try:
        gh = metrics.get("greenhouse_pct")
        if gh is not None and float(gh) > 0:
            findings.append(
                f"Protected-farming structures may cover about {fmt_num(gh, 1, '%')} of the assessed area, so greenhouse conditions should be reviewed alongside open-field conditions."
            )
    except Exception:
        pass
    if not findings:
        findings = [
            "Environmental conditions should be read as a practical farm and SME decision-support assessment.",
            "Water, heat, vegetation, and land-cover conditions should be interpreted together rather than in isolation.",
            "The LEAP structure is used to turn satellite indicators into plain-language business meaning.",
        ]
    return findings[:3]

def _image_block(story: List[Any], title: str, description: str, img_data: Any) -> None:
    story.append(Paragraph(title, _STYLES["SmallBrand"]))
    story.append(Paragraph(description, _STYLES["MutedBrand"]))
    bio = _normalize_image_input(img_data)
    if bio:
        img = _fit_image(bio, 17.5 * cm, 10.0 * cm)
        if img:
            story.append(img)
            story.append(Spacer(1, 0.15 * cm))
            return
    story.append(Paragraph("Image not available in this export.", _STYLES["MutedBrand"]))
    story.append(Spacer(1, 0.15 * cm))

def _chart_block(story: List[Any], title: str, description: str, chart_data: Any) -> None:
    story.append(Paragraph(title, _STYLES["SmallBrand"]))
    story.append(Paragraph(description, _STYLES["MutedBrand"]))
    bio = _normalize_image_input(chart_data)
    if bio:
        img = _fit_image(bio, 17.5 * cm, 8.8 * cm)
        if img:
            story.append(img)
            story.append(Spacer(1, 0.15 * cm))
            return
    story.append(Paragraph("Plot not available in this export.", _STYLES["MutedBrand"]))
    story.append(Spacer(1, 0.15 * cm))

def build_tnfd_matrix(metrics: Dict[str, Any]) -> List[Tuple[str, str, str, str]]:
    return [
        (
            "Water availability",
            fmt_num(metrics.get("water_occ"), 1),
            "Low visible surface-water presence can increase dependence on irrigation, boreholes, or storage.",
            "Review water storage, irrigation planning, and groundwater reliance."
        ),
        (
            "Heat stress",
            fmt_num(metrics.get("lst_mean"), 1, " °C"),
            "Elevated temperature conditions can increase plant stress, evaporation, and cooling demand.",
            "Monitor heat conditions and consider shading, ventilation, or cooling measures."
        ),
        (
            "Vegetation condition",
            fmt_num(metrics.get("ndvi_current"), 3),
            "Vegetation condition gives a simple signal of cover strength and possible stress in the landscape.",
            "Monitor vegetation condition together with soil moisture and field observations."
        ),
        (
            "Rainfall variability",
            fmt_num(metrics.get("rain_anom_pct"), 1, "%"),
            "Rainfall conditions influence irrigation demand, water certainty, and seasonal production planning.",
            "Review seasonal planning and irrigation scheduling."
        ),
        (
            "Land condition",
            fmt_num(metrics.get("forest_loss_pct"), 1, "%"),
            "Landscape change can affect ecosystem stability, local resilience, and longer-term production conditions.",
            "Monitor surrounding land-use change and maintain ecological buffers where possible."
        ),
    ]

def build_overall_narrative(metrics: Dict[str, Any]) -> List[str]:
    statements: List[str] = []

    try:
        if metrics.get("rain_anom_pct") is not None and float(metrics["rain_anom_pct"]) < -10:
            statements.append(
                f"Rainfall conditions are currently {fmt_num(metrics.get('rain_anom_pct'), 1, '%')}, which suggests higher irrigation demand and closer water planning may be needed."
            )
    except Exception:
        pass

    try:
        if metrics.get("lst_mean") is not None and float(metrics["lst_mean"]) > 30:
            statements.append(
                f"Average land surface temperature is {fmt_num(metrics.get('lst_mean'), 1, ' °C')}, which suggests elevated heat conditions that may increase crop stress and water demand."
            )
    except Exception:
        pass

    try:
        if metrics.get("ndvi_trend") is not None and float(metrics["ndvi_trend"]) < 0:
            statements.append(
                f"The vegetation trend is {fmt_num(metrics.get('ndvi_trend'), 3)}, which may indicate moisture, soil, or management-related stress in part of the landscape."
            )
    except Exception:
        pass

    if not statements:
        statements.append("Environmental conditions appear broadly stable based on the available indicators, although seasonal monitoring remains important.")

    return statements

def build_greenhouse_recommendations(metrics: Dict[str, Any]) -> List[str]:
    recs: List[str] = []

    try:
        if metrics.get("lst_mean") is not None and float(metrics["lst_mean"]) >= 30:
            recs.append(
                f"Heat conditions are elevated at about {fmt_num(metrics.get('lst_mean'), 1, ' °C')}; review ventilation, shading, or cooling measures for protected farming areas."
            )
    except Exception:
        pass

    try:
        if metrics.get("rain_anom_pct") is not None and float(metrics["rain_anom_pct"]) < -10:
            recs.append(
                f"Rainfall is {fmt_num(metrics.get('rain_anom_pct'), 1, '%')} relative to the baseline trend; review irrigation scheduling and storage capacity for both greenhouse and open-field production."
            )
    except Exception:
        pass

    try:
        if metrics.get("ndvi_trend") is not None and float(metrics["ndvi_trend"]) < -0.01:
            recs.append(
                f"The vegetation trend is {fmt_num(metrics.get('ndvi_trend'), 3)}; inspect for moisture stress, nutrient issues, or pest pressure where crops appear uneven."
            )
    except Exception:
        pass

    humidity = _safe_text(metrics.get("greenhouse_humidity_risk"), "")
    if humidity and humidity not in ("", "Not available", "Unknown", "Low"):
        recs.append(
            f"Humidity risk is assessed as {humidity.lower()}; review airflow and ventilation routines to reduce disease pressure in protected-farming zones."
        )

    pest = _safe_text(metrics.get("greenhouse_pest_risk"), "")
    if pest and pest not in ("", "Not available", "Unknown", "Low"):
        recs.append(
            f"Pest risk is assessed as {pest.lower()}; increase crop inspection frequency and review pest monitoring in greenhouse and nearby production areas."
        )

    if not recs:
        recs.append(
            "Protected-farming conditions do not currently show a single dominant warning sign, but routine monitoring of temperature, ventilation, irrigation, and crop health remains important."
        )

    return recs

def build_pdf_report(
    preset: str,
    category: str,
    hist_start: int,
    hist_end: int,
    metrics: Dict[str, Any],
    risk: Dict[str, Any],
    image_payloads: Optional[List[Dict[str, Any]]] = None,
    chart_payloads: Optional[List[Dict[str, Any]]] = None,
    **kwargs,
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.5 * cm,
        title="EagleNatureInsight Panuka Pilot Report",
        author="OpenAI",
    )

    story: List[Any] = []

    story.append(Paragraph("EagleNatureInsight | Panuka Pilot", _STYLES["TitleBrand"]))
    story.append(Paragraph(
        "TNFD-aligned agribusiness screening report for Panuka AgriBiz Hub. This report translates satellite and environmental signals into plain-language insights for farm operations, greenhouse conditions, water planning, climate resilience, and SME financing discussions.",
        _STYLES["SubBrand"],
    ))

    story.append(Paragraph("1. Executive summary", _STYLES["SectionBrand"]))
    for txt in [
        f"This report summarises environmental and nature-related screening results for <b>{_safe_text(preset)}</b>.",
        f"The historical review period used in this assessment is <b>{hist_start} to {hist_end}</b>.",
        "The purpose of the report is to help Panuka and supported SMEs understand practical questions such as water certainty, vegetation condition, heat stress, greenhouse conditions, and possible operational risks.",
        "The report follows the TNFD LEAP structure and translates technical outputs into practical agribusiness language.",
    ]:
        story.append(Paragraph(txt, _STYLES["BodyBrand"]))

    story.append(Paragraph("Top takeaways", _STYLES["SmallBrand"]))
    _add_bullets(story, _derive_findings(metrics))
    _section_rule(story)

    story.append(Paragraph("2. Reading guide and defined abbreviations", _STYLES["SectionBrand"]))
    story.append(Paragraph(
        "This report keeps technical language to a minimum. Where abbreviations are used, they are defined below so the report remains easy to read for non-technical audiences.",
        _STYLES["BodyBrand"],
    ))
    story.append(_metric_table(sorted(ABBREVIATIONS.items()), (3.2 * cm, 13.8 * cm)))
    _section_rule(story)

    story.append(Paragraph("3. Overview metrics", _STYLES["SectionBrand"]))
    story.append(_metric_table([
        ("Panuka pilot site", _safe_text(preset)),
        ("Pilot category", _safe_text(category)),
        ("Assessment area", fmt_num(metrics.get("area_ha"), 2, " ha")),
        ("Current vegetation condition", fmt_num(metrics.get("ndvi_current"), 3)),
        ("Vegetation trend", fmt_num(metrics.get("ndvi_trend"), 3)),
        ("Rainfall anomaly", fmt_num(metrics.get("rain_anom_pct"), 1, "%")),
        ("Recent land surface temperature", fmt_num(metrics.get("lst_mean"), 1, " °C")),
        ("Tree cover", fmt_num(metrics.get("tree_pct"), 1, "%")),
        ("Cropland", fmt_num(metrics.get("cropland_pct"), 1, "%")),
        ("Built-up area", fmt_num(metrics.get("built_pct"), 1, "%")),
        ("Surface-water occurrence", fmt_num(metrics.get("water_occ"), 1)),
        ("Forest loss", fmt_num(metrics.get("forest_loss_pct"), 1, "%")),
    ], (7.2 * cm, 9.8 * cm)))
    _section_rule(story)

    story.append(Paragraph("4. Environmental indicator interpretation", _STYLES["SectionBrand"]))
    indicator_rows = [
        ["Indicator", "Current value", "What this means", "Suggested response"],
        [
            "Rainfall anomaly",
            fmt_num(metrics.get("rain_anom_pct"), 1, "%"),
            "Shows whether recent rainfall is below, near, or above the longer-term baseline.",
            "Review irrigation scheduling and seasonal planning.",
        ],
        [
            "Vegetation condition",
            fmt_num(metrics.get("ndvi_current"), 3),
            "Shows whether vegetation cover appears weak, moderate, or relatively strong.",
            "Use together with field checks and crop observations.",
        ],
        [
            "Vegetation trend",
            fmt_num(metrics.get("ndvi_trend"), 3),
            "Shows whether vegetation is improving, stable, or weakening over time.",
            "Monitor soil moisture, crop stress, and local management conditions.",
        ],
        [
            "Land surface temperature",
            fmt_num(metrics.get("lst_mean"), 1, " °C"),
            "Shows whether heat conditions may be adding stress to crops, workers, or infrastructure.",
            "Review shading, cooling, and heat-management measures where needed.",
        ],
        [
            "Surface-water occurrence",
            fmt_num(metrics.get("water_occ"), 1),
            "Shows whether visible water is limited or more available in the surrounding context.",
            "Review storage, borehole reliance, and water planning.",
        ],
    ]
    story.append(_matrix_table(indicator_rows, (3.5 * cm, 2.8 * cm, 5.2 * cm, 5.5 * cm)))
    _section_rule(story)

    story.append(Paragraph("5. LEAP summary", _STYLES["SectionBrand"]))
    for heading, desc in [
        ("Locate", "The site and surrounding production landscape were defined using the selected point or polygon, then screened for land cover, vegetation, water context, and surrounding environmental conditions."),
        ("Evaluate", "The assessment reviewed nature dependencies, visible pressures, greenhouse conditions where relevant, and practical business meaning for water, heat, vegetation, and operational resilience."),
        ("Assess", "The assessment translated those signals into a plain-language risk view, including physical conditions such as water stress, heat stress, vegetation stress, and broader landscape pressure."),
        ("Prepare", "The assessment generated practical next actions, suggested review frequency, and business-oriented recommendations that Panuka or supported SMEs can test and refine."),
    ]:
        story.append(Paragraph(f"<b>{heading}</b>: {desc}", _STYLES["BodyBrand"]))
    _section_rule(story)

    story.append(Paragraph("6. Locate", _STYLES["SectionBrand"]))
    story.append(Paragraph(
        "Locate explains where the farm interacts with nature. It shows the production setting, surrounding land cover, visible water context, and the physical footprint used for the assessment.",
        _STYLES["BodyBrand"],
    ))
    story.append(_metric_table([
        ("Area of interest", fmt_num(metrics.get("area_ha"), 2, " ha")),
        ("Tree cover", fmt_num(metrics.get("tree_pct"), 1, "%")),
        ("Cropland", fmt_num(metrics.get("cropland_pct"), 1, "%")),
        ("Built-up", fmt_num(metrics.get("built_pct"), 1, "%")),
        ("Surface-water occurrence", fmt_num(metrics.get("water_occ"), 1)),
    ], (7.2 * cm, 9.8 * cm)))
    _section_rule(story)

    story.append(Paragraph("7. Evaluate", _STYLES["SectionBrand"]))
    story.append(Paragraph(
        "Evaluate reviews how the farm depends on nature, what pressures may be visible, what protected-farming conditions may matter, and what the indicators suggest for practical farm management.",
        _STYLES["BodyBrand"],
    ))
    story.append(Paragraph("Dependencies on nature", _STYLES["SmallBrand"]))
    _add_bullets(story, [
        "The business depends on reliable water availability for irrigation, crop growth, and day-to-day farm operations.",
        "Vegetation condition and tree cover matter because they help with soil protection, microclimate stability, and ecological resilience.",
        "Rainfall patterns and heat conditions matter because they influence crop stress, pest pressure, and farming uncertainty.",
    ])
    impacts = []
    try:
        if metrics.get("ndvi_trend") is not None and float(metrics["ndvi_trend"]) < -0.03:
            impacts.append(f"Vegetation trend is {fmt_num(metrics.get('ndvi_trend'), 3)}, which suggests weakening vegetation conditions in part of the landscape.")
        else:
            impacts.append("Vegetation condition does not show a strong decline signal, but it should still be monitored over time.")
    except Exception:
        impacts.append("Vegetation condition should be monitored over time.")
    try:
        if metrics.get("forest_loss_pct") is not None and float(metrics["forest_loss_pct"]) > 5:
            impacts.append(f"Forest loss of {fmt_num(metrics.get('forest_loss_pct'), 1, '%')} is visible in the broader landscape, which can indicate land-use pressure.")
        else:
            impacts.append("Forest-loss pressure does not appear to be a dominant signal within the current assessment area.")
    except Exception:
        pass
    try:
        if metrics.get("water_occ") is not None and float(metrics["water_occ"]) < 5:
            impacts.append(f"Visible surface-water occurrence is {fmt_num(metrics.get('water_occ'), 1)}, which suggests stronger dependence on irrigation, boreholes, or storage.")
    except Exception:
        pass
    story.append(Paragraph("Possible impacts and pressures", _STYLES["SmallBrand"]))
    _add_bullets(story, impacts)
    story.append(Paragraph("What the indicators are suggesting", _STYLES["SmallBrand"]))
    _add_bullets(story, _derive_findings(metrics))
    story.append(Paragraph("Exposure summary", _STYLES["SmallBrand"]))
    story.append(_metric_table([
        ("Water exposure", f'{_water_exposure(metrics)} — Based on visible surface-water context'),
        ("Heat exposure", f'{_heat_exposure(metrics)} — Based on recent land surface temperature'),
        ("Vegetation exposure", f'{_vegetation_exposure(metrics)} — Based on current vegetation and trend'),
    ], (7.2 * cm, 9.8 * cm)))
    story.append(Paragraph("Why this matters", _STYLES["SmallBrand"]))
    story.append(Paragraph(
        "For an agribusiness, these signals matter because water reliability, vegetation condition, and heat stress can affect production, pest pressure, soil protection, and financial resilience.",
        _STYLES["BodyBrand"],
    ))
    _section_rule(story)

    story.append(Paragraph("8. TNFD environmental risk matrix", _STYLES["SectionBrand"]))
    story.append(Paragraph(
        "The matrix below uses a portfolio of indicators rather than a single nature score. It is intended to help the reader understand current environmental conditions, what they mean, and what responses may be practical.",
        _STYLES["BodyBrand"],
    ))
    matrix_rows = [["Indicator", "Current value", "What this means", "Suggested response"]]
    for row in build_tnfd_matrix(metrics):
        matrix_rows.append(list(row))
    story.append(_matrix_table(matrix_rows, (3.4 * cm, 2.6 * cm, 5.3 * cm, 5.7 * cm)))
    _section_rule(story)

    story.append(Paragraph("9. Greenhouse and production conditions", _STYLES["SectionBrand"]))
    story.append(Paragraph(
        "This section summarises observed conditions related to protected and open-field production environments. Greenhouse-related outputs are best read as screening signals that help prioritise management attention.",
        _STYLES["BodyBrand"],
    ))
    story.append(_metric_table([
        ("Greenhouse detected", _safe_text(metrics.get("greenhouse_detected"), "No")),
        ("Estimated greenhouse area", fmt_num(metrics.get("greenhouse_ha"), 2, " ha")),
        ("Estimated greenhouse share of site", fmt_num(metrics.get("greenhouse_pct"), 1, "%")),
        ("Greenhouse heat stress", _safe_text(metrics.get("greenhouse_heat_risk"))),
        ("Greenhouse humidity risk", _safe_text(metrics.get("greenhouse_humidity_risk"))),
        ("Greenhouse pest risk", _safe_text(metrics.get("greenhouse_pest_risk"))),
        ("Irrigation demand", _safe_text(metrics.get("irrigation_demand"))),
    ], (7.2 * cm, 9.8 * cm)))
    story.append(Paragraph("Operational recommendations for protected and open-field production", _STYLES["SmallBrand"]))
    _add_bullets(story, build_greenhouse_recommendations(metrics))
    _section_rule(story)

    story.append(Paragraph("10. Overall environmental interpretation", _STYLES["SectionBrand"]))
    for statement in build_overall_narrative(metrics):
        story.append(Paragraph(statement, _STYLES["BodyBrand"]))
    _section_rule(story)

    story.append(Paragraph("11. Recommended actions", _STYLES["SectionBrand"]))
    story.append(Paragraph(
        "The actions below translate the observed environmental conditions into practical next steps for operations, incubation support, and resilience planning.",
        _STYLES["BodyBrand"],
    ))
    _add_bullets(story, risk.get("recs") or [])
    _section_rule(story)

    story.append(Paragraph("12. Monitoring and review frequency", _STYLES["SectionBrand"]))
    _add_bullets(story, [
        "Review this assessment at the start of each planting season.",
        "Review again after major rainfall variability, drought signals, or unusual heat conditions.",
        "Review before expansion, irrigation investment, or financing discussions.",
        "Review protected-farming conditions more frequently during peak production periods.",
    ])
    _section_rule(story)

    story.append(Paragraph("13. Bankability and SME support perspective", _STYLES["SectionBrand"]))
    _add_bullets(story, [
        "Use water reliability, production reliability, and heat conditions to support conversations about climate and operational stability.",
        "Use protected-farming and open-field differences to show that the business understands where different production risks sit.",
        "Use vegetation and rainfall trends to explain longer-term resilience, not just current conditions.",
        "Use the report as a structured screening document for incubation, advisory support, or discussions with funders and partners.",
    ])
    _section_rule(story)

    story.append(Paragraph("14. Image outputs", _STYLES["SectionBrand"]))
    story.append(Paragraph(
        "Each image below is paired with a short explanation so that non-technical readers can understand what it shows and why it matters.",
        _STYLES["BodyBrand"],
    ))
    for payload in (image_payloads or []):
        _image_block(
            story,
            _safe_text(payload.get("title")),
            _safe_text(payload.get("description")),
            payload.get("bytes"),
        )

    story.append(PageBreak())

    story.append(Paragraph("15. Historical plots and current charts", _STYLES["SectionBrand"]))
    story.append(Paragraph(
        "The plots below help explain trends over time. Each one is described in plain language so the reader can understand what changes may matter for farm decisions.",
        _STYLES["BodyBrand"],
    ))
    for payload in (chart_payloads or []):
        _chart_block(
            story,
            _safe_text(payload.get("title")),
            _safe_text(payload.get("description")),
            payload.get("bytes"),
        )
    _section_rule(story)

    story.append(Paragraph("16. Detailed metrics appendix", _STYLES["SectionBrand"]))
    appendix_rows = sorted((str(k), _safe_text(v)) for k, v in metrics.items())
    story.append(_metric_table(appendix_rows, (6.0 * cm, 11.0 * cm)))

    doc.build(story, onFirstPage=_page_number, onLaterPages=_page_number)
    return buffer.getvalue()
