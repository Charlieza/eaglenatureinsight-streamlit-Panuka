import json
import ee


def initialize_ee_from_secrets(st) -> None:
    if getattr(initialize_ee_from_secrets, "_initialized", False):
        return

    service_account_info = {
        "type": st.secrets["earthengine"]["type"],
        "project_id": st.secrets["earthengine"]["project_id"],
        "private_key_id": st.secrets["earthengine"]["private_key_id"],
        "private_key": st.secrets["earthengine"]["private_key"],
        "client_email": st.secrets["earthengine"]["client_email"],
        "client_id": st.secrets["earthengine"]["client_id"],
        "auth_uri": st.secrets["earthengine"]["auth_uri"],
        "token_uri": st.secrets["earthengine"]["token_uri"],
        "auth_provider_x509_cert_url": st.secrets["earthengine"]["auth_provider_x509_cert_url"],
        "client_x509_cert_url": st.secrets["earthengine"]["client_x509_cert_url"],
        "universe_domain": st.secrets["earthengine"]["universe_domain"],
    }

    credentials = ee.ServiceAccountCredentials(
        service_account_info["client_email"],
        key_data=json.dumps(service_account_info),
    )

    ee.Initialize(credentials)
    initialize_ee_from_secrets._initialized = True



def get_datasets():
    s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
    chirps = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
    worldcover = ee.Image("ESA/WorldCover/v200/2021").select("Map")
    gsw = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence")
    gsw_yearly = ee.ImageCollection("JRC/GSW1_4/YearlyHistory")
    gsw_monthly = ee.ImageCollection("JRC/GSW1_4/MonthlyHistory")
    dynamic_world = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
    hansen = ee.Image("UMD/hansen/global_forest_change_2024_v1_12")
    modis_lst = ee.ImageCollection("MODIS/061/MOD11A2")

    lt05 = ee.ImageCollection("LANDSAT/LT05/C02/T1_L2")
    le07 = ee.ImageCollection("LANDSAT/LE07/C02/T1_L2")
    lc08 = ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
    lc09 = ee.ImageCollection("LANDSAT/LC09/C02/T1_L2")

    modis_et = ee.ImageCollection("MODIS/061/MOD16A2GF")
    smap_l4 = ee.ImageCollection("NASA/SMAP/SPL4SMGP/008")
    grace = ee.ImageCollection("NASA/GRACE/MASS_GRIDS_V04/LAND")
    soil_organic_carbon = ee.Image("OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02")
    soil_texture = ee.Image("OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02")
    flood_hazard = ee.ImageCollection("JRC/CEMS_GLOFAS/FloodHazard/v2_1")
    fire_burned = ee.ImageCollection("MODIS/061/MCD64A1")
    market_access = ee.Image("projects/malariaatlasproject/assets/accessibility/accessibility_to_cities/2015_v1_0")

    bio_proxy = (
        ee.FeatureCollection("RESOLVE/ECOREGIONS/2017")
        .reduceToImage(properties=["BIOME_NUM"], reducer=ee.Reducer.first())
        .rename("bio_proxy")
    )

    return {
        "S2": s2,
        "CHIRPS": chirps,
        "WORLDCOVER": worldcover,
        "GSW": gsw,
        "GSW_YEARLY": gsw_yearly,
        "GSW_MONTHLY": gsw_monthly,
        "DYNAMIC_WORLD": dynamic_world,
        "HANSEN": hansen,
        "MODIS_LST": modis_lst,
        "MODIS_ET": modis_et,
        "SMAP_L4": smap_l4,
        "GRACE": grace,
        "SOIL_OC": soil_organic_carbon,
        "SOIL_TEXTURE": soil_texture,
        "FLOOD_HAZARD": flood_hazard,
        "FIRE_BURNED": fire_burned,
        "MARKET_ACCESS": market_access,
        "LT05": lt05,
        "LE07": le07,
        "LC08": lc08,
        "LC09": lc09,
        "BIO_PROXY": bio_proxy,
    }



def geojson_to_ee_geometry(geojson_obj: dict) -> ee.Geometry:
    geometry = geojson_obj.get("geometry", geojson_obj)
    return ee.Geometry(geometry)



def point_buffer_to_ee_geometry(lat: float, lon: float, buffer_m: float) -> ee.Geometry:
    return ee.Geometry.Point([lon, lat]).buffer(buffer_m)



def mask_s2_clouds(image: ee.Image) -> ee.Image:
    scl = image.select("SCL")
    mask = (
        scl.neq(3)
        .And(scl.neq(8))
        .And(scl.neq(9))
        .And(scl.neq(10))
        .And(scl.neq(11))
    )
    return image.updateMask(mask)



def current_sentinel_rgb(geom: ee.Geometry, last_full_year: int) -> ee.Image:
    ds = get_datasets()
    return (
        ds["S2"]
        .filterBounds(geom)
        .filterDate(f"{last_full_year}-01-01", f"{last_full_year}-12-31")
        .map(mask_s2_clouds)
        .median()
    )



def current_ndvi_image_and_mean(geom: ee.Geometry, last_full_year: int):
    img = current_sentinel_rgb(geom, last_full_year)
    ndvi = img.normalizedDifference(["B8", "B4"]).rename("NDVI")
    mean = ndvi.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geom,
        scale=10,
        maxPixels=1e13,
    ).get("NDVI")
    return ndvi, mean



def build_polygon_outline(geom: ee.Geometry) -> ee.Image:
    return ee.Image().byte().paint(
        ee.FeatureCollection([ee.Feature(geom)]), 1, 3
    ).visualize(palette=["#ff0000"])



def add_polygon_overlay(base_image: ee.Image, geom: ee.Geometry) -> ee.Image:
    return ee.ImageCollection([base_image, build_polygon_outline(geom)]).mosaic()



def satellite_with_polygon(geom: ee.Geometry, last_full_year: int) -> ee.Image:
    rgb = current_sentinel_rgb(geom, last_full_year).visualize(
        bands=["B4", "B3", "B2"], min=0, max=3000
    )
    return add_polygon_overlay(rgb, geom)



def ndvi_with_polygon(geom: ee.Geometry, last_full_year: int) -> ee.Image:
    ndvi, _ = current_ndvi_image_and_mean(geom, last_full_year)
    vis = ndvi.visualize(
        min=0,
        max=0.8,
        palette=["#d73027", "#fee08b", "#1a9850"],
    )
    return add_polygon_overlay(vis, geom)



def landcover_with_polygon(geom: ee.Geometry) -> ee.Image:
    ds = get_datasets()
    vis = ds["WORLDCOVER"].visualize(
        min=10,
        max=100,
        palette=[
            "#006400", "#ffbb22", "#ffff4c", "#f096ff", "#fa0000",
            "#b4b4b4", "#f0f0f0", "#0064c8", "#0096a0", "#00cf75"
        ],
    )
    return add_polygon_overlay(vis, geom)



def forest_loss_with_polygon(geom: ee.Geometry) -> ee.Image:
    ds = get_datasets()
    vis = ds["HANSEN"].select("lossyear").gt(0).selfMask().visualize(
        palette=["#dc2626"]
    )
    return add_polygon_overlay(vis, geom)




def flood_risk_with_polygon(geom: ee.Geometry) -> ee.Image:
    ds = get_datasets()
    collection = ds["FLOOD_HAZARD"].filterBounds(geom)
    image = ee.Image(collection.first()).select("RP100_depth")
    vis = image.visualize(
        min=0,
        max=2,
        palette=["#f7fbff", "#c6dbef", "#6baed6", "#2171b5", "#08306b"],
    )
    return add_polygon_overlay(vis, geom)


def soil_condition_with_polygon(geom: ee.Geometry) -> ee.Image:
    ds = get_datasets()
    # Use soil organic carbon as a simple soil-condition layer.
    image = ds["SOIL_OC"].select([ee.String(ds["SOIL_OC"].bandNames().get(0))])
    vis = image.visualize(
        min=0,
        max=80,
        palette=["#f7fcb9", "#addd8e", "#31a354", "#006837"],
    )
    return add_polygon_overlay(vis, geom)


def heat_stress_with_polygon(geom: ee.Geometry, hist_end: int) -> ee.Image:
    ds = get_datasets()
    start = max(hist_end - 2, 2001)
    image = (
        ds["MODIS_LST"]
        .filterBounds(geom)
        .filterDate(f"{start}-01-01", f"{hist_end}-12-31")
        .select("LST_Day_1km")
        .mean()
        .multiply(0.02)
        .subtract(273.15)
        .rename("LST_C")
    )
    vis = image.visualize(
        min=20,
        max=40,
        palette=["#2c7bb6", "#abd9e9", "#ffffbf", "#fdae61", "#d7191c"],
    )
    return add_polygon_overlay(vis, geom)


def vegetation_change_with_polygon(geom: ee.Geometry, hist_start: int, hist_end: int) -> ee.Image:
    ds = get_datasets()
    start_year = max(hist_start, 2016)
    end_year = hist_end

    early_end_year = min(start_year + 1, end_year)
    late_start_year = max(end_year - 1, start_year)

    early = (
        ds["S2"]
        .filterBounds(geom)
        .filterDate(f"{start_year}-01-01", f"{early_end_year}-12-31")
        .map(mask_s2_clouds)
        .median()
        .normalizedDifference(["B8", "B4"])
        .rename("NDVI")
    )

    late = (
        ds["S2"]
        .filterBounds(geom)
        .filterDate(f"{late_start_year}-01-01", f"{end_year}-12-31")
        .map(mask_s2_clouds)
        .median()
        .normalizedDifference(["B8", "B4"])
        .rename("NDVI")
    )

    change = late.subtract(early).rename("NDVI_change")

    vis = change.visualize(
        min=-0.4,
        max=0.4,
        palette=[
            "#8b0000",
            "#d73027",
            "#f46d43",
            "#fdae61",
            "#ffffbf",
            "#a6d96a",
            "#66bd63",
            "#1a9850",
        ],
    )

    return add_polygon_overlay(vis, geom)



def image_thumb_url(image: ee.Image, geom: ee.Geometry, dimensions: int = 1200) -> str:
    return image.getThumbURL({
        "region": geom.bounds(),
        "dimensions": dimensions,
        "format": "png",
    })





def _get_info_safe(obj):
    try:
        return obj.getInfo()
    except Exception:
        return None

def prep_l57(img: ee.Image) -> ee.Image:
    qa = img.select("QA_PIXEL")
    mask = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))

    sr = img.select(["SR_B3", "SR_B4"], ["RED", "NIR"]).multiply(0.0000275).add(-0.2)
    return sr.updateMask(mask).copyProperties(img, img.propertyNames())



def prep_l89(img: ee.Image) -> ee.Image:
    qa = img.select("QA_PIXEL")
    mask = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))

    sr = img.select(["SR_B4", "SR_B5"], ["RED", "NIR"]).multiply(0.0000275).add(-0.2)
    return sr.updateMask(mask).copyProperties(img, img.propertyNames())



def landsat_annual_ndvi_collection(geom: ee.Geometry, start_year: int, end_year: int) -> ee.FeatureCollection:
    ds = get_datasets()
    years = ee.List.sequence(start_year, end_year)

    def per_year(y):
        y = ee.Number(y)
        start = ee.Date.fromYMD(y, 1, 1)
        end = ee.Date.fromYMD(y, 12, 31)

        l5 = ds["LT05"].filterBounds(geom).filterDate(start, end).map(prep_l57)
        l7 = ds["LE07"].filterBounds(geom).filterDate(start, end).map(prep_l57)
        l8 = ds["LC08"].filterBounds(geom).filterDate(start, end).map(prep_l89)
        l9 = ds["LC09"].filterBounds(geom).filterDate(start, end).map(prep_l89)

        merged = l5.merge(l7).merge(l8).merge(l9)
        count = merged.size()

        mean_val = ee.Algorithms.If(
            count.gt(0),
            merged.median()
            .normalizedDifference(["NIR", "RED"])
            .rename("NDVI")
            .reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geom,
                scale=30,
                maxPixels=1e13,
            )
            .get("NDVI"),
            None,
        )

        return ee.Feature(None, {"year": y, "value": mean_val, "metric": "ndvi"})

    return ee.FeatureCollection(years.map(per_year))



def annual_rain_collection(geom: ee.Geometry, start_year: int, end_year: int) -> ee.FeatureCollection:
    ds = get_datasets()
    years = ee.List.sequence(start_year, end_year)

    def per_year(y):
        y = ee.Number(y)
        annual = (
            ds["CHIRPS"]
            .filterBounds(geom)
            .filterDate(ee.Date.fromYMD(y, 1, 1), ee.Date.fromYMD(y, 12, 31))
            .select("precipitation")
            .sum()
        )

        mean = annual.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=5566,
            maxPixels=1e13,
        ).get("precipitation")

        return ee.Feature(None, {
            "year": y,
            "value": ee.Algorithms.If(mean, mean, None),
            "metric": "rain_mm",
        })

    return ee.FeatureCollection(years.map(per_year))



def annual_lst_collection(geom: ee.Geometry, start_year: int, end_year: int) -> ee.FeatureCollection:
    ds = get_datasets()
    years = ee.List.sequence(start_year, end_year)

    def per_year(y):
        y = ee.Number(y)
        annual = (
            ds["MODIS_LST"]
            .filterBounds(geom)
            .filterDate(ee.Date.fromYMD(y, 1, 1), ee.Date.fromYMD(y, 12, 31))
            .select("LST_Day_1km")
            .mean()
            .multiply(0.02)
            .subtract(273.15)
            .rename("LST_C")
        )

        mean = annual.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=1000,
            maxPixels=1e13,
        ).get("LST_C")

        return ee.Feature(None, {
            "year": y,
            "value": ee.Algorithms.If(mean, mean, None),
            "metric": "lst_c",
        })

    return ee.FeatureCollection(years.map(per_year))



def forest_loss_by_year_collection(geom: ee.Geometry, start_year: int, end_year: int) -> ee.FeatureCollection:
    ds = get_datasets()
    s = max(start_year, 2001)
    e = min(end_year, 2024)
    years = ee.List.sequence(s, e)
    area_ha = ee.Image.pixelArea().divide(10000)
    loss_year = ds["HANSEN"].select("lossyear")

    def per_year(y):
        y = ee.Number(y)
        code = y.subtract(2000)
        loss_mask = loss_year.eq(code)

        loss_ha = area_ha.updateMask(loss_mask).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geom,
            scale=30,
            maxPixels=1e13,
        ).get("area")

        return ee.Feature(None, {
            "year": y,
            "value": ee.Algorithms.If(loss_ha, loss_ha, 0),
            "metric": "forest_loss_ha",
        })

    return ee.FeatureCollection(years.map(per_year))



def water_history_collection(geom: ee.Geometry, start_year: int, end_year: int) -> ee.FeatureCollection:
    ds = get_datasets()
    coll = (
        ds["GSW_YEARLY"]
        .filterBounds(geom)
        .filterDate(ee.Date.fromYMD(start_year, 1, 1), ee.Date.fromYMD(end_year, 12, 31))
    )

    def per_img(img):
        year = ee.Date(img.get("system:time_start")).get("year")
        water_mask = img.select("waterClass").gte(2)

        water_pct = water_mask.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=30,
            maxPixels=1e13,
        ).get("waterClass")

        safe_val = ee.Algorithms.If(water_pct, ee.Number(water_pct).multiply(100), None)

        return ee.Feature(None, {
            "year": year,
            "value": safe_val,
            "metric": "water_pct",
        })

    return ee.FeatureCollection(coll.map(per_img))



def safe_number(value, default=0):
    return ee.Number(ee.Algorithms.If(ee.Algorithms.IsEqual(value, None), default, value))




def landcover_feature_collection(geom: ee.Geometry) -> ee.FeatureCollection:
    ds = get_datasets()
    classes = [10, 20, 30, 40, 50, 60, 80, 90, 95, 100]
    class_names = {
        10: "Tree cover",
        20: "Shrubland",
        30: "Grassland",
        40: "Cropland",
        50: "Built-up",
        60: "Bare/sparse vegetation",
        80: "Permanent water",
        90: "Herbaceous wetland",
        95: "Mangroves",
        100: "Moss & lichen",
    }

    area_image = ee.Image.pixelArea().divide(10000)
    features = []
    for cls in classes:
        area = area_image.updateMask(ds["WORLDCOVER"].eq(cls)).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geom,
            scale=10,
            maxPixels=1e13,
        ).get("area")
        features.append(
            ee.Feature(None, {
                "class_value": cls,
                "class_name": class_names[cls],
                "area_ha": ee.Algorithms.If(ee.Algorithms.IsEqual(area, None), 0, area),
            })
        )

    return ee.FeatureCollection(features)

def landcover_pct(geom: ee.Geometry, cls: int):
    ds = get_datasets()
    total_area_raw = ee.Image.pixelArea().reduceRegion(
        reducer=ee.Reducer.sum(), geometry=geom, scale=10, maxPixels=1e13
    ).get("area")
    total_area = safe_number(total_area_raw, 0)

    class_area_raw = ee.Image.pixelArea().updateMask(ds["WORLDCOVER"].eq(cls)).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=geom, scale=10, maxPixels=1e13
    ).get("area")
    class_area = safe_number(class_area_raw, 0)

    return ee.Algorithms.If(total_area.gt(0), class_area.divide(total_area).multiply(100), None)



def forest_loss_summary(geom: ee.Geometry):
    ds = get_datasets()
    area_ha = ee.Image.pixelArea().divide(10000)
    tree2000 = ds["HANSEN"].select("treecover2000")
    forest_mask = tree2000.gte(30)

    forest_ha_raw = area_ha.updateMask(forest_mask).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=geom, scale=30, maxPixels=1e13
    ).get("area")
    forest_ha = safe_number(forest_ha_raw, 0)

    loss_mask = ds["HANSEN"].select("lossyear").gt(0)
    loss_ha_raw = area_ha.updateMask(forest_mask.And(loss_mask)).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=geom, scale=30, maxPixels=1e13
    ).get("area")
    loss_ha = safe_number(loss_ha_raw, 0)

    loss_pct = ee.Algorithms.If(forest_ha.gt(0), loss_ha.divide(forest_ha).multiply(100), None)
    return {"forest_ha": forest_ha, "loss_ha": loss_ha, "loss_pct": loss_pct}



def surface_water_occurrence_mean(geom: ee.Geometry):
    ds = get_datasets()
    return ds["GSW"].reduceRegion(
        reducer=ee.Reducer.mean(), geometry=geom, scale=30, maxPixels=1e13
    ).get("occurrence")



def bio_proxy_mean(geom: ee.Geometry):
    ds = get_datasets()
    return ds["BIO_PROXY"].reduceRegion(
        reducer=ee.Reducer.mean(), geometry=geom, scale=250, maxPixels=1e13
    ).get("bio_proxy")



def series_recent_vs_early_delta(fc: ee.FeatureCollection):
    sorted_fc = ee.FeatureCollection(fc).sort("year").filter(ee.Filter.notNull(["value"]))
    count = ee.Number(sorted_fc.size())

    return ee.Algorithms.If(
        count.gte(6),
        ee.Number(ee.FeatureCollection(sorted_fc.toList(3, count.subtract(3))).aggregate_mean("value"))
        .subtract(ee.Number(ee.FeatureCollection(sorted_fc.toList(3, 0)).aggregate_mean("value"))),
        None,
    )



def rainfall_anomaly_pct_from_range(geom: ee.Geometry, hist_start: int, hist_end: int):
    baseline = annual_rain_collection(geom, 1981, 2010)
    recent = annual_rain_collection(geom, max(hist_end - 2, hist_start), hist_end)
    baseline_mean = baseline.aggregate_mean("value")
    recent_mean = recent.aggregate_mean("value")

    missing_any = ee.List([
        ee.Algorithms.IsEqual(baseline_mean, None),
        ee.Algorithms.IsEqual(recent_mean, None),
    ]).contains(True)

    baseline_num = safe_number(baseline_mean, 0)
    recent_num = safe_number(recent_mean, 0)

    return ee.Algorithms.If(
        missing_any,
        None,
        ee.Algorithms.If(
            baseline_num.eq(0),
            None,
            recent_num.subtract(baseline_num).divide(baseline_num).multiply(100),
        ),
    )



def lst_recent_mean_from_range(geom: ee.Geometry, hist_start: int, hist_end: int):
    s = max(hist_end - 2, max(hist_start, 2001))
    fc = annual_lst_collection(geom, s, hist_end)
    mean_val = fc.aggregate_mean("value")
    return ee.Algorithms.If(ee.Algorithms.IsEqual(mean_val, None), None, mean_val)



def detect_greenhouse_area_ha(geom: ee.Geometry, last_full_year: int):
    img = current_sentinel_rgb(geom, last_full_year)
    ndvi = img.normalizedDifference(["B8", "B4"]).rename("ndvi")
    ndbi_like = img.normalizedDifference(["B11", "B8"]).rename("ndbix")
    bright = img.select(["B2", "B3", "B4"]).reduce(ee.Reducer.mean()).rename("bright")

    greenhouse_mask = (
        bright.gt(1800)
        .And(ndvi.lt(0.45))
        .And(ndvi.gt(0.02))
        .And(ndbi_like.lt(0.12))
    )

    area_raw = ee.Image.pixelArea().divide(10000).updateMask(greenhouse_mask).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=geom, scale=10, maxPixels=1e13
    ).get("area")
    return safe_number(area_raw, 0)





def _reduce_mean_first_band(image: ee.Image, geom: ee.Geometry, scale: int):
    reduction = image.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geom,
        scale=scale,
        maxPixels=1e13,
    )
    values = ee.Dictionary(reduction).values()
    return ee.Algorithms.If(ee.List(values).size().gt(0), values.get(0), None)


def soil_moisture_mean(geom: ee.Geometry, hist_end: int):
    ds = get_datasets()
    start_year = max(2015, hist_end - 1)
    image = (
        ds["SMAP_L4"]
        .filterBounds(geom)
        .filterDate(f"{start_year}-01-01", f"{hist_end}-12-31")
        .select("sm_surface")
        .mean()
    )
    return _reduce_mean_first_band(image, geom, 11000)


def evapotranspiration_mean(geom: ee.Geometry, hist_end: int):
    ds = get_datasets()
    start_year = max(2000, hist_end - 1)
    image = (
        ds["MODIS_ET"]
        .filterBounds(geom)
        .filterDate(f"{start_year}-01-01", f"{hist_end}-12-31")
        .select("ET")
        .mean()
    )
    raw = _reduce_mean_first_band(image, geom, 500)
    return ee.Algorithms.If(ee.Algorithms.IsEqual(raw, None), None, ee.Number(raw).multiply(0.1))


def groundwater_anomaly_mean(geom: ee.Geometry, hist_end: int):
    ds = get_datasets()
    end_year = min(hist_end, 2017)
    start_year = max(2003, end_year - 1)
    image = (
        ds["GRACE"]
        .filterBounds(geom)
        .filterDate(f"{start_year}-01-01", f"{end_year}-12-31")
        .select("lwe_thickness_csr")
        .mean()
    )
    return _reduce_mean_first_band(image, geom, 25000)


def soil_organic_carbon_mean(geom: ee.Geometry):
    ds = get_datasets()
    return _reduce_mean_first_band(ds["SOIL_OC"], geom, 250)


def soil_texture_class_mean(geom: ee.Geometry):
    ds = get_datasets()
    return _reduce_mean_first_band(ds["SOIL_TEXTURE"], geom, 250)


def flood_risk_mean(geom: ee.Geometry):
    ds = get_datasets()
    collection = ds["FLOOD_HAZARD"].filterBounds(geom)
    image = ee.Image(collection.first()).select("RP100_depth")
    return _reduce_mean_first_band(image, geom, 90)


def fire_risk_mean(geom: ee.Geometry, hist_end: int):
    ds = get_datasets()
    start_year = max(2001, hist_end - 4)
    burned_coll = (
        ds["FIRE_BURNED"]
        .filterBounds(geom)
        .filterDate(f"{start_year}-01-01", f"{hist_end}-12-31")
        .select("BurnDate")
        .map(lambda img: img.gt(0))
    )
    image = burned_coll.sum()
    return _reduce_mean_first_band(image, geom, 500)


def market_access_mean(geom: ee.Geometry):
    ds = get_datasets()
    return _reduce_mean_first_band(ds["MARKET_ACCESS"], geom, 1000)



def dynamic_world_class_probability_mean(geom: ee.Geometry, class_band: str, hist_end: int):
    ds = get_datasets()
    start_year = max(2020, hist_end - 1)
    image = (
        ds["DYNAMIC_WORLD"]
        .filterBounds(geom)
        .filterDate(f"{start_year}-01-01", f"{hist_end}-12-31")
        .select(class_band)
        .mean()
    )
    raw = _reduce_mean_first_band(image, geom, 10)
    return ee.Algorithms.If(ee.Algorithms.IsEqual(raw, None), None, ee.Number(raw).multiply(100))


def hansen_current_tree_cover_pct(geom: ee.Geometry, canopy_threshold: int = 10):
    ds = get_datasets()
    current_tree = ds["HANSEN"].select("treecover2000").gte(canopy_threshold).And(ds["HANSEN"].select("lossyear").eq(0))
    area_image = ee.Image.pixelArea()
    total_area = safe_number(area_image.reduceRegion(
        reducer=ee.Reducer.sum(), geometry=geom, scale=30, maxPixels=1e13
    ).get("area"), 0)
    tree_area = safe_number(area_image.updateMask(current_tree).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=geom, scale=30, maxPixels=1e13
    ).get("area"), 0)
    return ee.Algorithms.If(total_area.gt(0), tree_area.divide(total_area).multiply(100), None)


def surface_water_max_extent_pct(geom: ee.Geometry):
    ds = get_datasets()
    area_image = ee.Image.pixelArea()
    total_area = safe_number(area_image.reduceRegion(
        reducer=ee.Reducer.sum(), geometry=geom, scale=30, maxPixels=1e13
    ).get("area"), 0)
    water_area = safe_number(area_image.updateMask(ds["GSW"].select("max_extent").eq(1)).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=geom, scale=30, maxPixels=1e13
    ).get("area"), 0)
    return ee.Algorithms.If(total_area.gt(0), water_area.divide(total_area).multiply(100), None)


def water_seasonality_mean_months(geom: ee.Geometry):
    ds = get_datasets()
    seasonality = ds["GSW"].select("seasonality")
    water_mask = ds["GSW"].select("max_extent").eq(1)
    image = seasonality.updateMask(water_mask)
    return _reduce_mean_first_band(image, geom, 30)


def permanent_water_pct(geom: ee.Geometry):
    ds = get_datasets()
    area_image = ee.Image.pixelArea()
    total_area = safe_number(area_image.reduceRegion(
        reducer=ee.Reducer.sum(), geometry=geom, scale=30, maxPixels=1e13
    ).get("area"), 0)
    perm_area = safe_number(area_image.updateMask(ds["GSW"].select("seasonality").eq(12)).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=geom, scale=30, maxPixels=1e13
    ).get("area"), 0)
    return ee.Algorithms.If(total_area.gt(0), perm_area.divide(total_area).multiply(100), None)


def seasonal_water_pct(geom: ee.Geometry):
    ds = get_datasets()
    area_image = ee.Image.pixelArea()
    total_area = safe_number(area_image.reduceRegion(
        reducer=ee.Reducer.sum(), geometry=geom, scale=30, maxPixels=1e13
    ).get("area"), 0)
    seasonal_mask = ds["GSW"].select("seasonality").gt(0).And(ds["GSW"].select("seasonality").lt(12))
    seasonal_area = safe_number(area_image.updateMask(seasonal_mask).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=geom, scale=30, maxPixels=1e13
    ).get("area"), 0)
    return ee.Algorithms.If(total_area.gt(0), seasonal_area.divide(total_area).multiply(100), None)


def water_presence_frequency_pct(geom: ee.Geometry, hist_end: int):
    ds = get_datasets()
    start_year = max(2019, hist_end - 2)
    coll = (
        ds["GSW_MONTHLY"]
        .filterBounds(geom)
        .filterDate(f"{start_year}-01-01", f"{hist_end}-12-31")
        .select("water")
        .map(lambda img: img.gte(2))
    )
    image = coll.mean()
    raw = _reduce_mean_first_band(image, geom, 30)
    return ee.Algorithms.If(ee.Algorithms.IsEqual(raw, None), None, ee.Number(raw).multiply(100))


def compute_metrics(geom: ee.Geometry, hist_start: int, hist_end: int, last_full_year: int):
    """
    Compute metrics in separate small Earth Engine calls to reduce the chance
    of hitting user-memory limits.
    """
    _, ndvi_mean = current_ndvi_image_and_mean(geom, last_full_year)
    ndvi_hist = landsat_annual_ndvi_collection(geom, max(hist_start, 1984), hist_end)
    forest_summary = forest_loss_summary(geom)

    total_area_ha_raw = ee.Image.pixelArea().divide(10000).reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=geom,
        scale=30,
        maxPixels=1e12,
        bestEffort=True,
    ).get("area")
    total_area_ha = safe_number(total_area_ha_raw, 0)

    # Use lighter scales and per-metric evaluation.
    greenhouse_ha = detect_greenhouse_area_ha(geom, last_full_year)
    greenhouse_pct = ee.Algorithms.If(
        ee.Number(total_area_ha).gt(0),
        ee.Number(greenhouse_ha).divide(ee.Number(total_area_ha)).multiply(100),
        0,
    )

    rain_anom_pct = rainfall_anomaly_pct_from_range(geom, hist_start, hist_end)
    lst_mean = lst_recent_mean_from_range(geom, hist_start, hist_end)
    ndvi_trend = series_recent_vs_early_delta(ndvi_hist)

    soil_moisture = soil_moisture_mean(geom, hist_end)
    evapotranspiration = evapotranspiration_mean(geom, hist_end)
    groundwater_anomaly = groundwater_anomaly_mean(geom, hist_end)
    worldcover_tree_pct = landcover_pct(geom, 10)
    hansen_tree_pct = hansen_current_tree_cover_pct(geom, 10)
    dynamic_world_tree_prob_pct = dynamic_world_class_probability_mean(geom, "trees", hist_end)
    dynamic_world_water_prob_pct = dynamic_world_class_probability_mean(geom, "water", hist_end)
    water_max_extent_pct = surface_water_max_extent_pct(geom)
    permanent_water_area_pct = permanent_water_pct(geom)
    seasonal_water_area_pct = seasonal_water_pct(geom)
    water_seasonality_months = water_seasonality_mean_months(geom)
    water_presence_frequency = water_presence_frequency_pct(geom, hist_end)
    soil_organic_carbon = soil_organic_carbon_mean(geom)
    soil_texture_class = soil_texture_class_mean(geom)
    flood_risk = flood_risk_mean(geom)
    fire_risk = fire_risk_mean(geom, hist_end)
    travel_time_to_market = market_access_mean(geom)

    water_reliability = ee.Algorithms.If(
        ee.Algorithms.IsEqual(rain_anom_pct, None),
        None,
        ee.Number(100).subtract(ee.Number(rain_anom_pct).abs().min(100)),
    )
    soil_stress_proxy = ee.Algorithms.If(
        ee.Algorithms.IsEqual(ndvi_trend, None),
        None,
        ee.Number(50).add(ee.Number(ndvi_trend).multiply(-1000)).max(0).min(100),
    )
    greenhouse_heat_stress = ee.Algorithms.If(
        ee.Algorithms.IsEqual(lst_mean, None),
        None,
        ee.Number(lst_mean).subtract(26).multiply(12).max(0).min(100),
    )
    greenhouse_humidity_risk = ee.Algorithms.If(
        ee.List([
            ee.Algorithms.IsEqual(rain_anom_pct, None),
            ee.Algorithms.IsEqual(lst_mean, None),
        ]).contains(True),
        None,
        ee.Number(40)
        .add(ee.Number(rain_anom_pct).max(0).multiply(1.2))
        .add(ee.Number(lst_mean).subtract(24).multiply(2))
        .max(0)
        .min(100),
    )
    greenhouse_pest_risk = ee.Algorithms.If(
        ee.List([
            ee.Algorithms.IsEqual(greenhouse_humidity_risk, None),
            ee.Algorithms.IsEqual(greenhouse_heat_stress, None),
        ]).contains(True),
        None,
        ee.Number(greenhouse_humidity_risk).multiply(0.55)
        .add(ee.Number(greenhouse_heat_stress).multiply(0.45))
        .max(0)
        .min(100),
    )
    irrigation_demand = ee.Algorithms.If(
        ee.List([
            ee.Algorithms.IsEqual(rain_anom_pct, None),
            ee.Algorithms.IsEqual(lst_mean, None),
        ]).contains(True),
        None,
        ee.Number(50)
        .add(ee.Number(rain_anom_pct).multiply(-1.2))
        .add(ee.Number(lst_mean).subtract(25).multiply(3))
        .max(0)
        .min(100),
    )
    production_reliability = ee.Algorithms.If(
        ee.List([
            ee.Algorithms.IsEqual(water_reliability, None),
            ee.Algorithms.IsEqual(soil_stress_proxy, None),
        ]).contains(True),
        None,
        ee.Number(water_reliability).multiply(0.35)
        .add(ee.Number(100).subtract(ee.Number(soil_stress_proxy)).multiply(0.35))
        .add(
            ee.Algorithms.If(
                ee.Algorithms.IsEqual(soil_moisture, None),
                15,
                ee.Number(soil_moisture).multiply(100).min(30),
            )
        )
        .max(0)
        .min(100),
    )
    funding_readiness = ee.Algorithms.If(
        ee.Algorithms.IsEqual(production_reliability, None),
        None,
        ee.Number(production_reliability).multiply(0.55)
        .add(ee.Number(100).subtract(safe_number(forest_summary["loss_pct"], 0)).multiply(0.15))
        .add(
            ee.Algorithms.If(
                ee.Algorithms.IsEqual(flood_risk, None),
                15,
                ee.Number(100).subtract(ee.Number(flood_risk).min(100)).multiply(0.15),
            )
        )
        .add(
            ee.Algorithms.If(
                ee.Algorithms.IsEqual(travel_time_to_market, None),
                15,
                ee.Number(100).subtract(ee.Number(travel_time_to_market).divide(3).min(100)).multiply(0.15),
            )
        )
        .max(0)
        .min(100),
    )

    metric_exprs = {
        "area_ha": total_area_ha,
        "ndvi_current": ndvi_mean,
        "ndvi_trend": ndvi_trend,
        "rain_anom_pct": rain_anom_pct,
        "lst_mean": lst_mean,
        "tree_pct": ee.Number(safe_number(worldcover_tree_pct, 0)).max(safe_number(hansen_tree_pct, 0)),
        "worldcover_tree_pct": worldcover_tree_pct,
        "hansen_tree_pct": hansen_tree_pct,
        "dynamic_world_tree_prob_pct": dynamic_world_tree_prob_pct,
        "cropland_pct": landcover_pct(geom, 40),
        "built_pct": landcover_pct(geom, 50),
        "water_occ": surface_water_occurrence_mean(geom),
        "water_max_extent_pct": water_max_extent_pct,
        "permanent_water_area_pct": permanent_water_area_pct,
        "seasonal_water_area_pct": seasonal_water_area_pct,
        "water_seasonality_months": water_seasonality_months,
        "water_presence_frequency": water_presence_frequency,
        "dynamic_world_water_prob_pct": dynamic_world_water_prob_pct,
        "bio_proxy": bio_proxy_mean(geom),
        "forest_ha": forest_summary["forest_ha"],
        "forest_loss_ha": forest_summary["loss_ha"],
        "forest_loss_pct": forest_summary["loss_pct"],
        "greenhouse_ha": greenhouse_ha,
        "greenhouse_pct": greenhouse_pct,
        "water_reliability": water_reliability,
        "soil_stress_proxy": soil_stress_proxy,
        "greenhouse_heat_stress": greenhouse_heat_stress,
        "greenhouse_humidity_risk": greenhouse_humidity_risk,
        "greenhouse_pest_risk": greenhouse_pest_risk,
        "irrigation_demand": irrigation_demand,
        "production_reliability": production_reliability,
        "funding_readiness": funding_readiness,
        "soil_moisture": soil_moisture,
        "evapotranspiration": evapotranspiration,
        "groundwater_anomaly": groundwater_anomaly,
        "soil_organic_carbon": soil_organic_carbon,
        "soil_texture_class": soil_texture_class,
        "flood_risk": flood_risk,
        "fire_risk": fire_risk,
        "travel_time_to_market": travel_time_to_market,
    }

    results = {}
    for key, expr in metric_exprs.items():
        results[key] = _get_info_safe(expr)

    return results
