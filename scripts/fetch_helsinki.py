"""
Helsinki municipal bench fetcher.
Source: Helsinki City WFS (YLRE registry) – street & park layers.
Native CRS: EPSG:3879 → reprojected to WGS84.
"""

import time
import requests
from scripts.normalize import normalize_municipal_feature

CITY_KEY = "helsinki"
WFS_BASE = "https://kartta.hel.fi/ws/geoserver/avoindata/wfs"
PAGE_SIZE = 1000


def _fetch_layer(layer_cfg: dict, epsg: str) -> list[dict]:
    name       = layer_cfg["name"]
    cql_filter = layer_cfg["cql_filter"]
    source_tag = layer_cfg["source_tag"]
    field_map  = layer_cfg["field_map"]

    features = []
    start = 0
    print(f"  Fetching {name} …", flush=True)

    while True:
        params = {
            "service":      "WFS",
            "version":      "2.0.0",
            "request":      "GetFeature",
            "typeNames":    name,
            "outputFormat": "application/json",
            "count":        PAGE_SIZE,
            "startIndex":   start,
        }
        if cql_filter:
            params["CQL_FILTER"] = cql_filter

        resp = requests.get(WFS_BASE, params=params, timeout=90)
        resp.raise_for_status()
        batch = resp.json().get("features", [])

        if not batch:
            break

        for raw in batch:
            feat = normalize_municipal_feature(raw, CITY_KEY, source_tag, field_map, epsg)
            if feat:
                features.append(feat)

        print(f"    … {start + len(batch)} records", flush=True)
        start += len(batch)
        if len(batch) < PAGE_SIZE:
            break
        time.sleep(0.3)

    print(f"  → {len(features)} features from {name}")
    return features


def fetch(city_cfg: dict) -> list[dict]:
    """Return normalized bench features from Helsinki YLRE WFS."""
    api  = city_cfg["municipal_api"]
    epsg = city_cfg["epsg"]
    features = []
    for layer_cfg in api["layers"]:
        features.extend(_fetch_layer(layer_cfg, epsg))
    return features
