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
import ee

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
    "Panuka Site 1": {"lat": -15.251194, "lon": 28.144500, "buffer_m": 1200, "zoom": 15},
    "Panuka Site 2": {"lat": -15.251472, "lon": 28.147417, "buffer_m": 1200, "zoom": 15},
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
        "map_zoom": 15,
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


def build_map(center, zoom, draw_mode, lat=None, lon=None, buffer_m=None, existing_geojson=None):
    m = folium.Map(
        location=center,
        zoom_start=zoom,
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

    if draw_mode == "Enter coordinates":
        try:
            lat_val = float(lat)
            lon_val = float(lon)
            folium.Marker([lat_val, lon_val], tooltip="Selected point").add_to(m)
            if buffer_m:
                folium.Circle(
                    [lat_val, lon_val],
                    radius=float(buffer_m),
                    color="#ff0000",
                    weight=2,
                    fill=False,
                ).add_to(m)
        except (TypeError, ValueError):
            pass

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


def safe_float(val):
    try:
        return float(val)
    except Exception:
        return None


def greenhouse_detection_stats(geom, last_full_year):
    s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")

    def _mask(image):
        scl = image.select("SCL")
        mask = (
            scl.neq(3)
            .And(scl.neq(8))
            .And(scl.neq(9))
            .And(scl.neq(10))
            .And(scl.neq(11))
        )
        return image.updateMask(mask)

    img = (
        s2.filterBounds(geom)
        .filterDate(f"{last_full_year}-01-01", f"{last_full_year}-12-31")
        .map(_mask)
        .median()
    )

    worldcover = ee.Image("ESA/WorldCover/v200/2021").select("Map")
    blue = img.select("B2")
    green = img.select("B3")
    red = img.select("B4")
    nir = img.select("B8")
    ndvi = img.normalizedDifference(["B8", "B4"]).rename("NDVI")
    bright = blue.add(green).add(red)

    greenhouse_mask = (
        bright.gt(4200)
        .And(ndvi.gt(-0.05))
        .And(ndvi.lt(0.35))
        .And(worldcover.eq(40).Or(worldcover.eq(50)))
    )

    area_ha = ee.Image.pixelArea().divide(10000).updateMask(greenhouse_mask).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=geom, scale=10, maxPixels=1e13
    ).get("area")

    total_ha = ee.Image.pixelArea().divide(10000).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=geom, scale=10, maxPixels=1e13
    ).get("area")

    pct = ee.Algorithms.If(
        ee.Number(total_ha).gt(0), ee.Number(area_ha).divide(ee.Number(total_ha)).multiply(100), 0
    )

    return ee.Dictionary({
        "greenhouse_ha": ee.Algorithms.If(area_ha, area_ha, 0),
        "greenhouse_pct": pct,
    }).getInfo()


def derive_panuka_operational_metrics(metrics, greenhouse):
    rain = safe_float(metrics.get("rain_anom_pct"))
    water = safe_float(metrics.get("water_occ"))
    heat = safe_float(metrics.get("lst_mean"))
    ndvi = safe_float(metrics.get("ndvi_current"))
    trend = safe_float(metrics.get("ndvi_trend"))
    gh_pct = safe_float((greenhouse or {}).get("greenhouse_pct")) or 0.0
    gh_ha = safe_float((greenhouse or {}).get("greenhouse_ha")) or 0.0

    water_score = 100.0
    if rain is not None:
        water_score += max(-35.0, min(15.0, rain))
    if water is not None:
        water_score += min(10.0, water * 0.4) - 10.0
    if trend is not None and trend < 0:
        water_score += trend * 120.0
    water_score = max(0.0, min(100.0, water_score))

    if water_score >= 70:
        water_label = "High"
    elif water_score >= 45:
        water_label = "Moderate"
    else:
        water_label = "Low"

    soil_risk = "Low"
    if (trend is not None and trend < -0.03) or (ndvi is not None and ndvi < 0.25):
        soil_risk = "High"
    elif (trend is not None and trend < -0.01) or (ndvi is not None and ndvi < 0.45):
        soil_risk = "Moderate"

    greenhouse_detected = gh_pct >= 0.2 or gh_ha >= 0.2

    if heat is None:
        heat_stress = "Unknown"
    elif heat >= 32:
        heat_stress = "High"
    elif heat >= 29:
        heat_stress = "Moderate"
    else:
        heat_stress = "Low"

    if rain is None or heat is None:
        humidity_risk = "Unknown"
    elif rain > 5 and heat >= 28:
        humidity_risk = "High"
    elif rain > -5 and heat >= 26:
        humidity_risk = "Moderate"
    else:
        humidity_risk = "Low"

    pest_score = 0
    pest_score += 2 if heat_stress == "High" else 1 if heat_stress == "Moderate" else 0
    pest_score += 2 if humidity_risk == "High" else 1 if humidity_risk == "Moderate" else 0
    pest_score += 1 if ndvi is not None and ndvi > 0.35 else 0
    pest_risk = "High" if pest_score >= 4 else "Moderate" if pest_score >= 2 else "Low"

    irrigation_demand = "High" if water_label == "Low" or heat_stress == "High" else "Moderate" if water_label == "Moderate" or heat_stress == "Moderate" else "Low"

    production_reliability_score = 100.0
    production_reliability_score -= (100.0 - water_score) * 0.35
    production_reliability_score -= 18 if heat_stress == "High" else 8 if heat_stress == "Moderate" else 0
    production_reliability_score -= 14 if soil_risk == "High" else 6 if soil_risk == "Moderate" else 0
    production_reliability_score -= 10 if pest_risk == "High" else 4 if pest_risk == "Moderate" else 0
    production_reliability_score = max(0.0, min(100.0, production_reliability_score))

    funding_readiness = "Strong" if production_reliability_score >= 75 else "Moderate" if production_reliability_score >= 50 else "Needs support"

    return {
        "greenhouse_detected": greenhouse_detected,
        "greenhouse_area_ha": gh_ha,
        "greenhouse_pct": gh_pct,
        "water_reliability_score": round(water_score, 1),
        "water_reliability_label": water_label,
        "soil_stress_risk": soil_risk,
        "greenhouse_heat_stress": heat_stress,
        "greenhouse_humidity_risk": humidity_risk,
        "greenhouse_pest_risk": pest_risk,
        "irrigation_demand": irrigation_demand,
        "production_reliability_score": round(production_reliability_score, 1),
        "funding_readiness": funding_readiness,
    }


def build_panuka_story(metrics, greenhouse, operational):
    lines = []
    if operational.get("greenhouse_detected"):
        lines.append(
            f"Satellite screening suggests about {fmt_num(operational.get('greenhouse_area_ha'),1,' ha')} of likely protected farming, roughly {fmt_num(operational.get('greenhouse_pct'),1,'%')} of the selected area."
        )
    else:
        lines.append("Satellite screening did not detect a strong protected-farming signal in the selected area, so this looks more like open-field context than greenhouse-dominated farming.")

    lines.append(
        f"Water reliability is currently rated {operational.get('water_reliability_label','Unknown').lower()}, which matters because Panuka relies on irrigation, boreholes, and climate certainty to support farm production and SME incubation."
    )

    if operational.get("greenhouse_detected"):
        lines.append(
            f"For the greenhouse parts of the area, heat stress is {operational.get('greenhouse_heat_stress','Unknown').lower()}, humidity risk is {operational.get('greenhouse_humidity_risk','Unknown').lower()}, and pest conditions are {operational.get('greenhouse_pest_risk','Unknown').lower()}. These are satellite-based proxy insights, useful for screening but not a replacement for in-structure sensors or field checks."
        )
    else:
        lines.append(
            f"For open-field farming, heat stress is {operational.get('greenhouse_heat_stress','Unknown').lower()} and irrigation demand is {operational.get('irrigation_demand','Unknown').lower()}, which helps indicate pressure on crops, water planning, and field operations."
        )

    lines.append(
        f"Production reliability is estimated at {fmt_num(operational.get('production_reliability_score'),1,'%')} and funding readiness is rated {operational.get('funding_readiness','Unknown')}, helping translate environmental conditions into a business and finance conversation for Panuka and the SMEs it supports."
    )
    return lines


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
        "This overview gives a plain-language summary of the Panuka pilot site, highlighting the most important nature-related signals for agribusiness screening and decision support. It now also translates those signals into operational meaning for irrigation, greenhouse conditions, open-field farming, and SME finance readiness."
    )

    business_relevance = (
        "For Panuka, these results matter because water reliability, vegetation condition, greenhouse stress, and rainfall variability can affect farm resilience, training and incubation support, production planning, small-farmer support, and the way environmental performance is communicated to partners or funders."
    )

    return {
        "narrative": narrative,
        "findings": findings[:3],
        "business_relevance": business_relevance,
    }


def build_evaluate_content(category, metrics, operational):
    dependencies = [
        "The farm depends on reliable water availability for irrigation, boreholes, crop growth, and day-to-day farm operations.",
        "Vegetation condition and tree cover matter because they help with soil protection, microclimate stability, pollinators, and ecological resilience.",
        "Rainfall patterns, heat conditions, and seasonal variability matter because they influence crop stress, pest pressure, and farming uncertainty.",
    ]

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
            impacts.append("Forest loss is visible in the broader landscape, which may signal habitat pressure or land-use change that matters for long-term farm resilience.")
        else:
            impacts.append("Forest-loss pressure does not appear to be a dominant signal within the current assessment area.")
    except Exception:
        pass

    if operational.get("greenhouse_detected"):
        impacts.append("Satellite screening suggests protected farming structures are present, so greenhouse operations should be interpreted separately from the open-field part of the farm.")
    else:
        impacts.append("The site appears to be dominated more by open-field context than by clearly detectable greenhouse structures.")

    signals = build_panuka_story(metrics, {}, operational)

    return {
        "narrative": "This section reviews the site's environmental condition, historical change, likely greenhouse and open-field context, and the main ways the business may depend on nature or place pressure on it. The aim is to turn the indicators into practical agribusiness meaning.",
        "dependencies": dependencies,
        "impacts": impacts,
        "signals": signals,
        "exposure_cards": [
            {"label": "Water reliability", "value": operational.get("water_reliability_label", "Unknown"), "subtext": f"Score: {fmt_num(operational.get('water_reliability_score'),1)}/100"},
            {"label": "Heat stress", "value": operational.get("greenhouse_heat_stress", "Unknown"), "subtext": "Greenhouse/open-field heat proxy"},
            {"label": "Soil stress", "value": operational.get("soil_stress_risk", "Unknown"), "subtext": "Vegetation-based soil stress proxy"},
        ],
        "greenhouse_cards": [
            {"label": "Greenhouse detected", "value": "Yes" if operational.get("greenhouse_detected") else "No", "subtext": "Satellite screening only"},
            {"label": "Humidity risk", "value": operational.get("greenhouse_humidity_risk", "Unknown"), "subtext": "Greenhouse disease/ventilation proxy"},
            {"label": "Pest risk", "value": operational.get("greenhouse_pest_risk", "Unknown"), "subtext": "Temperature + humidity + vegetation proxy"},
            {"label": "Irrigation demand", "value": operational.get("irrigation_demand", "Unknown"), "subtext": "Likely water-demand pressure"},
        ],
        "business_cards": [
            {"label": "Production reliability", "value": fmt_num(operational.get("production_reliability_score"),1,"%"), "subtext": "Environmental stability proxy"},
            {"label": "Funding readiness", "value": operational.get("funding_readiness", "Unknown"), "subtext": "For bankability discussion"},
        ],
        "why_it_matters": "For Panuka, these signals matter because they link environmental conditions to operational decisions, greenhouse management, irrigation planning, pest monitoring, and the bankability of the SMEs the platform supports. The outputs are intended for screening and prioritisation, not as a replacement for field checks or greenhouse sensors.",
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
        greenhouse = greenhouse_detection_stats(ee_geom, LAST_FULL_YEAR)
        operational = derive_panuka_operational_metrics(metrics, greenhouse)
        risk = build_risk_and_recommendations(
            preset=preset,
            category=category,
            metrics=metrics,
        )
        if operational.get("greenhouse_detected"):
            risk["recs"] = [
                "Treat greenhouse blocks and open-field blocks as separate management zones when planning water, pest control, and heat mitigation.",
                "Use satellite greenhouse detection as a screening layer, then validate with on-site greenhouse maps and operating records.",
            ] + risk["recs"]
        risk["recs"] = risk["recs"][:10]

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
            "file_name": f"EagleNatureInsight_Report_{date.today().isoformat()}.pdf",
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
            "greenhouse": greenhouse,
            "operational": operational,
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
    greenhouse = results.get("greenhouse", {})
    operational = results.get("operational", {})

    overview = build_overview_content(preset, category, metrics, risk)
    evaluate = build_evaluate_content(category, metrics, operational)

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
            metric_card("Nature Risk", f'{risk["score"]}/100', risk["band"])
        with r1c2:
            metric_card("Current NDVI", fmt_num(metrics.get("ndvi_current"), 3), "Sentinel-2")
        with r1c3:
            metric_card("Rainfall Anomaly", fmt_num(metrics.get("rain_anom_pct"), 1, "%"), "vs 1981–2010")

        r2c1, r2c2, r2c3 = st.columns(3)
        with r2c1:
            metric_card("Tree Cover", fmt_num(metrics.get("tree_pct"), 1, "%"), "Current")
        with r2c2:
            metric_card("Built-up", fmt_num(metrics.get("built_pct"), 1, "%"), "Current")
        with r2c3:
            metric_card("Surface Water", fmt_num(metrics.get("water_occ"), 1), "Occurrence")

        st.markdown("### Top findings")
        for finding in overview["findings"]:
            st.write(f"• {finding}")

        g1, g2, g3 = st.columns(3)
        with g1:
            metric_card("Greenhouse detected", "Yes" if operational.get("greenhouse_detected") else "No", "Satellite screening")
        with g2:
            metric_card("Greenhouse area", fmt_num(operational.get("greenhouse_area_ha"), 1, " ha"), "Likely protected farming")
        with g3:
            metric_card("Production reliability", fmt_num(operational.get("production_reliability_score"), 1, "%"), operational.get("funding_readiness", ""))

        st.markdown("### Operational story")
        for line in build_panuka_story(metrics, greenhouse, operational):
            st.write(f"• {line}")

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

        st.markdown("### Greenhouse conditions")
        g1, g2, g3, g4 = st.columns(4)
        for col, card in zip([g1, g2, g3, g4], evaluate["greenhouse_cards"]):
            with col:
                metric_card(card["label"], card["value"], card["subtext"])

        st.markdown("### Business impact")
        b1, b2 = st.columns(2)
        for col, card in zip([b1, b2], evaluate["business_cards"]):
            with col:
                metric_card(card["label"], card["value"], card["subtext"])

        st.markdown("### Why this matters")
        st.write(evaluate["why_it_matters"])

    with tab4:
        st.markdown("## Assess")
        st.write("The dashboard interprets the evidence into a business-facing nature risk signal and identifies the most relevant issues.")
        st.write(f"Nature risk score: {risk['score']} / 100")
        st.write(f"Risk band: {risk['band']}")
        if risk["flags"]:
            for flag in risk["flags"]:
                st.write(f"• {flag}")
        else:
            st.write("• No major automated flags triggered in the current rule set.")

    with tab5:
        st.markdown("## Prepare")
        st.write("The dashboard provides category-specific next actions based on the current signals and business context.")
        for rec in risk["recs"]:
            st.write(f"• {rec}")

        st.markdown("### Suggested use frequency")
        st.write("• Seasonal review before major planting or production cycles")
        st.write("• Additional checks after rainfall shocks, heat spikes, or visible pest events")
        st.write("• Annual baseline report for partner, lender, or investor discussions")

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
                    "Greenhouse detected",
                    "Greenhouse area (ha)",
                    "Greenhouse share (%)",
                    "Water reliability score",
                    "Heat stress",
                    "Humidity risk",
                    "Pest risk",
                    "Soil stress risk",
                    "Irrigation demand",
                    "Production reliability (%)",
                    "Funding readiness",
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
                    "Yes" if operational.get("greenhouse_detected") else "No",
                    operational.get("greenhouse_area_ha"),
                    operational.get("greenhouse_pct"),
                    operational.get("water_reliability_score"),
                    operational.get("greenhouse_heat_stress"),
                    operational.get("greenhouse_humidity_risk"),
                    operational.get("greenhouse_pest_risk"),
                    operational.get("soil_stress_risk"),
                    operational.get("irrigation_demand"),
                    operational.get("production_reliability_score"),
                    operational.get("funding_readiness"),
                ],
            }
        )
        st.dataframe(detail_df, use_container_width=True)

        if not lc_df.empty:
            fig = build_landcover_bar(lc_df)
            st.plotly_chart(fig, use_container_width=True, key="detail_landcover_bar")
