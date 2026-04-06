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
    "ISSB": "International Sustainability Standards Board",
    "JRC": "Joint Research Centre",
    "LEAP": "Locate, Evaluate, Assess and Prepare",
    "LST": "Land surface temperature",
    "MODIS": "Moderate Resolution Imaging Spectroradiometer",
    "NDVI": "Normalized Difference Vegetation Index",
    "SME": "Small and medium-sized enterprise",
    "TNFD": "Taskforce on Nature-related Financial Disclosures",
}

def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleBrand", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=BRAND["primary"], spaceAfter=8))
    styles.add(ParagraphStyle(name="SubBrand", parent=styles["BodyText"], fontName="Helvetica", fontSize=10, leading=14, textColor=BRAND["subtext"], spaceAfter=12))
    styles.add(ParagraphStyle(name="SectionBrand", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=BRAND["primary"], spaceBefore=8, spaceAfter=6))
    styles.add(ParagraphStyle(name="SmallBrand", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=BRAND["text"], spaceBefore=6, spaceAfter=4))
    styles.add(ParagraphStyle(name="BodyBrand", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13, textColor=BRAND["text"], spaceAfter=6, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name="MutedBrand", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.5, leading=12, textColor=BRAND["subtext"], spaceAfter=5))
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

def _bucket_num(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None

def _level(value: Any, low_bad: bool, moderate: float, high: float) -> str:
    v = _bucket_num(value)
    if v is None:
        return "Not available"
    if low_bad:
        if v <= moderate:
            return "High"
        if v <= high:
            return "Moderate"
        return "Low"
    if v >= high:
        return "High"
    if v >= moderate:
        return "Moderate"
    return "Low"

def _greenhouse_recommendations(metrics: Dict[str, Any]) -> List[str]:
    recs: List[str] = []
    gh_pct = _bucket_num(metrics.get("greenhouse_pct"))
    lst = _bucket_num(metrics.get("lst_mean"))
    rain = _bucket_num(metrics.get("rain_anom_pct"))
    ndvi = _bucket_num(metrics.get("ndvi_current"))
    ndvi_trend = _bucket_num(metrics.get("ndvi_trend"))
    water = _bucket_num(metrics.get("water_occ"))

    if gh_pct is not None and gh_pct > 0:
        recs.append(f"Protected-farming structures appear to cover about {gh_pct:.1f}% of the assessed area, so greenhouse conditions should be reviewed alongside open-field conditions.")
    if lst is not None:
        if lst >= 30:
            recs.append(f"Average land surface temperature is {lst:.1f}°C, which suggests elevated heat pressure. Review greenhouse ventilation, shading, and cooling measures.")
        elif lst >= 28:
            recs.append(f"Average land surface temperature is {lst:.1f}°C, which suggests moderate heat pressure. Monitor greenhouse temperatures closely during hotter periods.")
    if rain is not None:
        if rain <= -10:
            recs.append(f"Rainfall is {abs(rain):.1f}% below the historical baseline. Review irrigation planning, storage, and water-use efficiency for protected farming.")
        elif rain >= 10:
            recs.append(f"Rainfall is {rain:.1f}% above the historical baseline. Check drainage, humidity control, and disease pressure in protected farming areas.")
    if ndvi_trend is not None and ndvi_trend < -0.03:
        recs.append(f"Vegetation trend is {ndvi_trend:.3f}, indicating decline. Inspect crop stress, soil moisture, nutrient status, and possible pest or disease pressure.")
    elif ndvi is not None and ndvi < 0.25:
        recs.append(f"Current NDVI is {ndvi:.3f}, which suggests weak vegetation cover. Check plant health, irrigation adequacy, and crop stress conditions.")
    if water is not None and water < 5:
        recs.append(f"Surface-water occurrence is {water:.1f}, suggesting limited visible natural water. Confirm borehole reliability, water storage, and contingency planning.")
    if not recs:
        recs.append("Satellite signals do not show a single dominant greenhouse concern, but regular checks of ventilation, irrigation, and plant-health conditions are still recommended.")
    return recs[:5]

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
        "TNFD-aligned agribusiness screening report for Panuka AgriBiz Hub. This report translates satellite and environmental signals into practical farm-management insights for water planning, vegetation condition, greenhouse operations, climate resilience, and SME financing discussions.",
        _STYLES["SubBrand"],
    ))

    story.append(Paragraph("1. Executive summary", _STYLES["SectionBrand"]))
    for txt in [
        f"This report summarises screening results for <b>{_safe_text(preset)}</b> within the <b>{hist_start} to {hist_end}</b> review period.",
        "The analysis is designed to support Panuka, its farm team, and supported SMEs with practical interpretation of water conditions, vegetation performance, heat stress, land cover, and greenhouse-related conditions.",
        f"The current risk score is <b>{_safe_text(risk.get('score'))}/100</b>, with a risk band of <b>{_safe_text(risk.get('band'))}</b>.",
    ]:
        story.append(Paragraph(txt, _STYLES["BodyBrand"]))

    story.append(Paragraph("Top takeaways", _STYLES["SmallBrand"]))
    takeaways = []
    rain = _bucket_num(metrics.get("rain_anom_pct"))
    if rain is not None:
        takeaways.append(f"Rainfall anomaly is {rain:.1f}%, which helps explain current water certainty and likely irrigation pressure.")
    ndvi = _bucket_num(metrics.get("ndvi_current"))
    if ndvi is not None:
        takeaways.append(f"Current NDVI is {ndvi:.3f}, which gives a quick view of vegetation strength across the site.")
    lst = _bucket_num(metrics.get("lst_mean"))
    if lst is not None:
        takeaways.append(f"Recent land surface temperature is {lst:.1f}°C, which helps indicate heat stress conditions.")
    if not takeaways:
        takeaways = ["This site should be interpreted using the combined picture from rainfall, vegetation, heat, water, and land-cover conditions rather than one indicator alone."]
    _add_bullets(story, takeaways[:3])
    _section_rule(story)

    story.append(Paragraph("2. Reading guide and abbreviations", _STYLES["SectionBrand"]))
    story.append(Paragraph(
        "This report uses plain language, but keeps key numbers visible so that the reader can see both the evidence and the interpretation.",
        _STYLES["BodyBrand"],
    ))
    story.append(_metric_table(sorted(ABBREVIATIONS.items()), (3.2 * cm, 13.8 * cm)))
    _section_rule(story)

    story.append(Paragraph("3. Site overview", _STYLES["SectionBrand"]))
    story.append(_metric_table([
        ("Panuka pilot site", _safe_text(preset)),
        ("Pilot category", _safe_text(category)),
        ("Assessment area", fmt_num(metrics.get("area_ha"), 2, " ha")),
        ("Current NDVI", fmt_num(metrics.get("ndvi_current"), 3)),
        ("Vegetation trend", fmt_num(metrics.get("ndvi_trend"), 3)),
        ("Rainfall anomaly", fmt_num(metrics.get("rain_anom_pct"), 1, "%")),
        ("Recent LST", fmt_num(metrics.get("lst_mean"), 1, " °C")),
        ("Tree cover", fmt_num(metrics.get("tree_pct"), 1, "%")),
        ("Cropland", fmt_num(metrics.get("cropland_pct"), 1, "%")),
        ("Built-up area", fmt_num(metrics.get("built_pct"), 1, "%")),
        ("Surface-water occurrence", fmt_num(metrics.get("water_occ"), 1)),
        ("Forest loss", fmt_num(metrics.get("forest_loss_pct"), 1, "%")),
    ], (7.0 * cm, 10.0 * cm)))
    _section_rule(story)

    story.append(Paragraph("4. Environmental indicator interpretation", _STYLES["SectionBrand"]))
    interp_rows = [
        ("Rainfall anomaly", f"{fmt_num(metrics.get('rain_anom_pct'), 1, '%')} — Below-normal rainfall usually means higher irrigation pressure; above-normal rainfall may increase drainage and disease concerns."),
        ("Current NDVI", f"{fmt_num(metrics.get('ndvi_current'), 3)} — Lower NDVI usually suggests weaker vegetation; higher NDVI usually suggests stronger vegetation cover."),
        ("Vegetation trend", f"{fmt_num(metrics.get('ndvi_trend'), 3)} — A negative trend suggests vegetation is weakening over time; a positive trend suggests improvement."),
        ("Recent LST", f"{fmt_num(metrics.get('lst_mean'), 1, ' °C')} — Higher temperature values usually mean greater heat stress for crops, workers, and infrastructure."),
        ("Surface-water occurrence", f"{fmt_num(metrics.get('water_occ'), 1)} — Lower values suggest limited visible natural water and possible stronger dependence on storage or groundwater."),
        ("Forest loss", f"{fmt_num(metrics.get('forest_loss_pct'), 1, '%')} — Higher values indicate more forest loss in the wider landscape context."),
    ]
    story.append(_metric_table(interp_rows, (4.3 * cm, 12.7 * cm)))
    _section_rule(story)

    story.append(Paragraph("5. Locate", _STYLES["SectionBrand"]))
    story.append(Paragraph(
        "Locate explains where the farm interacts with nature. It shows the production setting, surrounding land cover, visible water context, and the assessment footprint used in this report.",
        _STYLES["BodyBrand"],
    ))
    story.append(_metric_table([
        ("Area of interest", fmt_num(metrics.get("area_ha"), 2, " ha")),
        ("Tree cover", fmt_num(metrics.get("tree_pct"), 1, "%")),
        ("Cropland", fmt_num(metrics.get("cropland_pct"), 1, "%")),
        ("Built-up", fmt_num(metrics.get("built_pct"), 1, "%")),
        ("Surface-water occurrence", fmt_num(metrics.get("water_occ"), 1)),
    ], (7.0 * cm, 10.0 * cm)))
    _section_rule(story)

    story.append(Paragraph("6. Evaluate", _STYLES["SectionBrand"]))
    story.append(Paragraph(
        "Evaluate reviews how the farm depends on nature and what pressures may be building in the landscape. The aim is to translate indicators into practical business meaning.",
        _STYLES["BodyBrand"],
    ))
    story.append(Paragraph("Dependencies on nature", _STYLES["SmallBrand"]))
    _add_bullets(story, [
        f"Water availability matters because rainfall anomaly is {fmt_num(metrics.get('rain_anom_pct'), 1, '%')} and visible surface-water occurrence is {fmt_num(metrics.get('water_occ'), 1)}.",
        f"Vegetation and soil protection matter because current NDVI is {fmt_num(metrics.get('ndvi_current'), 3)} and the vegetation trend is {fmt_num(metrics.get('ndvi_trend'), 3)}.",
        f"Heat conditions matter because recent LST is {fmt_num(metrics.get('lst_mean'), 1, ' °C')}, which can affect crop stress, water demand, and working conditions.",
    ])
    story.append(Paragraph("Possible impacts and pressures", _STYLES["SmallBrand"]))
    pressures = []
    if _bucket_num(metrics.get("ndvi_trend")) is not None and _bucket_num(metrics.get("ndvi_trend")) < -0.03:
        pressures.append(f"Vegetation trend is {fmt_num(metrics.get('ndvi_trend'), 3)}, suggesting vegetation pressure or declining ground condition.")
    else:
        pressures.append(f"Vegetation trend is {fmt_num(metrics.get('ndvi_trend'), 3)}, which does not indicate a strong decline signal at this stage.")
    if _bucket_num(metrics.get("forest_loss_pct")) is not None:
        pressures.append(f"Forest loss is {fmt_num(metrics.get('forest_loss_pct'), 1, '%')} in the wider landscape context, which helps show whether surrounding habitat pressure is rising.")
    if _bucket_num(metrics.get("built_pct")) is not None:
        pressures.append(f"Built-up area is {fmt_num(metrics.get('built_pct'), 1, '%')}, which helps explain site heat and fragmentation pressure.")
    _add_bullets(story, pressures)
    story.append(Paragraph("Exposure summary", _STYLES["SmallBrand"]))
    story.append(_metric_table([
        ("Water exposure", f"{_level(metrics.get('water_occ'), True, 5, 15)} — driven by visible water context and rainfall conditions"),
        ("Heat exposure", f"{_level(metrics.get('lst_mean'), False, 28, 30)} — driven by current land surface temperature"),
        ("Vegetation exposure", f"{_level(metrics.get('ndvi_current'), True, 0.25, 0.45)} — supported by current vegetation condition and trend"),
    ], (7.0 * cm, 10.0 * cm)))
    _section_rule(story)

    story.append(Paragraph("7. Greenhouse and protected-farming conditions", _STYLES["SectionBrand"]))
    story.append(Paragraph(
        "This section focuses on protected farming and greenhouse operations. Where greenhouse structures are detected, the recommendations below should be read alongside open-field conditions. Even where greenhouse detection is limited, satellite indicators can still suggest likely heat, water, humidity, and pest-related concerns.",
        _STYLES["BodyBrand"],
    ))
    story.append(_metric_table([
        ("Greenhouse detected", _safe_text(metrics.get("greenhouse_detected"), "No")),
        ("Estimated greenhouse area", fmt_num(metrics.get("greenhouse_ha"), 2, " ha")),
        ("Estimated greenhouse share of site", fmt_num(metrics.get("greenhouse_pct"), 1, "%")),
        ("Greenhouse heat stress", _safe_text(metrics.get("greenhouse_heat_risk"), _level(metrics.get("lst_mean"), False, 28, 30))),
        ("Greenhouse humidity risk", _safe_text(metrics.get("greenhouse_humidity_risk"), "Moderate" if (_bucket_num(metrics.get("rain_anom_pct")) or 0) > 5 else "Elevated" if (_bucket_num(metrics.get("rain_anom_pct")) or 0) < -10 else "Moderate")),
        ("Greenhouse pest risk", _safe_text(metrics.get("greenhouse_pest_risk"), "Elevated" if (_bucket_num(metrics.get("lst_mean")) or 0) >= 30 or (_bucket_num(metrics.get("ndvi_trend")) or 0) < -0.03 else "Moderate")),
        ("Irrigation demand", _safe_text(metrics.get("irrigation_demand"), "High" if (_bucket_num(metrics.get("rain_anom_pct")) or 0) <= -10 else "Moderate")),
    ], (7.0 * cm, 10.0 * cm)))
    story.append(Paragraph("Greenhouse recommendations", _STYLES["SmallBrand"]))
    _add_bullets(story, _greenhouse_recommendations(metrics))
    _section_rule(story)

    story.append(Paragraph("8. Assess", _STYLES["SectionBrand"]))
    story.append(Paragraph(
        "Assess translates the environmental signals into practical risk implications for production, operations, and resilience planning.",
        _STYLES["BodyBrand"],
    ))
    story.append(_metric_table([
        ("Nature risk score", f"{_safe_text(risk.get('score'))}/100"),
        ("Risk band", _safe_text(risk.get("band"))),
        ("Production reliability", _safe_text(metrics.get("production_reliability"), "Not available")),
        ("Funding readiness", _safe_text(metrics.get("funding_readiness"), "Not available")),
    ], (7.0 * cm, 10.0 * cm)))
    story.append(Paragraph("Main flagged issues", _STYLES["SmallBrand"]))
    _add_bullets(story, risk.get("flags") or ["No major client-facing flags were generated for this assessment."])
    _section_rule(story)

    story.append(Paragraph("9. Prepare", _STYLES["SectionBrand"]))
    story.append(Paragraph(
        "Prepare turns the screening findings into practical next actions for Panuka, the farm team, or supported SMEs.",
        _STYLES["BodyBrand"],
    ))
    _add_bullets(story, risk.get("recs") or [])
    story.append(Paragraph("Suggested review frequency", _STYLES["SmallBrand"]))
    _add_bullets(story, [
        "Review at the start of each planting cycle.",
        "Review before major irrigation or water-infrastructure decisions.",
        "Review greenhouse conditions more frequently during hotter periods.",
        "Review before financing, expansion, or major operational changes.",
    ])
    _section_rule(story)

    story.append(Paragraph("10. Image outputs", _STYLES["SectionBrand"]))
    story.append(Paragraph(
        "Each image is paired with a short explanation so that non-technical readers can understand what it shows and why it matters.",
        _STYLES["BodyBrand"],
    ))
    for payload in (image_payloads or []):
        _image_block(story, _safe_text(payload.get("title")), _safe_text(payload.get("description")), payload.get("bytes"))

    story.append(PageBreak())

    story.append(Paragraph("11. Historical plots and current charts", _STYLES["SectionBrand"]))
    story.append(Paragraph(
        "The plots below help explain how conditions have changed over time. Each chart is supported with a short description so the numbers are easier to interpret.",
        _STYLES["BodyBrand"],
    ))
    for payload in (chart_payloads or []):
        _chart_block(story, _safe_text(payload.get("title")), _safe_text(payload.get("description")), payload.get("bytes"))
    _section_rule(story)

    story.append(Paragraph("12. Ongoing monitoring and review", _STYLES["SectionBrand"]))
    _add_bullets(story, [
        "Use this report as a seasonal screening tool rather than a once-off document.",
        "Pair the report with field checks, irrigation records, pest scouting, and greenhouse observations.",
        "Update the assessment when rainfall conditions change materially or when production systems expand.",
        "Use the results to support incubation, advisory discussions, and funding-readiness conversations.",
    ])
    _section_rule(story)

    story.append(Paragraph("13. Detailed metrics appendix", _STYLES["SectionBrand"]))
    appendix_rows = sorted((str(k), _safe_text(v)) for k, v in metrics.items())
    story.append(_metric_table(appendix_rows, (6.0 * cm, 11.0 * cm)))

    doc.build(story, onFirstPage=_page_number, onLaterPages=_page_number)
    return buffer.getvalue()
