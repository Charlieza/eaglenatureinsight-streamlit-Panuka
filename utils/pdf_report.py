from io import BytesIO
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.utils import ImageReader


def _fmt(val, digits=2, suffix=""):
    if val is None:
        return "—"
    try:
        return f"{float(val):.{digits}f}{suffix}"
    except Exception:
        return str(val) if val not in [None, ""] else "—"


def _safe_rl_image(img_source, width_mm=None, height_mm=None):
    img_reader = ImageReader(img_source)
    orig_w, orig_h = img_reader.getSize()
    if width_mm is not None and height_mm is None:
        aspect = orig_h / orig_w
        height_mm = width_mm * aspect
    elif height_mm is not None and width_mm is None:
        aspect = orig_w / orig_h
        width_mm = height_mm * aspect
    elif width_mm is None and height_mm is None:
        width_mm = 60
        aspect = orig_h / orig_w
        height_mm = width_mm * aspect
    return Image(img_source, width=width_mm * mm, height=height_mm * mm)


def _section_with_optional_image(title, description, img_bytes, h_style, small_style, body_style):
    items = [Paragraph(title, h_style)]
    if description:
        items.append(Paragraph(description, small_style))
    if img_bytes is not None:
        try:
            items.append(_safe_rl_image(img_bytes, width_mm=175))
        except Exception:
            items.append(Paragraph("Image unavailable in this export.", body_style))
    else:
        items.append(Paragraph("Image unavailable in this export.", body_style))
    items.append(Spacer(1, 4 * mm))
    return KeepTogether(items)


def _portfolio_band(metrics):
    items = []
    rain = metrics.get("rain_anom_pct")
    lst = metrics.get("lst_mean")
    ndvi = metrics.get("ndvi_current")
    g_pct = metrics.get("greenhouse_pct")
    try:
        if rain is not None and float(rain) < -10:
            items.append("water uncertainty appears elevated")
    except Exception:
        pass
    try:
        if lst is not None and float(lst) > 30:
            items.append("heat pressure appears elevated")
    except Exception:
        pass
    try:
        if ndvi is not None and float(ndvi) < 0.25:
            items.append("vegetation condition is currently low")
    except Exception:
        pass
    try:
        if g_pct is not None and float(g_pct) > 0.5:
            items.append("part of the area may include protected farming")
    except Exception:
        pass
    if not items:
        return "The current screening does not point to one dominant pressure, so the site should be monitored as a portfolio of signals rather than through a single score."
    return "The current screening suggests that " + ", ".join(items[:-1]) + (" and " + items[-1] if len(items) > 1 else items[0]) + "."


def build_pdf_report(preset, category, hist_start, hist_end, metrics, risk, image_payloads, chart_payloads) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title_style", parent=styles["Title"], textColor=colors.HexColor("#163d63"), fontSize=20, leading=24, spaceAfter=8)
    h_style = ParagraphStyle("h_style", parent=styles["Heading2"], textColor=colors.HexColor("#163d63"), fontSize=13, leading=16, spaceAfter=4, spaceBefore=8)
    body_style = ParagraphStyle("body_style", parent=styles["BodyText"], fontSize=9.5, leading=12, spaceAfter=4)
    small_style = ParagraphStyle("small_style", parent=styles["BodyText"], fontSize=8.8, leading=11, textColor=colors.HexColor("#4b5563"), spaceAfter=4)
    box_style = ParagraphStyle("box_style", parent=styles["BodyText"], fontSize=9.2, leading=12, textColor=colors.HexColor("#111827"), spaceAfter=2)

    story = []
    logo_path = Path("assets/logo.png")
    if logo_path.exists():
        try:
            story.append(_safe_rl_image(str(logo_path), width_mm=42))
            story.append(Spacer(1, 3 * mm))
        except Exception:
            pass

    story.append(Paragraph("EagleNatureInsight | Panuka Pilot Report", title_style))
    story.append(Paragraph(f"Assessment date: {date.today().isoformat()}", body_style))
    story.append(Paragraph(f"Pilot site: {preset}", body_style))
    story.append(Paragraph(f"Pilot category: {category}", body_style))
    story.append(Paragraph(f"Historical range: {hist_start} to {hist_end}", body_style))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("Executive summary", h_style))
    story.append(Paragraph(
        "This report translates satellite and environmental screening into practical farm intelligence for Panuka. It is designed to support agribusiness decision-making, SME incubation, climate-risk conversations, and finance-readiness discussions while keeping the TNFD LEAP structure clear and accessible.",
        body_style,
    ))
    story.append(Paragraph(_portfolio_band(metrics), body_style))

    summary_data = [
        ["Metric", "Value"],
        ["Nature risk", f'{risk.get("score", "—")}/100 ({risk.get("band", "—")})'],
        ["Area analysed", _fmt(metrics.get("area_ha"), 1, " ha")],
        ["Current vegetation (NDVI)", _fmt(metrics.get("ndvi_current"), 3)],
        ["Vegetation trend", _fmt(metrics.get("ndvi_trend"), 3)],
        ["Rainfall anomaly", _fmt(metrics.get("rain_anom_pct"), 1, "%")],
        ["Tree cover", _fmt(metrics.get("tree_pct"), 1, "%")],
        ["Surface water occurrence", _fmt(metrics.get("water_occ"), 1)],
        ["Recent land surface temperature", _fmt(metrics.get("lst_mean"), 1, " °C")],
        ["Greenhouse share", _fmt(metrics.get("greenhouse_pct"), 1, "%")],
        ["Forest loss", _fmt(metrics.get("forest_loss_pct"), 1, "%")],
    ]
    summary_table = Table(summary_data, colWidths=[64 * mm, 106 * mm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#163d63")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d1d5db")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LEADING", (0, 0), (-1, -1), 11),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(summary_table)

    story.append(Paragraph("How this pilot responds to Panuka's SME engagement priorities", h_style))
    bullets = [
        "Accessible: the results are written in plain language so non-specialists can understand the practical meaning of the signals.",
        "Automated: the screening combines farm location data with satellite datasets to reduce manual work and speed up first-pass analysis.",
        "Actionable: the outputs point to water reliability, vegetation condition, heat, greenhouse conditions, irrigation demand, and farm resilience.",
        "Relevant to incubation and finance: the report highlights environmental factors that can affect production reliability and support bankability discussions with funders and partners.",
        "Suitable for small farms: basic coordinates or boundaries are enough for an initial assessment, making it easier to scale across SME portfolios.",
    ]
    for b in bullets:
        story.append(Paragraph(f"• {b}", body_style))

    story.append(Paragraph("Greenhouse and open-field interpretation", h_style))
    g_pct = metrics.get("greenhouse_pct")
    try:
        g_pct_val = float(g_pct or 0)
    except Exception:
        g_pct_val = 0.0
    if g_pct_val > 0.5:
        story.append(Paragraph(
            f"Satellite screening suggests that approximately {_fmt(g_pct_val,1,' %')} of the selected area may contain protected farming structures. These areas should be interpreted differently from open-field zones because greenhouse performance is more sensitive to heat build-up, humidity, ventilation, irrigation reliability, and pest pressure.",
            body_style,
        ))
    else:
        story.append(Paragraph(
            "Satellite screening does not show a strong greenhouse signal in the selected area. The outputs should therefore mainly be interpreted as open-field and surrounding-landscape screening, while still recognising that small protected structures may not always be fully visible from satellite imagery.",
            body_style,
        ))
    story.append(Paragraph(
        "Greenhouse-related outputs in this report are screening proxies from satellite and climate context. They are useful for prioritising inspection and management but do not replace in-greenhouse sensors, field scouting, humidity logging, pest traps, or soil and pH measurements.",
        small_style,
    ))

    story.append(Paragraph("TNFD LEAP alignment", h_style))
    story.append(Paragraph("<b>Locate:</b> define the farm area, identify surrounding land cover, and understand where the operation interfaces with nature.", body_style))
    story.append(Paragraph("<b>Evaluate:</b> review dependencies on water, vegetation, soil stability, and climate, alongside visible pressures such as vegetation decline or limited surface water.", body_style))
    story.append(Paragraph("<b>Assess:</b> interpret the signals as practical farm risks and opportunities rather than relying on a single metric alone.", body_style))
    story.append(Paragraph("<b>Prepare:</b> translate the findings into next actions, monitoring priorities, and conversations with incubated SMEs, lenders, insurers, and partners.", body_style))
    story.append(Paragraph(
        "This responds directly to the TNFD discussion points by reducing jargon, telling more of a story, showing dependencies and impacts clearly, and connecting the outputs to the business bottom line.",
        body_style,
    ))

    story.append(Paragraph("Plain-language reading guide", h_style))
    for line in [
        "Greener vegetation images usually suggest stronger plant cover. Redder vegetation images usually suggest lower or more stressed vegetation.",
        "Vegetation change maps use red for decline and green for improvement.",
        "Rainfall anomaly compares recent rainfall with a longer historical baseline; negative values can mean more water uncertainty.",
        "These outputs are first-pass screening outputs. They help identify where closer review or field verification may be most useful.",
    ]:
        story.append(Paragraph(f"• {line}", body_style))

    if risk.get("flags"):
        story.append(Paragraph("Key risk signals", h_style))
        for flag in risk["flags"]:
            story.append(Paragraph(f"• {flag}", body_style))

    if risk.get("recs"):
        story.append(Paragraph("Recommended next actions", h_style))
        for rec in risk["recs"]:
            story.append(Paragraph(f"• {rec}", body_style))
        story.append(Paragraph("Suggested use frequency: seasonally for farm decisions, after major weather events for rapid screening, and annually for portfolio review and finance-readiness conversations.", body_style))

    if image_payloads:
        story.append(PageBreak())
        story.append(Paragraph("Image outputs", h_style))
        for item in image_payloads:
            story.append(_section_with_optional_image(item.get("title", "Image"), item.get("description", ""), item.get("bytes"), h_style, small_style, body_style))

    if chart_payloads:
        story.append(PageBreak())
        story.append(Paragraph("Historical plots and charts", h_style))
        for item in chart_payloads:
            story.append(_section_with_optional_image(item.get("title", "Chart"), item.get("description", ""), item.get("bytes"), h_style, small_style, body_style))

    story.append(PageBreak())
    story.append(Paragraph("Detailed metrics", h_style))
    detail_rows = [["Metric", "Value"]]
    for label, val in [
        ("Area analysed", _fmt(metrics.get("area_ha"),1," ha")),
        ("Current NDVI", _fmt(metrics.get("ndvi_current"),3)),
        ("Vegetation trend", _fmt(metrics.get("ndvi_trend"),3)),
        ("Rainfall anomaly", _fmt(metrics.get("rain_anom_pct"),1,"%")),
        ("Recent LST mean", _fmt(metrics.get("lst_mean"),1," °C")),
        ("Tree cover", _fmt(metrics.get("tree_pct"),1,"%")),
        ("Cropland", _fmt(metrics.get("cropland_pct"),1,"%")),
        ("Built-up", _fmt(metrics.get("built_pct"),1,"%")),
        ("Surface water occurrence", _fmt(metrics.get("water_occ"),1)),
        ("Forest loss", _fmt(metrics.get("forest_loss_pct"),1,"%")),
        ("Greenhouse area", _fmt(metrics.get("greenhouse_ha"),1," ha")),
        ("Greenhouse share", _fmt(metrics.get("greenhouse_pct"),1,"%")),
    ]:
        detail_rows.append([label, val])
    detail_table = Table(detail_rows, colWidths=[70 * mm, 100 * mm])
    detail_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#163d63")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d1d5db")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(detail_table)

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
