from __future__ import annotations

import io
import math
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
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

IMAGE_LABELS = {
    "satellite_url": ("Satellite image with polygon", "A natural-colour satellite image of the selected site. This helps the reader see the farm layout, surrounding land use, and the exact boundary used for the assessment."),
    "ndvi_url": ("NDVI image with polygon", "This vegetation-condition image helps show where plant cover is stronger or weaker. Greener areas usually indicate stronger vegetation, while redder areas may suggest stress, bare ground, or sparse cover."),
    "landcover_url": ("Land-cover image with polygon", "This image shows the main land-cover classes inside the site, such as cropland, built-up areas, tree cover, bare ground, or water. It helps explain the production landscape and the surrounding ecological setting."),
    "veg_change_url": ("Vegetation change map with polygon", "This map compares earlier and more recent vegetation conditions. Green usually means vegetation has improved, while red usually means vegetation has weakened over time."),
    "forest_loss_url": ("Forest loss map with polygon", "This map highlights areas where forest loss has been detected historically. It helps show whether the wider landscape has experienced vegetation or habitat pressure."),
}

PLOT_LABELS = {
    "ndvi_plot_path": ("Historical vegetation trend", "This chart shows how vegetation condition has changed over time. It helps indicate whether the farm or surrounding landscape is becoming greener, more stressed, or remaining stable."),
    "rain_plot_path": ("Historical rainfall trend", "This chart shows how rainfall has varied over time. It helps indicate water certainty, climate variability, and possible irrigation pressure."),
    "lst_plot_path": ("Historical temperature trend", "This chart shows land surface temperature over time. It helps indicate heat stress conditions that may affect crops, livestock, workers, infrastructure, or greenhouse operations."),
    "forest_plot_path": ("Historical forest-loss trend", "This chart shows forest loss over time where relevant. It helps indicate landscape pressure and ecological change in the broader area."),
    "water_plot_path": ("Historical water-presence trend", "This chart shows changes in visible water presence over time. It helps indicate water availability context and possible exposure to water stress."),
    "landcover_plot_path": ("Current land-cover composition", "This chart summarises the current land-cover mix inside the assessment boundary, such as cropland, tree cover, built-up areas, and water."),
}


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleBrand", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=BRAND["primary"], spaceAfter=8))
    styles.add(ParagraphStyle(name="SubBrand", parent=styles["BodyText"], fontName="Helvetica", fontSize=10, leading=14, textColor=BRAND["subtext"], spaceAfter=12))
    styles.add(ParagraphStyle(name="SectionBrand", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=BRAND["primary"], spaceBefore=8, spaceAfter=6))
    styles.add(ParagraphStyle(name="SmallBrand", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=BRAND["text"], spaceBefore=6, spaceAfter=4))
    styles.add(ParagraphStyle(name="BodyBrand", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13, textColor=BRAND["text"], spaceAfter=6, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name="MutedBrand", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.5, leading=12, textColor=BRAND["subtext"], spaceAfter=5))
    styles.add(ParagraphStyle(name="CenterMuted", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.5, leading=12, textColor=BRAND["subtext"], alignment=TA_CENTER, spaceAfter=5))
    return styles


_STYLES = _styles()


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


def _safe_text(value: Any, fallback: str = "Not available") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _fetch_image(url: str) -> Optional[io.BytesIO]:
    if not url:
        return None
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        return io.BytesIO(r.content)
    except Exception:
        return None


def _fit_image(source: Any, max_width: float, max_height: float) -> Optional[Image]:
    try:
        img = Image(source)
        img._restrictSize(max_width, max_height)
        return img
    except Exception:
        return None


def _logo_image(logo_path: Optional[str], max_width: float = 4.0 * cm, max_height: float = 2.2 * cm) -> Optional[Image]:
    if not logo_path:
        return None
    return _fit_image(logo_path, max_width, max_height)


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


def _image_block(story: List[Any], title: str, description: str, source: Any, is_url: bool = False) -> None:
    img_data = _fetch_image(source) if is_url else source
    img = _fit_image(img_data, 17.5 * cm, 10.0 * cm) if img_data else None
    story.append(Paragraph(title, _STYLES["SmallBrand"]))
    story.append(Paragraph(description, _STYLES["MutedBrand"]))
    if img:
        story.append(img)
        story.append(Spacer(1, 0.15 * cm))
    else:
        story.append(Paragraph("Image not available in this export.", _STYLES["MutedBrand"]))
    story.append(Spacer(1, 0.15 * cm))


def _plot_block(story: List[Any], title: str, description: str, plot_path: Optional[str]) -> None:
    story.append(Paragraph(title, _STYLES["SmallBrand"]))
    story.append(Paragraph(description, _STYLES["MutedBrand"]))
    if plot_path:
        img = _fit_image(plot_path, 17.5 * cm, 8.8 * cm)
        if img:
            story.append(img)
            story.append(Spacer(1, 0.15 * cm))
            return
    story.append(Paragraph("Plot not available in this export.", _STYLES["MutedBrand"]))
    story.append(Spacer(1, 0.15 * cm))


def _greenhouse_table(metrics: Dict[str, Any]) -> Table:
    rows = [
        ("Greenhouse detected", _safe_text(metrics.get("greenhouse_detected"), "No")),
        ("Estimated greenhouse area", fmt_num(metrics.get("greenhouse_ha"), 2, " ha")),
        ("Estimated greenhouse share of site", fmt_num(metrics.get("greenhouse_pct"), 1, "%")),
        ("Greenhouse heat stress", _safe_text(metrics.get("greenhouse_heat_risk"))),
        ("Greenhouse humidity risk", _safe_text(metrics.get("greenhouse_humidity_risk"))),
        ("Greenhouse pest risk", _safe_text(metrics.get("greenhouse_pest_risk"))),
        ("Irrigation demand", _safe_text(metrics.get("irrigation_demand"))),
    ]
    return _metric_table(rows, (7.2 * cm, 9.8 * cm))


def _financial_table(metrics: Dict[str, Any], risk: Dict[str, Any]) -> Table:
    rows = [
        ("Production reliability", _safe_text(metrics.get("production_reliability"), "Not available")),
        ("Funding readiness", _safe_text(metrics.get("funding_readiness"), "Not available")),
        ("Nature risk score", _safe_text(risk.get("score"), "Not available")),
        ("Risk band", _safe_text(risk.get("band"), "Not available")),
    ]
    return _metric_table(rows, (7.2 * cm, 9.8 * cm))


def _page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(BRAND["muted"])
    canvas.drawRightString(PAGE_WIDTH - 1.6 * cm, 1.2 * cm, f"Page {doc.page}")
    canvas.restoreState()


def build_panuka_pdf_report(output_path: str, report_data: Dict[str, Any], logo_path: Optional[str] = None) -> str:
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.5 * cm,
        title="EagleNatureInsight Panuka Pilot Report",
        author="OpenAI",
    )

    metrics: Dict[str, Any] = report_data.get("metrics", {}) or {}
    risk: Dict[str, Any] = report_data.get("risk", {}) or {}
    evaluate: Dict[str, Any] = report_data.get("evaluate", {}) or {}
    overview: Dict[str, Any] = report_data.get("overview", {}) or {}

    story: List[Any] = []
    logo = _logo_image(logo_path)
    if logo:
        logo.hAlign = "LEFT"
        story.append(logo)
        story.append(Spacer(1, 0.15 * cm))

    story.append(Paragraph("EagleNatureInsight | Panuka Pilot", _STYLES["TitleBrand"]))
    story.append(Paragraph("TNFD-aligned agribusiness screening report for Panuka AgriBiz Hub. This report translates satellite and environmental signals into plain-language insights for farm operations, greenhouse conditions, water planning, climate resilience, and SME financing discussions.", _STYLES["SubBrand"]))

    site_name = _safe_text(report_data.get("preset"), "Panuka site")
    hist_start = _safe_text(report_data.get("hist_start"), "Not available")
    hist_end = _safe_text(report_data.get("hist_end"), "Not available")

    story.append(Paragraph("1. Executive summary", _STYLES["SectionBrand"]))
    for line in [
        f"This report summarises environmental and nature-related screening results for <b>{site_name}</b>.",
        f"The historical review period used in this assessment is <b>{hist_start} to {hist_end}</b>.",
        "The purpose of the report is to help Panuka and supported SMEs understand practical questions such as water certainty, vegetation condition, heat stress, greenhouse conditions, and possible operational risks.",
        "The report follows the TNFD LEAP structure and translates technical outputs into practical agribusiness language.",
    ]:
        story.append(Paragraph(line, _STYLES["BodyBrand"]))

    story.append(Paragraph("Top takeaways", _STYLES["SmallBrand"]))
    top_takeaways = overview.get("top_findings") or report_data.get("top_findings") or []
    if top_takeaways:
        _add_bullets(story, top_takeaways)
    else:
        _add_bullets(story, [
            "This site should be read as a practical farm and SME decision-support assessment rather than a technical remote-sensing output only.",
            "Water, vegetation, heat, and land-cover conditions should be reviewed together rather than in isolation.",
            "Where greenhouse activity is detected, greenhouse-specific risk conditions should be prioritised alongside open-field conditions.",
        ])

    _section_rule(story)
    story.append(Paragraph("2. Reading guide and defined abbreviations", _STYLES["SectionBrand"]))
    story.append(Paragraph("This report avoids jargon as far as possible. Where abbreviations appear, they are defined below so that non-technical readers can follow the report easily.", _STYLES["BodyBrand"]))
    story.append(_metric_table(sorted(ABBREVIATIONS.items()), (3.2 * cm, 13.8 * cm)))

    _section_rule(story)
    story.append(Paragraph("3. Panuka SME engagement priorities addressed in this report", _STYLES["SectionBrand"]))
    _add_bullets(story, [
        "Water certainty and irrigation pressure",
        "Rainfall variability and climate uncertainty",
        "Protected farming versus open-field farming conditions",
        "Soil stress and land condition screening",
        "Pest-risk conditions and greenhouse humidity context",
        "Usefulness for small farmers and incubation support",
        "Financial resilience and funding-readiness conversations",
        "Plain-language TNFD LEAP interpretation",
    ])

    _section_rule(story)
    story.append(Paragraph("4. Overview metrics", _STYLES["SectionBrand"]))
    overview_rows = [
        ("Panuka pilot site", site_name),
        ("Pilot category", _safe_text(report_data.get("category"), "Agriculture / Agribusiness")),
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
    ]
    story.append(_metric_table(overview_rows, (7.2 * cm, 9.8 * cm)))

    _section_rule(story)
    story.append(Paragraph("5. LEAP summary", _STYLES["SectionBrand"]))
    for heading, desc in [
        ("Locate", "The site and surrounding production landscape were defined using the selected point or polygon, then screened for land cover, vegetation, water context, and surrounding environmental conditions."),
        ("Evaluate", "The system reviewed nature dependencies, visible pressures, greenhouse conditions where detected, and practical business meaning for water, heat, vegetation, and operational resilience."),
        ("Assess", "The system translated those signals into a plain-language risk view, including physical risk conditions such as water stress, heat stress, vegetation stress, and broader landscape pressure."),
        ("Prepare", "The system generated practical next actions, suggested review frequency, and business-oriented recommendations that Panuka or supported SMEs can test and refine."),
    ]:
        story.append(Paragraph(f"<b>{heading}</b>: {desc}", _STYLES["BodyBrand"]))

    _section_rule(story)
    story.append(Paragraph("6. Locate", _STYLES["SectionBrand"]))
    story.append(Paragraph("Locate explains where the farm interacts with nature. It shows the production setting, surrounding land cover, visible water context, and the physical footprint used for the assessment.", _STYLES["BodyBrand"]))
    story.append(_metric_table([
        ("Area of interest", fmt_num(metrics.get("area_ha"), 2, " ha")),
        ("Tree cover", fmt_num(metrics.get("tree_pct"), 1, "%")),
        ("Cropland", fmt_num(metrics.get("cropland_pct"), 1, "%")),
        ("Built-up", fmt_num(metrics.get("built_pct"), 1, "%")),
        ("Surface-water occurrence", fmt_num(metrics.get("water_occ"), 1)),
    ], (7.2 * cm, 9.8 * cm)))

    _section_rule(story)
    story.append(Paragraph("7. Evaluate", _STYLES["SectionBrand"]))
    story.append(Paragraph(evaluate.get("narrative") or "Evaluate reviews how the farm depends on nature, what pressures may be visible, what greenhouse conditions may matter, and what the indicators suggest for practical farm management.", _STYLES["BodyBrand"]))
    story.append(Paragraph("Dependencies on nature", _STYLES["SmallBrand"]))
    _add_bullets(story, evaluate.get("dependencies") or [])
    story.append(Paragraph("Possible impacts and pressures", _STYLES["SmallBrand"]))
    _add_bullets(story, evaluate.get("impacts") or [])
    story.append(Paragraph("What the indicators are suggesting", _STYLES["SmallBrand"]))
    _add_bullets(story, evaluate.get("signals") or [])
    story.append(Paragraph("Exposure summary", _STYLES["SmallBrand"]))
    exposure_rows = [(item.get("label", "Exposure"), f'{_safe_text(item.get("value"))} — {_safe_text(item.get("subtext"))}') for item in (evaluate.get("exposureCards") or [])]
    if exposure_rows:
        story.append(_metric_table(exposure_rows, (7.2 * cm, 9.8 * cm)))
    story.append(Paragraph("Why this matters", _STYLES["SmallBrand"]))
    story.append(Paragraph(_safe_text(evaluate.get("whyItMatters")), _STYLES["BodyBrand"]))

    _section_rule(story)
    story.append(Paragraph("8. Greenhouse and protected-farming screening", _STYLES["SectionBrand"]))
    story.append(Paragraph("This section addresses the Panuka discussion about protected farming. Greenhouse-related outputs are screening proxies from satellite and contextual data. They are useful for prioritising field checks, but they do not replace in-greenhouse sensors, humidity sensors, pest traps, or direct agronomic inspection.", _STYLES["BodyBrand"]))
    story.append(_greenhouse_table(metrics))
    story.append(Paragraph("How to read this section: greenhouse heat stress can indicate likely cooling or shading pressure; greenhouse humidity risk can indicate conditions that may favour disease or ventilation needs; greenhouse pest risk can indicate whether heat, vegetation, and moisture conditions may support closer inspection.", _STYLES["MutedBrand"]))

    _section_rule(story)
    story.append(Paragraph("9. Assess", _STYLES["SectionBrand"]))
    story.append(Paragraph("Assess translates environmental signals into a practical risk view for the farm and SME context. This is intended as a screening view, not a final agronomic or financial determination.", _STYLES["BodyBrand"]))
    story.append(_financial_table(metrics, risk))
    story.append(Paragraph("Main flagged issues", _STYLES["SmallBrand"]))
    _add_bullets(story, risk.get("flags") or ["No major automated flags were triggered in the current rule set."])

    _section_rule(story)
    story.append(Paragraph("10. Prepare", _STYLES["SectionBrand"]))
    story.append(Paragraph("Prepare turns the screening findings into actions Panuka, its farm team, or supported SMEs can test. These recommendations are written to support decision-making, incubation support, and funding-readiness conversations.", _STYLES["BodyBrand"]))
    _add_bullets(story, risk.get("recs") or [])
    suggested_frequency = report_data.get("assessment_frequency") or "Seasonal review, with additional review before major planting, irrigation, or financing decisions."
    story.append(Paragraph("Suggested use frequency", _STYLES["SmallBrand"]))
    story.append(Paragraph(_safe_text(suggested_frequency), _STYLES["BodyBrand"]))

    _section_rule(story)
    story.append(Paragraph("11. Bankability and SME support perspective", _STYLES["SectionBrand"]))
    _add_bullets(story, [
        "Use water reliability, production reliability, and heat stress outputs to support conversations about climate and operational stability.",
        "Use greenhouse and open-field differences to show that the business understands where different production risks sit.",
        "Use vegetation and rainfall trends to explain longer-term resilience, not just current conditions.",
        "Use the report as a structured screening document for incubation, advisory support, or discussions with funders and partners.",
    ])

    _section_rule(story)
    story.append(Paragraph("12. Image outputs", _STYLES["SectionBrand"]))
    story.append(Paragraph("Each image below is paired with a short explanation so that non-technical readers can understand what it shows and why it matters.", _STYLES["BodyBrand"]))
    for key, (title, desc) in IMAGE_LABELS.items():
        _image_block(story, title, desc, report_data.get(key), is_url=True)

    story.append(PageBreak())
    story.append(Paragraph("13. Historical plots and current charts", _STYLES["SectionBrand"]))
    story.append(Paragraph("The plots below help explain trends over time. Each one is described in plain language so the reader can understand what changes may matter for farm decisions.", _STYLES["BodyBrand"]))
    for key, (title, desc) in PLOT_LABELS.items():
        _plot_block(story, title, desc, report_data.get(key))

    _section_rule(story)
    story.append(Paragraph("14. TNFD meeting points addressed by this report", _STYLES["SectionBrand"]))
    _add_bullets(story, [
        "Less jargon: the report uses plain-language interpretations and defines abbreviations.",
        "More narrative than raw data: each section explains what the trend means and why it matters.",
        "Dependencies are made explicit: water, soil, vegetation, climate, and greenhouse conditions are discussed as business dependencies.",
        "A portfolio of indicators is used rather than a single score only.",
        "Numbers are supported by text, so a reader does not need technical background to interpret the outputs.",
        "The report links environmental conditions to business resilience, operations, and funding readiness.",
        "The LEAP structure remains clear and visible throughout the document.",
    ])

    _section_rule(story)
    story.append(Paragraph("15. Detailed metrics appendix", _STYLES["SectionBrand"]))
    appendix_rows = sorted((str(k), _safe_text(v)) for k, v in metrics.items())
    story.append(_metric_table(appendix_rows, (6.0 * cm, 11.0 * cm)))

    doc.build(story, onFirstPage=_page_number, onLaterPages=_page_number)
    return output_path


def build_pdf_report(output_path: str, report_data: Dict[str, Any], logo_path: Optional[str] = None) -> str:
    return build_panuka_pdf_report(output_path=output_path, report_data=report_data, logo_path=logo_path)
