from pathlib import Path
from datetime import date
from io import BytesIO

import pandas as pd
import plotly.express as px
import streamlit as st
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
import matplotlib.pyplot as plt
import requests

from utils.ee_helpers import (
    initialize_ee_from_secrets,
    geojson_to_ee_geometry,
    point_buffer_to_ee_geometry,
    compute_metrics,
    satellite_with_polygon,
    ndvi_with_polygon,
    landcover_with_polygon,
    forest_loss_with_polygon,
    vegetation_change_with_polygon,
    image_thumb_url,
    landsat_annual_ndvi_collection,
    annual_rain_collection,
    annual_lst_collection,
    forest_loss_by_year_collection,
    water_history_collection,
    landcover_feature_collection,
)
from utils.scoring import build_risk_and_recommendations
from utils.pdf_report import build_pdf_report


st.set_page_config(page_title="EagleNatureInsight", layout="wide")

APP_TITLE = "EagleNatureInsight | Panuka Pilot"
APP_SUBTITLE = "TNFD LEAP agribusiness dashboard for Panuka AgriBiz Hub"
APP_TAGLINE = "Locate • Evaluate • Assess • Prepare"

CURRENT_YEAR = date.today().year
LAST_FULL_YEAR = CURRENT_YEAR - 1

LOGO_PATH = Path("assets/logo.png")

PRESET_TO_CATEGORY = {
    "Panuka Site 1": "Agriculture / Agribusiness",
    "Panuka Site 2": "Agriculture / Agribusiness",
}

PRESET_TO_LOCATION = {
    "Panuka Site 1": {"lat": -15.251194, "lon": 28.144500, "buffer_m": 1200, "zoom": 12},
    "Panuka Site 2": {"lat": -15.251472, "lon": 28.147417, "buffer_m": 1200, "zoom": 12},
}

PRESETS = [
    "Select Panuka Site",
    "Panuka Site 1",
    "Panuka Site 2",
]

CATEGORIES = [
    "Agriculture / Agribusiness",
]


def init_state():
    defaults = {
        "preset_selector": "Select Panuka Site",
        "active_preset": "Select Panuka Site",
        "category_selector": "Agriculture / Agribusiness",
        "lat_input": "",
        "lon_input": "",
        "buffer_input": 1000,
        "map_center": [-15.251194, 28.144500],
        "map_zoom": 12,
        "draw_mode": "Draw polygon",
        "last_drawn_geojson": None,
        "report_payload": None,
        "results_payload": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def apply_preset(preset: str):
    st.session_state["active_preset"] = preset

    if preset in PRESET_TO_CATEGORY:
        st.session_state["category_selector"] = PRESET_TO_CATEGORY[preset]

    if preset in PRESET_TO_LOCATION:
        loc = PRESET_TO_LOCATION[preset]
        st.session_state["lat_input"] = str(loc["lat"])
        st.session_state["lon_input"] = str(loc["lon"])
        st.session_state["buffer_input"] = int(loc["buffer_m"])
        st.session_state["map_center"] = [loc["lat"], loc["lon"]]
        st.session_state["map_zoom"] = loc["zoom"]


def preset_changed():
    preset = st.session_state["preset_selector"]
    st.session_state["active_preset"] = preset
    if preset != "Select Panuka Site":
        apply_preset(preset)
    st.rerun()


def build_map(center, zoom, draw_mode, lat=None, lon=None, buffer_m=None, existing_geojson=None):
    m = folium.Map(
        location=center,
        zoom_start=zoom,
        min_zoom=5,
        control_scale=True,
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri Satellite",
    )

    Draw(
        export=False,
        draw_options={
            "polyline": False,
            "rectangle": True,
            "polygon": True,
            "circle": False,
            "marker": False,
            "circlemarker": False,
        },
        edit_options={"edit": True, "remove": True},
    ).add_to(m)

    if existing_geojson:
        folium.GeoJson(
            existing_geojson,
            style_function=lambda x: {
                "color": "#ff0000",
                "weight": 3,
                "fillOpacity": 0.05,
            },
        ).add_to(m)

    active_name = None
    active_lat = None
    active_lon = None
    try:
        if lat not in [None, "", "None"] and lon not in [None, "", "None"]:
            active_lat = float(lat)
            active_lon = float(lon)
    except (TypeError, ValueError):
        active_lat = None
        active_lon = None

    site_points = [
        ("Panuka Site 1", PRESET_TO_LOCATION["Panuka Site 1"]["lat"], PRESET_TO_LOCATION["Panuka Site 1"]["lon"]),
        ("Panuka Site 2", PRESET_TO_LOCATION["Panuka Site 2"]["lat"], PRESET_TO_LOCATION["Panuka Site 2"]["lon"]),
    ]

    fg = folium.FeatureGroup(name="Panuka pilot sites")
    bounds = []
    for name, plat, plon in site_points:
        bounds.append([plat, plon])
        is_active = active_lat is not None and active_lon is not None and abs(active_lat - plat) < 0.0008 and abs(active_lon - plon) < 0.0008
        if is_active:
            active_name = name
            folium.CircleMarker(
                location=[plat, plon],
                radius=14,
                color="#60a5fa",
                weight=2,
                fill=True,
                fill_color="#93c5fd",
                fill_opacity=0.35,
                opacity=0.8,
                popup=folium.Popup(f"<b>{name}</b><br>Selected site", max_width=220),
                tooltip=f"{name} (selected)",
            ).add_to(fg)

        folium.CircleMarker(
            location=[plat, plon],
            radius=9 if is_active else 7,
            color="#163d63" if is_active else "#1f8f5f",
            weight=3 if is_active else 2,
            fill=True,
            fill_color="#163d63" if is_active else "#1f8f5f",
            fill_opacity=0.95,
            popup=folium.Popup(f"<b>{name}</b>", max_width=220),
            tooltip=name,
        ).add_to(fg)

    fg.add_to(m)

    if draw_mode == "Enter coordinates" and active_lat is not None and active_lon is not None:
        folium.Circle(
            [active_lat, active_lon],
            radius=float(buffer_m or 1000),
            color="#ff0000",
            weight=2,
            fill=False,
        ).add_to(m)

    if len(bounds) == 2:
        m.fit_bounds(bounds, padding=(35, 35))
        if active_name is not None:
            m.location = [active_lat, active_lon]
            m.options["zoom"] = min(zoom, 12)

    return m

def extract_drawn_geometry(map_data):
    if not map_data:
        return None
    drawings = map_data.get("all_drawings") or []
    if not drawings:
        return None
    return drawings[-1]


def get_geometry_payload(drawn_geojson, lat, lon, buffer_m, mode):
    if mode == "Draw polygon":
        if drawn_geojson:
            return "Polygon captured from map drawing.", drawn_geojson, geojson_to_ee_geometry(drawn_geojson)
        return "No polygon drawn yet.", None, None

    try:
        lat_val = float(lat)
        lon_val = float(lon)
        geom = point_buffer_to_ee_geometry(lat_val, lon_val, float(buffer_m))
        payload = {
            "type": "PointBuffer",
            "lat": lat_val,
            "lon": lon_val,
            "buffer_m": float(buffer_m),
        }
        return (
            f"Point entered at ({lat_val:.5f}, {lon_val:.5f}) with {buffer_m} m buffer.",
            payload,
            geom,
        )
    except (TypeError, ValueError):
        return "Please enter valid latitude and longitude.", None, None


def fc_to_dataframe(fc) -> pd.DataFrame:
    info = fc.getInfo()
    rows = []
    for feature in info.get("features", []):
        props = feature.get("properties", {})
        rows.append(props)
    return pd.DataFrame(rows)


def prep_year_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if "value" in df.columns:
        df = df[df["value"].notna()].copy()
    if "year" in df.columns:
        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        df = df[df["year"].notna()].copy()
        df["year"] = df["year"].astype(int)
    return df.sort_values("year")


def metric_card(label: str, value: str, subtext: str = ""):
    st.markdown(
        f"""
        <div style="padding:14px;border:1px solid #e5e7eb;border-radius:18px;background:#ffffff;height:116px;box-shadow:0 6px 18px rgba(17,24,39,0.06);">
            <div style="font-size:12px;color:#6b7280;">{label}</div>
            <div style="font-size:28px;font-weight:700;color:#111827;margin-top:6px;">{value}</div>
            <div style="font-size:11px;color:#6b7280;margin-top:5px;">{subtext}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def fmt_num(val, digits=1, suffix=""):
    if val is None:
        return "—"
    try:
        return f"{float(val):.{digits}f}{suffix}"
    except Exception:
        return "—"



def exposure_level(value, low_bad, low_threshold, high_threshold):
    if value is None:
        return "Unknown"
    try:
        v = float(value)
    except Exception:
        return "Unknown"
    if low_bad:
        if v <= low_threshold:
            return "High"
        if v <= high_threshold:
            return "Moderate"
        return "Low"
    if v >= high_threshold:
        return "High"
    if v >= low_threshold:
        return "Moderate"
    return "Low"


def build_overview_content(preset, category, metrics, risk):
    findings = []
    ndvi_current = metrics.get("ndvi_current")
    rain_anom = metrics.get("rain_anom_pct")
    ndvi_trend = metrics.get("ndvi_trend")

    if ndvi_current is not None:
        try:
            if float(ndvi_current) < 0.25:
                findings.append("Current vegetation condition is low and may indicate stressed or sparse vegetation in the assessed area.")
            elif float(ndvi_current) < 0.45:
                findings.append("Current vegetation condition is moderate, suggesting mixed vegetation performance across the site.")
            else:
                findings.append("Current vegetation condition is relatively strong, suggesting healthier vegetation cover in the assessed area.")
        except Exception:
            pass

    if ndvi_trend is not None:
        try:
            if float(ndvi_trend) < -0.03:
                findings.append("Historical vegetation trend is declining, which may point to growing ecological or land-management pressure.")
            elif float(ndvi_trend) > 0.03:
                findings.append("Historical vegetation trend is improving, which may reflect better ground cover or recovering vegetation.")
        except Exception:
            pass

    if rain_anom is not None:
        try:
            if float(rain_anom) < -10:
                findings.append("Recent rainfall is below the long-term baseline, which may increase water uncertainty for farming activities.")
            elif float(rain_anom) > 10:
                findings.append("Recent rainfall is above the long-term baseline, which may improve water availability but can also shift runoff and pest conditions.")
        except Exception:
            pass

    if not findings:
        findings.append("The site shows a mix of environmental signals that should be monitored over time rather than interpreted from a single indicator.")

    narrative = (
        "This overview gives a plain-language summary of the Panuka pilot site, highlighting the most important nature-related signals "
        "for agribusiness screening and decision support. It is designed to help users quickly understand what the site depends on, "
        "what may be changing, and where further attention may be needed."
    )

    business_relevance = (
        "For Panuka, these results matter because water reliability, vegetation condition, and rainfall variability can affect farm resilience, "
        "training and incubation support, production planning, and the way environmental performance is communicated to partners or funders."
    )

    return {
        "narrative": narrative,
        "findings": findings[:3],
        "business_relevance": business_relevance,
    }






def build_tnfd_matrix(metrics):
    return [
        {
            "indicator": "Water availability",
            "value": fmt_num(metrics.get("water_occ"), 1),
            "meaning": "Low visible surface water can increase dependence on irrigation, boreholes, or storage.",
            "response": "Review water storage, irrigation planning, and groundwater reliance.",
        },
        {
            "indicator": "Heat stress",
            "value": fmt_num(metrics.get("lst_mean"), 1, " °C"),
            "meaning": "Elevated temperature can increase crop stress, evaporation, and cooling needs.",
            "response": "Monitor heat conditions and consider shading or ventilation where needed.",
        },
        {
            "indicator": "Vegetation condition",
            "value": fmt_num(metrics.get("ndvi_current"), 3),
            "meaning": "Vegetation condition gives a simple signal of plant cover strength and possible stress.",
            "response": "Use together with field checks, crop observations, and soil moisture review.",
        },
        {
            "indicator": "Rainfall variability",
            "value": fmt_num(metrics.get("rain_anom_pct"), 1, "%"),
            "meaning": "Rainfall conditions influence irrigation demand, water certainty, and seasonal planning.",
            "response": "Review seasonal planning and irrigation scheduling.",
        },
        {
            "indicator": "Land condition",
            "value": fmt_num(metrics.get("forest_loss_pct"), 1, "%"),
            "meaning": "Landscape change can affect ecosystem stability and longer-term production conditions.",
            "response": "Monitor surrounding land-use change and maintain ecological buffers where possible.",
        },
    ]


def build_overall_environmental_interpretation(metrics):
    statements = []
    try:
        rain = metrics.get("rain_anom_pct")
        if rain is not None and float(rain) < -10:
            statements.append(f"Rainfall conditions are currently {fmt_num(rain, 1, '%')}, which suggests higher irrigation demand and closer water planning may be needed.")
    except Exception:
        pass

    try:
        lst = metrics.get("lst_mean")
        if lst is not None and float(lst) > 30:
            statements.append(f"Average land surface temperature is {fmt_num(lst, 1, ' °C')}, which suggests elevated heat conditions that may increase crop stress and water demand.")
    except Exception:
        pass

    try:
        trend = metrics.get("ndvi_trend")
        if trend is not None and float(trend) < 0:
            statements.append(f"The vegetation trend is {fmt_num(trend, 3)}, which may indicate moisture, soil, or management-related stress in part of the landscape.")
    except Exception:
        pass

    if not statements:
        statements.append("Environmental conditions appear broadly stable based on the available indicators, although seasonal monitoring remains important.")
    return statements

def build_evaluate_content(category, metrics):
    greenhouse_pct = metrics.get("greenhouse_pct")
    try:
        greenhouse_pct_f = float(greenhouse_pct) if greenhouse_pct is not None else 0.0
    except Exception:
        greenhouse_pct_f = 0.0

    dependencies = [
        "The farm depends on reliable water availability for irrigation, crop growth, boreholes, and day-to-day farm operations.",
        "Vegetation condition and tree cover matter because they help with soil protection, microclimate stability, pollinator support, and ecological resilience.",
        "Rainfall patterns and heat conditions matter because they influence crop stress, pest pressure, irrigation demand, and farming uncertainty.",
    ]
    if greenhouse_pct_f > 0.5:
        dependencies.append("Protected farming areas depend on temperature control, ventilation, water reliability, and stable operating conditions inside and around greenhouse structures.")

    impacts = []
    try:
        if metrics.get("ndvi_trend") is not None and float(metrics.get("ndvi_trend")) < -0.03:
            impacts.append("Vegetation decline suggests land pressure, ecological stress, or reduced ground cover in the surrounding landscape.")
        else:
            impacts.append("Vegetation condition does not show a strong decline signal, but should still be monitored over time.")
    except Exception:
        impacts.append("Vegetation condition should be monitored over time as part of routine screening.")

    try:
        if metrics.get("forest_loss_pct") is not None and float(metrics.get("forest_loss_pct")) > 5:
            impacts.append("Forest loss is visible in the broader landscape, which may signal habitat pressure or land-use change that could affect long-term resilience.")
        else:
            impacts.append("Forest-loss pressure does not appear to be a dominant signal within the current assessment area.")
    except Exception:
        pass

    try:
        if metrics.get("water_occ") is not None and float(metrics.get("water_occ")) < 5:
            impacts.append("Visible surface water is limited, which may increase dependence on groundwater, storage, or external supply.")
    except Exception:
        pass

    signals = []
    try:
        ndvi = metrics.get("ndvi_current")
        if ndvi is not None:
            ndvi = float(ndvi)
            if ndvi < 0.25:
                signals.append("Current vegetation condition is low, which may point to stressed or sparse vegetation.")
            elif ndvi < 0.45:
                signals.append("Current vegetation condition is moderate, suggesting mixed vegetation performance across the site.")
            else:
                signals.append("Current vegetation condition is relatively strong, suggesting healthier vegetation cover in the assessed area.")
    except Exception:
        pass

    try:
        rain = metrics.get("rain_anom_pct")
        if rain is not None:
            rain = float(rain)
            if rain < -10:
                signals.append("Recent rainfall is below the long-term baseline, which may increase water uncertainty and climate stress.")
            elif rain > 10:
                signals.append("Recent rainfall is above the long-term baseline, which may improve water availability but can also shift pest, runoff, or flood conditions.")
            else:
                signals.append("Recent rainfall is broadly close to the long-term baseline, so rainfall alone does not suggest a major change signal.")
    except Exception:
        pass

    try:
        lst = metrics.get("lst_mean")
        if lst is not None:
            lst = float(lst)
            if lst > 30:
                signals.append("Heat conditions are elevated, which may increase crop stress, water demand, or site cooling needs.")
            else:
                signals.append("Heat conditions are present but not unusually elevated in the current screening output.")
    except Exception:
        pass

    # Greenhouse and farm-operation proxies.
    greenhouse_detected = greenhouse_pct_f > 0.5
    water_reliability = "Moderate"
    try:
        rain = metrics.get("rain_anom_pct")
        trend = metrics.get("ndvi_trend")
        if (rain is not None and float(rain) < -10) or (trend is not None and float(trend) < -0.03):
            water_reliability = "Low"
        elif rain is not None and float(rain) > 5:
            water_reliability = "High"
    except Exception:
        pass

    soil_stress = "Moderate"
    try:
        ndvi = metrics.get("ndvi_current")
        trend = metrics.get("ndvi_trend")
        if (ndvi is not None and float(ndvi) < 0.25) or (trend is not None and float(trend) < -0.03):
            soil_stress = "High"
        elif ndvi is not None and float(ndvi) > 0.45:
            soil_stress = "Low"
    except Exception:
        pass

    greenhouse_heat = exposure_level(metrics.get("lst_mean"), False, 29, 31)
    greenhouse_humidity = "Moderate"
    irrigation_demand = "Moderate"
    pest_risk = "Moderate"
    production_reliability = "Moderate"
    funding_readiness = "Moderate"
    try:
        rain = metrics.get("rain_anom_pct")
        ndvi = metrics.get("ndvi_current")
        lst = metrics.get("lst_mean")
        water_occ = metrics.get("water_occ")
        if rain is not None and float(rain) < -10:
            irrigation_demand = "High"
            greenhouse_humidity = "Low"
        elif rain is not None and float(rain) > 10:
            greenhouse_humidity = "High"
            irrigation_demand = "Low"
        if lst is not None and float(lst) > 30:
            pest_risk = "High"
        if ndvi is not None and float(ndvi) > 0.45 and irrigation_demand != "High":
            production_reliability = "High"
        if ndvi is not None and float(ndvi) < 0.25:
            production_reliability = "Low"
        if water_occ is not None and float(water_occ) < 5 and irrigation_demand == "High":
            funding_readiness = "Low"
        elif production_reliability == "High":
            funding_readiness = "High"
    except Exception:
        pass

    water_exposure = exposure_level(metrics.get("water_occ"), True, 5, 15)
    heat_exposure = exposure_level(metrics.get("lst_mean"), False, 28, 30)

    vegetation_exposure = "Unknown"
    try:
        ndvi = metrics.get("ndvi_current")
        trend = metrics.get("ndvi_trend")
        vegetation_exposure = "Low"
        if (ndvi is not None and float(ndvi) < 0.25) or (trend is not None and float(trend) < -0.03):
            vegetation_exposure = "High"
        elif (ndvi is not None and float(ndvi) < 0.45) or (trend is not None and float(trend) < -0.01):
            vegetation_exposure = "Moderate"
    except Exception:
        pass

    greenhouse_text = (
        "Satellite screening suggests protected farming structures may be present in part of the assessment area. Greenhouse-specific heat, humidity, pest, and irrigation signals should therefore be read alongside the open-field indicators."
        if greenhouse_detected else
        "Satellite screening does not show a strong greenhouse signal in the selected area, so the current outputs should mainly be read as open-field and surrounding-landscape screening."
    )

    return {
        "narrative": "This section reviews the site's current environmental condition, historical change, and the main ways the business may depend on nature or place pressure on it. The aim is to translate the indicators into practical business meaning.",
        "dependencies": dependencies,
        "impacts": impacts,
        "signals": signals,
        "exposure_cards": [
            {"label": "Water exposure", "value": water_exposure, "subtext": "Based on visible surface-water context"},
            {"label": "Heat exposure", "value": heat_exposure, "subtext": "Based on recent land surface temperature"},
            {"label": "Vegetation exposure", "value": vegetation_exposure, "subtext": "Based on current vegetation and trend"},
        ],
        "greenhouse_detected": "Yes" if greenhouse_detected else "No",
        "greenhouse_text": greenhouse_text,
        "greenhouse_cards": [
            {"label": "Greenhouse share", "value": fmt_num(metrics.get('greenhouse_pct'), 1, '%'), "subtext": "Satellite screening proxy"},
            {"label": "Greenhouse heat", "value": greenhouse_heat, "subtext": "Useful for ventilation and cooling planning"},
            {"label": "Humidity risk", "value": greenhouse_humidity, "subtext": "Screening proxy from climate context"},
            {"label": "Pest risk", "value": pest_risk, "subtext": "Screening proxy from heat and vegetation"},
        ],
        "operations_cards": [
            {"label": "Water reliability", "value": water_reliability, "subtext": "Useful for irrigation planning"},
            {"label": "Soil stress", "value": soil_stress, "subtext": "Proxy from vegetation and rainfall"},
            {"label": "Irrigation demand", "value": irrigation_demand, "subtext": "Higher demand means more water planning"},
            {"label": "Production reliability", "value": production_reliability, "subtext": "Simple screening of environmental stability"},
            {"label": "Funding readiness", "value": funding_readiness, "subtext": "Environmental stability can support bankability conversations"},
        ],
        "why_it_matters": "For Panuka, these signals matter because water reliability, vegetation condition, greenhouse heat, pest pressure, and irrigation demand can affect production, SME support, soil protection, and financial resilience.",
    }

def df_chart_to_png_bytes(df, x_col, y_col, title, kind="line", x_label="Year", y_label="Value"):
    if df is None or df.empty:
        return None

    fig, ax = plt.subplots(figsize=(10, 5.2))
    if kind == "bar":
        ax.bar(df[x_col], df[y_col])
    else:
        ax.plot(df[x_col], df[y_col], marker="o")

    ax.set_title(title)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.grid(True, alpha=0.3)
    plt.xticks(rotation=45)
    plt.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def landcover_bar_to_png_bytes(df):
    if df is None or df.empty:
        return None

    df2 = df.sort_values("area_ha", ascending=False).copy()

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.bar(df2["class_name"], df2["area_ha"])
    ax.set_title("Current Land Cover Composition")
    ax.set_xlabel("Land-cover class")
    ax.set_ylabel("Area (ha)")
    ax.grid(True, axis="y", alpha=0.3)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def build_landcover_bar(df):
    fig = px.bar(
        df.sort_values("area_ha", ascending=False),
        x="class_name",
        y="area_ha",
        title="Current Land Cover Composition",
    )
    fig.update_layout(
        xaxis_title="Land-cover class",
        yaxis_title="Area (ha)",
        showlegend=False,
        margin=dict(l=40, r=20, t=60, b=80),
    )
    return fig


def fetch_image_bytes(url: str, timeout: int = 60):
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        buf = BytesIO(r.content)
        buf.seek(0)
        return buf
    except Exception:
        return None


def fetch_pdf_ee_image_bytes(image, geom, dimensions=900, retries=3):
    attempt_dims = [dimensions, 700, 500]

    for i in range(min(retries, len(attempt_dims))):
        try:
            url = image_thumb_url(image, geom, dimensions=attempt_dims[i])
            result = fetch_image_bytes(url, timeout=150)
            if result is not None:
                return result
        except Exception:
            pass

    return None


init_state()

try:
    initialize_ee_from_secrets(st)
except Exception as e:
    st.error("Earth Engine initialization failed. Check your Streamlit secrets and Google Cloud permissions.")
    st.exception(e)
    st.stop()

st.markdown(
    """
    <style>
    .top-hero {
        background: linear-gradient(135deg, #163d63 0%, #235784 55%, #2f6ea2 100%);
        border-radius: 24px;
        padding: 24px 28px;
        color: white;
        box-shadow: 0 10px 28px rgba(22,61,99,0.20);
        margin-bottom: 18px;
    }
    .top-sub {
        color: rgba(255,255,255,0.88);
        font-size: 0.98rem;
        margin-top: 2px;
    }
    .top-tag {
        display: inline-block;
        margin-top: 10px;
        padding: 7px 12px;
        border-radius: 999px;
        background: rgba(255,255,255,0.14);
        font-size: 0.88rem;
        color: white;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

hero_left, hero_right = st.columns([1.2, 5])

with hero_left:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=500)

with hero_right:
    st.markdown(
        f"""
        <div class="top-hero">
            <div style="font-size:2rem;font-weight:800;line-height:1.1;">{APP_TITLE}</div>
            <div class="top-sub">{APP_SUBTITLE}</div>
            <div class="top-tag">{APP_TAGLINE}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("### LEAP Process")
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.info("**Locate**\n\nDefine the site and understand the local nature context.")
with c2:
    st.info("**Evaluate**\n\nReview current conditions and historical environmental change.")
with c3:
    st.info("**Assess**\n\nInterpret key risks and opportunities for the business.")
with c4:
    st.info("**Prepare**\n\nTranslate findings into practical next actions.")

st.markdown("---")

left_col, right_col = st.columns(2)
with left_col:
    st.selectbox(
        "Select Panuka pilot site",
        PRESETS,
        key="preset_selector",
        on_change=preset_changed,
    )

with right_col:
    focus1, focus2 = st.columns(2)
    with focus1:
        if st.button("Focus Site 1", use_container_width=True):
            apply_preset("Panuka Site 1")
            st.rerun()
    with focus2:
        if st.button("Focus Site 2", use_container_width=True):
            apply_preset("Panuka Site 2")
            st.rerun()

st.selectbox(
    "Pilot category",
    CATEGORIES,
    key="category_selector",
)

mode_col1, mode_col2 = st.columns([1, 1])
with mode_col1:
    st.radio(
        "Site definition method",
        ["Draw polygon", "Enter coordinates"],
        key="draw_mode",
        horizontal=True,
    )

with mode_col2:
    st.number_input(
        "Buffer radius (metres)",
        min_value=100,
        max_value=50000,
        step=100,
        key="buffer_input",
        disabled=(st.session_state["draw_mode"] == "Draw polygon"),
    )

if st.session_state["draw_mode"] == "Enter coordinates":
    lat_col, lon_col = st.columns(2)
    with lat_col:
        st.text_input("Latitude", key="lat_input", placeholder="-29.9167")
    with lon_col:
        st.text_input("Longitude", key="lon_input", placeholder="31.0218")

hist1, hist2 = st.columns(2)
with hist1:
    hist_start = st.number_input("Historical start year", min_value=1981, max_value=LAST_FULL_YEAR, value=2001, step=1)
with hist2:
    hist_end = st.number_input("Historical end year", min_value=1981, max_value=LAST_FULL_YEAR, value=LAST_FULL_YEAR, step=1)

st.markdown("### Site Selection")
st.caption("The two Panuka pilot sites are shown as map points. Select a site to centre the map there, then draw the assessment polygon around the relevant production area.")
m = build_map(
    center=st.session_state["map_center"],
    zoom=st.session_state["map_zoom"],
    draw_mode=st.session_state["draw_mode"],
    lat=st.session_state["lat_input"],
    lon=st.session_state["lon_input"],
    buffer_m=st.session_state["buffer_input"],
    existing_geojson=st.session_state["last_drawn_geojson"],
)

map_data = st_folium(
    m,
    width=None,
    height=520,
    returned_objects=["all_drawings"],
    key="eaglenatureinsight_map",
)

drawn_geojson = extract_drawn_geometry(map_data)
if drawn_geojson is not None:
    st.session_state["last_drawn_geojson"] = drawn_geojson

summary_text, geometry_payload, ee_geom = get_geometry_payload(
    drawn_geojson=st.session_state["last_drawn_geojson"] if st.session_state["draw_mode"] == "Draw polygon" else None,
    lat=st.session_state["lat_input"],
    lon=st.session_state["lon_input"],
    buffer_m=st.session_state["buffer_input"],
    mode=st.session_state["draw_mode"],
)

st.markdown("### Current Selection")
st.write(summary_text)

with st.expander("Show geometry payload"):
    if geometry_payload is None:
        st.write("No valid geometry available yet.")
    else:
        st.json(geometry_payload)

run = st.button("Run Assessment", use_container_width=True)

if run:
    if ee_geom is None:
        st.warning("Please draw a polygon or enter valid coordinates first.")
        st.stop()

    if hist_start > hist_end:
        st.warning("Historical start year must be earlier than or equal to end year.")
        st.stop()

    preset = st.session_state["active_preset"]
    category = st.session_state["category_selector"]

    with st.spinner("Running assessment..."):
        metrics = compute_metrics(
            geom=ee_geom,
            hist_start=int(hist_start),
            hist_end=int(hist_end),
            last_full_year=LAST_FULL_YEAR,
        )
        risk = build_risk_and_recommendations(
            preset=preset,
            category=category,
            metrics=metrics,
        )

        satellite_img = satellite_with_polygon(ee_geom, LAST_FULL_YEAR)
        ndvi_img = ndvi_with_polygon(ee_geom, LAST_FULL_YEAR)
        landcover_img = landcover_with_polygon(ee_geom)
        forest_loss_img = forest_loss_with_polygon(ee_geom)
        veg_change_img = vegetation_change_with_polygon(ee_geom, int(hist_start), int(hist_end))

        satellite_url = image_thumb_url(satellite_img, ee_geom, 2200)
        ndvi_url = image_thumb_url(ndvi_img, ee_geom, 1400)
        landcover_url = image_thumb_url(landcover_img, ee_geom, 1400)
        forest_loss_url = image_thumb_url(forest_loss_img, ee_geom, 1400)
        veg_change_url = image_thumb_url(veg_change_img, ee_geom, 1400)

        ndvi_hist_df = prep_year_df(
            fc_to_dataframe(
                landsat_annual_ndvi_collection(ee_geom, max(int(hist_start), 1984), int(hist_end))
            )
        )
        rain_hist_df = prep_year_df(
            fc_to_dataframe(
                annual_rain_collection(ee_geom, max(int(hist_start), 1981), int(hist_end))
            )
        )
        lst_hist_df = prep_year_df(
            fc_to_dataframe(
                annual_lst_collection(ee_geom, max(int(hist_start), 2001), int(hist_end))
            )
        )
        forest_hist_df = prep_year_df(
            fc_to_dataframe(
                forest_loss_by_year_collection(ee_geom, int(hist_start), int(hist_end))
            )
        )
        water_hist_df = prep_year_df(
            fc_to_dataframe(
                water_history_collection(ee_geom, max(int(hist_start), 1984), int(hist_end))
            )
        )
        lc_df = fc_to_dataframe(landcover_feature_collection(ee_geom))
        if not lc_df.empty and "area_ha" in lc_df.columns:
            lc_df["area_ha"] = pd.to_numeric(lc_df["area_ha"], errors="coerce")
            lc_df = lc_df[lc_df["area_ha"].notna()].copy()
            lc_df = lc_df[lc_df["area_ha"] > 0].copy()

        chart_payloads = [
            {
                "title": "Historical NDVI",
                "description": "This plot shows how vegetation condition has changed over time. Rising values usually suggest stronger vegetation cover, while falling values may indicate declining vegetation condition.",
                "bytes": df_chart_to_png_bytes(ndvi_hist_df, "year", "value", "Historical NDVI (Landsat)", kind="line", y_label="NDVI"),
            },
            {
                "title": "Historical rainfall",
                "description": "This plot shows the rainfall pattern across the selected historical period. Lower rainfall over time can point to greater water stress.",
                "bytes": df_chart_to_png_bytes(rain_hist_df, "year", "value", "Historical Rainfall (CHIRPS)", kind="line", y_label="mm"),
            },
            {
                "title": "Historical land surface temperature",
                "description": "This plot shows how land surface temperature has changed over time. Higher values may suggest growing heat pressure across the site.",
                "bytes": df_chart_to_png_bytes(lst_hist_df, "year", "value", "Historical Land Surface Temperature (MODIS)", kind="line", y_label="°C"),
            },
            {
                "title": "Historical forest loss",
                "description": "This plot shows how much forest loss was detected each year. Larger bars indicate greater forest loss in that year.",
                "bytes": df_chart_to_png_bytes(forest_hist_df, "year", "value", "Historical Forest Loss by Year (Hansen)", kind="bar", y_label="ha"),
            },
            {
                "title": "Historical water presence",
                "description": "This plot shows how water presence has changed over time. Lower values may suggest reduced visible water in the landscape.",
                "bytes": df_chart_to_png_bytes(water_hist_df, "year", "value", "Historical Water Presence (JRC)", kind="line", y_label="% water pixels"),
            },
            {
                "title": "Current land-cover composition",
                "description": "This chart shows how the selected area is currently divided across land-cover classes such as tree cover, cropland, built-up land, and water.",
                "bytes": landcover_bar_to_png_bytes(lc_df),
            },
        ]

        image_payloads = [
            {
                "title": "Satellite image with polygon",
                "description": "This is a true-colour satellite view of the selected site. The red outline shows the assessment area.",
                "bytes": fetch_pdf_ee_image_bytes(satellite_img, ee_geom, dimensions=700),
            },
            {
                "title": "NDVI image with polygon",
                "description": "This image shows vegetation condition. Greener areas generally mean healthier or denser vegetation. Redder areas generally mean weaker vegetation.",
                "bytes": fetch_pdf_ee_image_bytes(ndvi_img, ee_geom, dimensions=700),
            },
            {
                "title": "Land-cover image with polygon",
                "description": "This image shows the main land-cover types in the selected area, such as tree cover, cropland, built-up land, and water.",
                "bytes": fetch_pdf_ee_image_bytes(landcover_img, ee_geom, dimensions=850),
            },
            {
                "title": "Vegetation change map with polygon",
                "description": "This image compares earlier and more recent vegetation condition. Redder areas suggest decline. Greener areas suggest improvement.",
                "bytes": fetch_pdf_ee_image_bytes(veg_change_img, ee_geom, dimensions=500),
            },
            {
                "title": "Forest loss map with polygon",
                "description": "This image highlights where forest loss has been detected in or around the selected area.",
                "bytes": fetch_pdf_ee_image_bytes(forest_loss_img, ee_geom, dimensions=850),
            },
        ]

        pdf_bytes = build_pdf_report(
            preset=preset,
            category=category,
            hist_start=int(hist_start),
            hist_end=int(hist_end),
            metrics=metrics,
            risk=risk,
            image_payloads=image_payloads,
            chart_payloads=chart_payloads,
        )

        st.session_state["report_payload"] = {
            "pdf_bytes": pdf_bytes,
            "file_name": f"Panuka_EagleNatureInsight_Report_{date.today().isoformat()}.pdf",
        }

        st.session_state["results_payload"] = {
            "preset": preset,
            "category": category,
            "metrics": metrics,
            "risk": risk,
            "satellite_url": satellite_url,
            "ndvi_url": ndvi_url,
            "landcover_url": landcover_url,
            "forest_loss_url": forest_loss_url,
            "veg_change_url": veg_change_url,
            "ndvi_hist_df": ndvi_hist_df,
            "rain_hist_df": rain_hist_df,
            "lst_hist_df": lst_hist_df,
            "forest_hist_df": forest_hist_df,
            "water_hist_df": water_hist_df,
            "lc_df": lc_df,
            "hist_start": int(hist_start),
            "hist_end": int(hist_end),
        }

    st.success("Assessment complete.")

if st.session_state["report_payload"] is not None:
    st.download_button(
        label="Download PDF Report",
        data=st.session_state["report_payload"]["pdf_bytes"],
        file_name=st.session_state["report_payload"]["file_name"],
        mime="application/pdf",
        use_container_width=True,
    )

results = st.session_state["results_payload"]

if results is not None:
    preset = results["preset"]
    category = results["category"]
    metrics = results["metrics"]
    risk = results["risk"]
    satellite_url = results["satellite_url"]
    ndvi_url = results["ndvi_url"]
    landcover_url = results["landcover_url"]
    forest_loss_url = results["forest_loss_url"]
    veg_change_url = results["veg_change_url"]
    ndvi_hist_df = results["ndvi_hist_df"]
    rain_hist_df = results["rain_hist_df"]
    lst_hist_df = results["lst_hist_df"]
    forest_hist_df = results["forest_hist_df"]
    water_hist_df = results["water_hist_df"]
    lc_df = results["lc_df"]
    hist_start = results.get("hist_start")
    hist_end = results.get("hist_end")

    overview = build_overview_content(preset, category, metrics, risk)
    evaluate = build_evaluate_content(category, metrics)

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
        ["Overview", "Locate", "Evaluate", "Assess", "Prepare", "Images", "Trends", "Detailed Results"]
    )

    with tab1:
        st.markdown("## Panuka Pilot Overview")
        st.write(overview["narrative"])
        st.write(f"**Panuka pilot site:** {preset}")
        st.write(f"**Pilot category:** {category}")

        r1c1, r1c2, r1c3 = st.columns(3)
        with r1c1:
            metric_card("Current NDVI", fmt_num(metrics.get("ndvi_current"), 3), "Sentinel-2")
        with r1c2:
            metric_card("Rainfall Anomaly", fmt_num(metrics.get("rain_anom_pct"), 1, "%"), "vs 1981–2010")
        with r1c3:
            metric_card("Heat Context", fmt_num(metrics.get("lst_mean"), 1, " °C"), "Recent LST mean")

        r2c1, r2c2, r2c3 = st.columns(3)
        with r2c1:
            metric_card("Tree Cover", fmt_num(metrics.get("tree_pct"), 1, "%"), "Current")
        with r2c2:
            metric_card("Surface Water", fmt_num(metrics.get("water_occ"), 1), "Occurrence")
        with r2c3:
            metric_card("Greenhouse Share", fmt_num(metrics.get("greenhouse_pct"), 1, "%"), "Estimated share of site")

        st.markdown("### Top findings")
        for finding in overview["findings"]:
            st.write(f"• {finding}")

        st.markdown("### Why this matters to the business")
        st.write(overview["business_relevance"])

    with tab2:
        st.markdown("## Locate")
        st.write("The selected area has been defined and screened for land cover, visible nature context, and surrounding landscape conditions.")

        c1, c2, c3 = st.columns(3)
        with c1:
            metric_card("Area analysed", fmt_num(metrics.get("area_ha"), 1, " ha"), "Assessment area")
        with c2:
            metric_card("Tree cover", fmt_num(metrics.get("tree_pct"), 1, "%"), "Landscape context")
        with c3:
            metric_card("Surface water", fmt_num(metrics.get("water_occ"), 1), "Occurrence")

        st.write(f"**Cropland:** {fmt_num(metrics.get('cropland_pct'), 1, '%')}")
        st.write(f"**Built-up land:** {fmt_num(metrics.get('built_pct'), 1, '%')}")

        st.markdown("### Current land-cover composition")
        if not lc_df.empty:
            fig = build_landcover_bar(lc_df)
            st.plotly_chart(fig, use_container_width=True, key="locate_landcover_bar")
            st.caption("This chart shows how the selected area is currently divided across land-cover classes such as tree cover, cropland, built-up land, and water.")

    with tab3:
        st.markdown("## Evaluate")
        st.write(evaluate["narrative"])

        e1, e2, e3 = st.columns(3)
        with e1:
            metric_card("Current vegetation", fmt_num(metrics.get("ndvi_current"), 3), "NDVI")
        with e2:
            metric_card("Vegetation trend", fmt_num(metrics.get("ndvi_trend"), 3), "Historical change")
        with e3:
            metric_card("Rainfall context", fmt_num(metrics.get("rain_anom_pct"), 1, "%"), "vs 1981–2010")

        e4, e5, e6 = st.columns(3)
        with e4:
            metric_card("Heat context", fmt_num(metrics.get("lst_mean"), 1, " °C"), "Recent LST mean")
        with e5:
            metric_card("Forest-loss context", fmt_num(metrics.get("forest_loss_pct"), 1, "%"), "% of baseline forest")
        with e6:
            metric_card("Water context", fmt_num(metrics.get("water_occ"), 1), "Surface water occurrence")

        st.markdown("### Dependencies on nature")
        for item in evaluate["dependencies"]:
            st.write(f"• {item}")

        st.markdown("### Possible impacts and pressures")
        for item in evaluate["impacts"]:
            st.write(f"• {item}")

        st.markdown("### What the indicators are suggesting")
        for item in evaluate["signals"]:
            st.write(f"• {item}")

        st.markdown("### Exposure summary")
        x1, x2, x3 = st.columns(3)
        for col, card in zip([x1, x2, x3], evaluate["exposure_cards"]):
            with col:
                metric_card(card["label"], card["value"], card["subtext"])

        st.markdown("### Greenhouse and protected farming screening")
        st.write(f"**Greenhouse detected:** {evaluate['greenhouse_detected']}")
        st.write(evaluate["greenhouse_text"])
        g1, g2, g3, g4 = st.columns(4)
        for col, card in zip([g1, g2, g3, g4], evaluate["greenhouse_cards"]):
            with col:
                metric_card(card["label"], card["value"], card["subtext"])

        st.markdown("### Farm operations and business impact")
        o1, o2, o3, o4, o5 = st.columns(5)
        for col, card in zip([o1, o2, o3, o4, o5], evaluate["operations_cards"]):
            with col:
                metric_card(card["label"], card["value"], card["subtext"])

        st.markdown("### Why this matters")
        st.write(evaluate["why_it_matters"])

    with tab4:
        st.markdown("## Assess")
        st.write("This section uses a portfolio of indicators rather than a single score. It helps explain what the current environmental conditions may mean for farm operations and what responses may be practical.")

        matrix_rows = build_tnfd_matrix(metrics)
        st.markdown("### TNFD environmental risk matrix")
        matrix_df = pd.DataFrame(matrix_rows)
        matrix_df.columns = ["Indicator", "Current value", "What this means", "Suggested response"]
        st.dataframe(matrix_df, use_container_width=True, hide_index=True)

        st.markdown("### Overall environmental interpretation")
        for statement in build_overall_environmental_interpretation(metrics):
            st.write(f"• {statement}")

    with tab5:
        st.markdown("## Prepare")
        st.write("The dashboard provides category-specific next actions based on the current signals and business context.")
        for rec in risk["recs"]:
            st.write(f"• {rec}")
        st.markdown("### Suggested use frequency")
        st.write("• **Seasonally:** before planting, at mid-season, and before harvest for farm decisions.")
        st.write("• **After major weather events:** to screen flood, heat, or vegetation impacts.")
        st.write("• **Annually:** for portfolio review, reporting, and finance-readiness conversations with partners or funders.")
        st.markdown("### TNFD and SME fit")
        st.write("This pilot keeps TNFD LEAP visible while translating the outputs into simple language for SMEs, incubation support, and farm decision-making.")

    with tab6:
        st.markdown("## Image outputs")
        st.write("**NDVI image:** greener usually means stronger vegetation; redder usually means weaker vegetation.")
        st.write("**Vegetation change map:** green usually means improvement; red usually means decline.")
        st.write("**Land-cover image:** colours represent classes such as tree cover, cropland, built-up land, and water.")
        st.write("**Forest loss map:** highlighted areas show detected forest loss.")

        img1, img2 = st.columns(2)
        with img1:
            st.image(satellite_url, caption="Satellite image with polygon", use_container_width=True)
            st.image(ndvi_url, caption="NDVI image with polygon", use_container_width=True)
            st.image(veg_change_url, caption="Vegetation change map with polygon", use_container_width=True)
        with img2:
            st.image(landcover_url, caption="Land-cover image with polygon", use_container_width=True)
            st.image(forest_loss_url, caption="Forest loss map with polygon", use_container_width=True)

    with tab7:
        st.markdown("## Historical plots")

        if not ndvi_hist_df.empty:
            fig = px.line(ndvi_hist_df, x="year", y="value", title="Historical NDVI (Landsat)")
            st.plotly_chart(fig, use_container_width=True, key="trend_ndvi")
        if not rain_hist_df.empty:
            fig = px.line(rain_hist_df, x="year", y="value", title="Historical Rainfall (CHIRPS)")
            st.plotly_chart(fig, use_container_width=True, key="trend_rain")
        if not lst_hist_df.empty:
            fig = px.line(lst_hist_df, x="year", y="value", title="Historical Land Surface Temperature (MODIS)")
            st.plotly_chart(fig, use_container_width=True, key="trend_lst")
        if not forest_hist_df.empty:
            fig = px.bar(forest_hist_df, x="year", y="value", title="Historical Forest Loss by Year (Hansen)")
            st.plotly_chart(fig, use_container_width=True, key="trend_forest")
        if not water_hist_df.empty:
            fig = px.line(water_hist_df, x="year", y="value", title="Historical Water Presence (JRC)")
            st.plotly_chart(fig, use_container_width=True, key="trend_water")

    with tab8:
        st.markdown("## Detailed results")

        detail_df = pd.DataFrame(
            {
                "Metric": [
                    "Business preset",
                    "Pilot category",
                    "Selected range",
                    "Area (ha)",
                    "Current NDVI",
                    "Tree cover (%)",
                    "Cropland (%)",
                    "Built-up (%)",
                    "Surface water occurrence",
                    "Recent LST mean (°C)",
                    "Forest loss (ha)",
                    "Forest loss (%)",
                    "Biome context proxy",
                ],
                "Value": [
                    preset,
                    category,
                    f"{hist_start} to {hist_end}",
                    metrics.get("area_ha"),
                    metrics.get("ndvi_current"),
                    metrics.get("tree_pct"),
                    metrics.get("cropland_pct"),
                    metrics.get("built_pct"),
                    metrics.get("water_occ"),
                    metrics.get("lst_mean"),
                    metrics.get("forest_loss_ha"),
                    metrics.get("forest_loss_pct"),
                    metrics.get("bio_proxy"),
                ],
            }
        )
        st.dataframe(detail_df, use_container_width=True)

        if not lc_df.empty:
            fig = build_landcover_bar(lc_df)
            st.plotly_chart(fig, use_container_width=True, key="detail_landcover_bar")
