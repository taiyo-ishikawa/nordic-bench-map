"""
Stockholm municipal bench fetcher.
Source: Trafikkontoret Open Data WFS (openstreetgs.stockholm.se).

SETUP REQUIRED
--------------
1. Register for a free API key at: https://openstreetgs.stockholm.se/
2. Set the environment variable:
     export STOCKHOLM_API_KEY=your_key_here
   or place it in a .env file (see python-dotenv).

FINDING THE CORRECT LAYER NAME
-------------------------------
Run the GetCapabilities query below and search for "bänk" or "parkinventarier":

  import requests
  api_key = "YOUR_KEY"
  url = f"https://openstreetgs.stockholm.se/geoservice/api/{api_key}/wfs"
  r = requests.get(url, params={"request": "GetCapabilities", "service": "WFS"})
  # Search r.text for bench-related FeatureType names

The layer in config.py ("od_gis:Parkinventarier_Punkt") is the most likely
candidate based on documented naming conventions. Adjust as needed.
"""

import os
import time
import requests
from scripts.normalize import normalize_municipal_feature

CITY_KEY  = "stockholm"
PAGE_SIZE = 1000


def _get_api_key(api_cfg: dict) -> str | None:
    env_var = api_cfg.get("api_key_env", "STOCKHOLM_API_KEY")
    key = os.environ.get(env_var)
    if not key:
        print(f"  ⚠ {env_var} not set – skipping Stockholm municipal data.")
        print("    Register at https://openstreetgs.stockholm.se/ to get a key.")
    return key


def _client_side_filter(features: list[dict], layer_cfg: dict) -> list[dict]:
    """Filter features that represent benches (field value match)."""
    filter_field  = layer_cfg.get("bench_filter_field")
    filter_values = layer_cfg.get("bench_filter_values", [])
    if not filter_field or not filter_values:
        return features

    lowered = {v.lower() for v in filter_values}
    return [
        f for f in features
        if str(f["properties"].get(filter_field, "")).lower() in lowered
    ]


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
            "srsName":      "EPSG:4326",  # request output in WGS84 directly
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

        # Stockholm data is already in WGS84 if srsName=EPSG:4326 is honored
        for raw in batch:
            feat = normalize_municipal_feature(
                raw, CITY_KEY, source_tag, field_map, "EPSG:4326"
            )
            if feat:
                features.append(feat)

        print(f"    … {start + len(batch)} records", flush=True)
        start += len(batch)
        if len(batch) < PAGE_SIZE:
            break
        time.sleep(0.3)

    # Apply client-side bench category filter
    features = _client_side_filter(features, layer_cfg)
    print(f"  → {len(features)} bench features from {name}")
    return features


def fetch(city_cfg: dict) -> list[dict]:
    """Return normalized bench features from Stockholm open data WFS."""
    api    = city_cfg["municipal_api"]
    epsg   = city_cfg["epsg"]
    api_key = _get_api_key(api)

    if not api_key:
        return []

    base_url = api["base_url"].format(api_key=api_key)
    features = []
    for layer_cfg in api["layers"]:
        features.extend(_fetch_layer(layer_cfg, base_url, epsg))
    return features
