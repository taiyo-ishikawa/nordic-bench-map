"""
Oslo municipal bench fetcher.
Source: Oslo Bymiljøetaten – ArcGIS MapServer (parkanlegg_for_Publikum).

Confirmed endpoint (April 2026):
  https://geodata.bymoslo.no/arcgis/rest/services/geodata/parkanlegg_for_Publikum/MapServer/1/query

Layer 1 = Punkt (point features). Contains park furniture including:
  - "Fast benk"   (fixed bench)
  - "Løs benk"    (movable bench)
  - "Benkebord"   (bench-table)
  Total benches: ~3698

Geometry comes back as ArcGIS JSON {x, y} (not GeoJSON), reprojected to
WGS84 by requesting outSR=4326.
"""

import time
import requests

CITY_KEY  = "oslo"
PAGE_SIZE = 1000


def _arcgis_feature_to_geojson(feature: dict, source_tag: str, field_map: dict) -> dict | None:
    """Convert an ArcGIS JSON feature to the common normalized GeoJSON schema."""
    geom  = feature.get("geometry")
    attrs = feature.get("attributes", {})

    if not geom:
        return None

    lon = geom.get("x")
    lat = geom.get("y")

    # Skip features with null, NaN or non-finite coordinates
    try:
        if lon is None or lat is None or not (
            -180 <= float(lon) <= 180 and -90 <= float(lat) <= 90
        ):
            return None
    except (TypeError, ValueError):
        return None

    lon, lat = float(lon), float(lat)

    def get(key: str):
        raw_key = field_map.get(key)
        return attrs.get(raw_key) if raw_key else None

    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "city":              CITY_KEY,
            "source":            "municipal",
            "raw_source":        source_tag,
            "feature_id":        get("feature_id"),
            "bench_type":        get("bench_type"),
            "material":          get("material"),
            "backrest":          None,
            "seats":             None,
            "location_name":     get("location_name"),
            "maintenance_class": get("maintenance_class"),
            "updated_date":      get("updated_date"),
            "osm_id":            None,
        },
    }


def fetch(city_cfg: dict) -> list[dict]:
    """Return normalized bench features from Oslo Bymiljøetaten ArcGIS MapServer."""
    api        = city_cfg["municipal_api"]
    base_url   = api["base_url"]
    source_tag = api["source_tag"]
    field_map  = api["field_map"]
    where      = api.get("where", "1=1")

    features = []
    offset   = 0
    print(f"  Fetching Oslo ArcGIS MapServer (parkanlegg_for_Publikum/1) …", flush=True)

    while True:
        params = {
            "where":             where,
            "outFields":         "*",
            "f":                 "json",   # ArcGIS JSON (has x/y geometry)
            "outSR":             "4326",
            "resultOffset":      offset,
            "resultRecordCount": PAGE_SIZE,
        }
        try:
            resp = requests.get(base_url, params=params, timeout=90)
            resp.raise_for_status()
        except Exception as exc:
            print(f"  ✗ ArcGIS request failed: {exc}")
            break

        data = resp.json()
        if "error" in data:
            print(f"  ✗ ArcGIS error: {data['error']}")
            break

        batch = data.get("features", [])
        if not batch:
            break

        for raw in batch:
            feat = _arcgis_feature_to_geojson(raw, source_tag, field_map)
            if feat:
                features.append(feat)

        print(f"    … {offset + len(batch)} records", flush=True)
        offset += len(batch)

        # ArcGIS paginates via exceededTransferLimit
        if not data.get("exceededTransferLimit", False):
            break
        time.sleep(0.3)

    print(f"  → {len(features)} bench features from Oslo")
    return features
