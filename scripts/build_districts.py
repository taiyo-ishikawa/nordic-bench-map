"""
Build district GeoJSON files with bench density for each city.

For each city:
  1. Fetch district boundary polygons from official city APIs
  2. Spatial join: count benches per district
  3. Compute bench density (benches/km²)
  4. Include population where available
  5. Output: docs/data/{city}_districts.geojson

Data sources:
  Helsinki   – WFS avoindata:Kaupunginosajako (HRI)
  Tallinn    – ArcGIS Linnaosad_asumid/FeatureServer/0 (asumid, with population)
  Copenhagen – WFS k101:bydel (Københavns Kommune)
  Oslo       – ArcGIS Befolkningstall.../MapServer/10 (bydeler, with population)
"""

import json
import math
import time
from pathlib import Path

import requests
from shapely.geometry import shape, Point
from shapely.ops import unary_union

DATA_DIR = Path("docs/data")
PAGE_SIZE = 1000


# ── Geometry helpers ─────────────────────────────────────────────────

def arcgis_rings_to_geojson(rings: list) -> dict:
    """Convert ArcGIS rings (polygon) to GeoJSON Polygon/MultiPolygon."""
    if len(rings) == 1:
        return {"type": "Polygon", "coordinates": rings}
    return {"type": "MultiPolygon", "coordinates": [[r] for r in rings]}


def arcgis_polygon_area_km2(rings: list) -> float:
    """Compute area of ArcGIS polygon (WGS84 coords) in km²."""
    try:
        geom = shape(arcgis_rings_to_geojson(rings))
        # Approximate: 1 deg lat ≈ 111 km, 1 deg lon ≈ 111*cos(lat) km
        lat = geom.centroid.y
        scale_x = 111.32 * math.cos(math.radians(lat))
        scale_y = 111.32
        return abs(geom.area) * scale_x * scale_y
    except Exception:
        return 0.0


def geojson_area_km2(geom_dict: dict) -> float:
    """Approximate area of a GeoJSON geometry in km²."""
    try:
        geom = shape(geom_dict)
        lat = geom.centroid.y
        scale_x = 111.32 * math.cos(math.radians(lat))
        scale_y = 111.32
        return abs(geom.area) * scale_x * scale_y
    except Exception:
        return 0.0


# ── Bench loading ─────────────────────────────────────────────────────

def load_bench_points(city_key: str) -> list[Point]:
    path = DATA_DIR / f"{city_key}_benches.geojson"
    data = json.loads(path.read_text(encoding="utf-8"))
    points = []
    for feat in data["features"]:
        coords = feat["geometry"]["coordinates"]
        points.append(Point(coords[0], coords[1]))
    return points


# ── Spatial join ─────────────────────────────────────────────────────

def count_benches_in_districts(districts: list[dict], bench_points: list[Point]) -> list[dict]:
    """
    For each district (GeoJSON Feature), count how many bench_points fall inside.
    Adds 'bench_count' and 'bench_density' to properties.
    """
    from shapely.strtree import STRtree
    print(f"  Spatial join: {len(bench_points)} benches × {len(districts)} districts…")

    # Build shapes with original index
    shapes = []
    valid_idx = []
    for i, d in enumerate(districts):
        try:
            s = shape(d["geometry"])
            shapes.append(s)
            valid_idx.append(i)
        except Exception:
            pass

    tree = STRtree(shapes)
    counts = [0] * len(districts)

    for pt in bench_points:
        # query returns indices into the shapes list
        candidate_indices = tree.query(pt)
        for ci in candidate_indices:
            if shapes[ci].contains(pt):
                counts[valid_idx[ci]] += 1
                break

    for i, d in enumerate(districts):
        d["properties"]["bench_count"] = counts[i]
        area = d["properties"].get("area_km2", 1)
        d["properties"]["bench_density"] = round(counts[i] / area, 2) if area > 0 else 0
    return districts


# ── Helsinki ─────────────────────────────────────────────────────────

def fetch_helsinki_districts() -> list[dict]:
    print("  Fetching Helsinki districts (WFS Kaupunginosajako)…")
    params = {
        "service": "WFS", "version": "2.0.0", "request": "GetFeature",
        "typeNames": "avoindata:Kaupunginosajako",
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
    }
    r = requests.get("https://kartta.hel.fi/ws/geoserver/avoindata/wfs", params=params, timeout=60)
    r.raise_for_status()
    raw = r.json()
    features = []
    for feat in raw.get("features", []):
        props = feat.get("properties", {})
        geom = feat.get("geometry")
        if not geom:
            continue
        area = geojson_area_km2(geom)
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "city":       "helsinki",
                "name":       props.get("nimi_fi", ""),
                "name_en":    props.get("nimi_fi", ""),
                "district_id": str(props.get("tunnus", "")),
                "population": None,
                "area_km2":   round(area, 3),
            }
        })
    print(f"  → {len(features)} Helsinki districts")
    return features


# ── Tallinn ──────────────────────────────────────────────────────────

def fetch_tallinn_districts() -> list[dict]:
    print("  Fetching Tallinn districts (ArcGIS Linnaosad_asumid / Asumid)…")
    base = ("https://gis.tallinn.ee/arcgis/rest/services/"
            "Linnaosad_asumid/FeatureServer/0/query")
    features = []
    offset = 0
    while True:
        params = {
            "where": "1=1", "outFields": "*", "f": "json",
            "outSR": "4326", "returnGeometry": "true",
            "resultOffset": offset, "resultRecordCount": PAGE_SIZE,
        }
        r = requests.get(base, params=params, timeout=60)
        r.raise_for_status()
        data = r.json()
        batch = data.get("features", [])
        if not batch:
            break
        for feat in batch:
            attrs = feat.get("attributes", {})
            rings = feat.get("geometry", {}).get("rings")
            if not rings:
                continue
            geom = arcgis_rings_to_geojson(rings)
            area = arcgis_polygon_area_km2(rings)
            pop = attrs.get("sum_rahvaarv")
            features.append({
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "city":        "tallinn",
                    "name":        attrs.get("asumi_nimi", ""),
                    "name_en":     attrs.get("asumi_nimi", ""),
                    "district_id": str(attrs.get("asumi_kood_tekst", "")),
                    "linnaosa":    attrs.get("linnaosa_nimi", ""),
                    "population":  int(pop) if pop is not None else None,
                    "area_km2":    round(area, 3),
                }
            })
        offset += len(batch)
        if not data.get("exceededTransferLimit", False):
            break
        time.sleep(0.3)
    print(f"  → {len(features)} Tallinn districts (asumid)")
    return features


# ── Copenhagen ───────────────────────────────────────────────────────

def fetch_copenhagen_districts() -> list[dict]:
    print("  Fetching Copenhagen districts (WFS k101:bydel)…")
    params = {
        "service": "WFS", "version": "2.0.0", "request": "GetFeature",
        "typeNames": "k101:bydel",
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
    }
    r = requests.get("https://wfs-kbhkort.kk.dk/k101/ows", params=params, timeout=60)
    r.raise_for_status()
    raw = r.json()
    features = []
    for feat in raw.get("features", []):
        props = feat.get("properties", {})
        geom = feat.get("geometry")
        if not geom:
            continue
        area_m2 = props.get("areal_m2") or 0
        area = area_m2 / 1_000_000
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "city":       "copenhagen",
                "name":       props.get("navn", ""),
                "name_en":    props.get("navn", ""),
                "district_id": str(props.get("bydel_nr", "")),
                "population": None,
                "area_km2":   round(area, 3),
            }
        })
    print(f"  → {len(features)} Copenhagen districts")
    return features


# ── Oslo ─────────────────────────────────────────────────────────────

def fetch_oslo_districts() -> list[dict]:
    print("  Fetching Oslo districts (ArcGIS Bydeler with population)…")
    base = ("https://geodata.bymoslo.no/arcgis/rest/services/"
            "geodata/Befolkningstall_gr_krets_delbydel_bydel/MapServer/10/query")
    features = []
    offset = 0
    while True:
        params = {
            "where": "1=1", "outFields": "*", "f": "json",
            "outSR": "4326", "returnGeometry": "true",
            "resultOffset": offset, "resultRecordCount": PAGE_SIZE,
        }
        r = requests.get(base, params=params, timeout=60)
        r.raise_for_status()
        data = r.json()
        batch = data.get("features", [])
        if not batch:
            break
        for feat in batch:
            attrs = feat.get("attributes", {})
            rings = feat.get("geometry", {}).get("rings")
            if not rings:
                continue
            geom = arcgis_rings_to_geojson(rings)
            area_m2 = attrs.get("st_area(shape)", 0)
            area = area_m2 / 1_000_000 if area_m2 else arcgis_polygon_area_km2(rings)
            pop = attrs.get("alder_i_alt")
            features.append({
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "city":        "oslo",
                    "name":        attrs.get("bydel", ""),
                    "name_en":     attrs.get("bydel", ""),
                    "district_id": str(attrs.get("objectid", "")),
                    "population":  int(pop) if pop is not None else None,
                    "area_km2":    round(area, 3),
                }
            })
        offset += len(batch)
        if not data.get("exceededTransferLimit", False):
            break
        time.sleep(0.3)
    print(f"  → {len(features)} Oslo districts (bydeler)")
    return features


# ── Main ─────────────────────────────────────────────────────────────

FETCHERS = {
    "helsinki":   fetch_helsinki_districts,
    "tallinn":    fetch_tallinn_districts,
    "copenhagen": fetch_copenhagen_districts,
    "oslo":       fetch_oslo_districts,
}


def build(cities: list[str] | None = None):
    DATA_DIR.mkdir(exist_ok=True)
    targets = cities or list(FETCHERS.keys())

    for city_key in targets:
        print(f"\n{'='*50}")
        print(f"  {city_key.upper()}")
        print(f"{'='*50}")

        districts = FETCHERS[city_key]()
        bench_pts  = load_bench_points(city_key)
        print(f"  Loaded {len(bench_pts)} bench points")

        districts = count_benches_in_districts(districts, bench_pts)

        # Add population density where possible
        for d in districts:
            pop = d["properties"].get("population")
            area = d["properties"].get("area_km2", 0)
            if pop and area > 0:
                d["properties"]["pop_density"] = round(pop / area, 1)
            else:
                d["properties"]["pop_density"] = None

        # Write
        out = {
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
            "features": districts,
        }
        out_path = DATA_DIR / f"{city_key}_districts.geojson"
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

        total_benches = sum(d["properties"]["bench_count"] for d in districts)
        print(f"  → {len(districts)} districts, {total_benches} benches assigned")
        print(f"  → Saved to {out_path}")


if __name__ == "__main__":
    import sys
    cities = sys.argv[1:] or None
    build(cities)
