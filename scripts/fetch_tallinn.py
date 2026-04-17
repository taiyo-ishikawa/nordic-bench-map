"""
Tallinn municipal bench fetcher.

Confirmed sources (April 2026):
  1. linnamööbel (FeatureServer/0) – city-wide street furniture registry
       URL: https://gis.tallinn.ee/arcgis/rest/services/Hosted/linnamööbel/FeatureServer/0
       Filter: tyyp = 'Pink'   (~118 bench features)
       Fields: tyyp (type), mudel (model), asukoht (location), linnaosa (district)

  2. Põhja_Tallinn_LOV_Pingid_hooldajale (FeatureServer/40) – Põhja-Tallinn district benches
       URL: https://gis.tallinn.ee/arcgis/rest/services/Hosted/
            Põhja_Tallinn_LOV_Pingid_hooldajale/FeatureServer/40
       Filter: 1=1  (all features are benches, ~547 features)
       Fields: tyyp (type), tootja (manufacturer/material proxy), markused (location),
               teisaldatav (movable: jah/ei), editdate (ms timestamp)

Geometry is ArcGIS JSON {x, y} in WGS84 (outSR=4326).
"""

import time
import requests

CITY_KEY  = "tallinn"
PAGE_SIZE = 1000


def _arcgis_to_feature(raw: dict, source_tag: str, field_map: dict) -> dict | None:
    """Convert ArcGIS JSON feature to the common normalised GeoJSON schema."""
    geom  = raw.get("geometry")
    attrs = raw.get("attributes", {})

    if not geom:
        return None

    lon = geom.get("x")
    lat = geom.get("y")
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
        if not raw_key:
            return None
        val = attrs.get(raw_key)
        # Convert epoch-ms timestamp to ISO date string
        if key == "updated_date" and isinstance(val, (int, float)) and val > 0:
            from datetime import datetime, timezone
            return datetime.fromtimestamp(val / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        return val

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


def _fetch_layer(base_url: str, where: str, source_tag: str, field_map: dict) -> list[dict]:
    features = []
    offset   = 0

    while True:
        params = {
            "where":             where,
            "outFields":         "*",
            "f":                 "json",
            "outSR":             "4326",
            "resultOffset":      offset,
            "resultRecordCount": PAGE_SIZE,
        }
        try:
            resp = requests.get(base_url, params=params, timeout=60)
            resp.raise_for_status()
        except Exception as exc:
            print(f"  ✗ Request failed ({source_tag}): {exc}")
            break

        data = resp.json()
        if "error" in data:
            print(f"  ✗ ArcGIS error ({source_tag}): {data['error']}")
            break

        batch = data.get("features", [])
        if not batch:
            break

        for raw in batch:
            feat = _arcgis_to_feature(raw, source_tag, field_map)
            if feat:
                features.append(feat)

        print(f"    {source_tag}: {offset + len(batch)} records", flush=True)
        offset += len(batch)

        if not data.get("exceededTransferLimit", False):
            break
        time.sleep(0.3)

    return features


def fetch(city_cfg: dict) -> list[dict]:
    """Return normalised bench features from Tallinn ArcGIS FeatureServer."""
    api    = city_cfg["municipal_api"]
    layers = api["layers"]

    all_features: list[dict] = []
    for layer_cfg in layers:
        print(f"  Fetching {layer_cfg['source_tag']} …", flush=True)
        feats = _fetch_layer(
            base_url   = layer_cfg["base_url"],
            where      = layer_cfg.get("where", "1=1"),
            source_tag = layer_cfg["source_tag"],
            field_map  = layer_cfg["field_map"],
        )
        print(f"  → {len(feats)} features from {layer_cfg['source_tag']}")
        all_features.extend(feats)

    print(f"  Tallinn municipal total: {len(all_features)}")
    return all_features
