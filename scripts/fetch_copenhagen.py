"""
Copenhagen municipal bench fetcher.
Source: Københavns Kommune WFS (wfs-kbhkort.kk.dk).

Confirmed (April 2026):
  Layer  : k101:baenke_borde_puma
  Filter : geoobjekttype LIKE '%ænk%'
  Total  : ~9015 bench features
  Geom   : MultiPoint (WGS84) – first coordinate is used
  Fields : geoobjekttype (bench type), stednavn (location name),
           driftsansvarlig_navn (maintenance), oprettet (created date)
"""

import time
import requests
from scripts.normalize import normalize_municipal_feature

CITY_KEY  = "copenhagen"
PAGE_SIZE = 1000


def _fetch_layer(layer_cfg: dict, base_url: str, epsg: str) -> list[dict]:
    name       = layer_cfg["name"]
    cql_filter = layer_cfg.get("cql_filter")
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
            "SRSNAME":      "EPSG:4326",
            "count":        PAGE_SIZE,
            "startIndex":   start,
        }
        if cql_filter:
            params["CQL_FILTER"] = cql_filter

        try:
            resp = requests.get(base_url, params=params, timeout=90)
            resp.raise_for_status()
        except Exception as exc:
            print(f"  ✗ Request failed: {exc}")
            break

        data  = resp.json()
        batch = data.get("features", [])

        if not batch:
            break

        for raw in batch:
            # normalize.py handles MultiPoint geometry automatically
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
    """Return normalized bench features from Copenhagen WFS."""
    api      = city_cfg["municipal_api"]
    epsg     = city_cfg["epsg"]
    base_url = api["base_url"]
    features = []
    for layer_cfg in api["layers"]:
        features.extend(_fetch_layer(layer_cfg, base_url, epsg))
    return features
