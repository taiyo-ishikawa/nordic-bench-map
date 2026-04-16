"""
Shared OSM bench fetcher via Overpass API.
Works for any city given a bounding box (south, west, north, east).

Retries across multiple public Overpass mirrors with exponential back-off.
"""

import time
import requests

# Public Overpass mirrors in priority order
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

MAX_RETRIES_PER_ENDPOINT = 2
BACKOFF_BASE = 5  # seconds


def fetch_osm_benches(city_key: str, bbox: tuple, timeout: int = 90) -> list[dict]:
    """
    Fetch amenity=bench nodes and ways from OpenStreetMap for the given bbox.
    Returns a list of normalized GeoJSON Feature dicts.
    """
    s, w, n, e = bbox
    query = f"""
[out:json][timeout:{timeout}];
(
  node["amenity"="bench"]({s},{w},{n},{e});
  way["amenity"="bench"]({s},{w},{n},{e});
);
out center tags;
"""
    elements = _query_overpass(query, timeout)
    if not elements:
        return []

    features = []
    for elem in elements:
        etype = elem.get("type")
        if etype == "node":
            lon, lat = elem["lon"], elem["lat"]
        elif etype == "way" and "center" in elem:
            lon = elem["center"]["lon"]
            lat = elem["center"]["lat"]
        else:
            continue

        tags = elem.get("tags", {})
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "city":          city_key,
                "source":        "osm",
                "raw_source":    "OpenStreetMap",
                "osm_id":        elem["id"],
                "osm_type":      etype,
                "bench_type":    tags.get("bench"),
                "material":      tags.get("material"),
                "backrest":      tags.get("backrest"),
                "colour":        tags.get("colour"),
                "seats":         tags.get("seats"),
                "location_name": tags.get("name"),
                "access":        tags.get("access"),
                "covered":       tags.get("covered"),
                "description":   tags.get("description"),
            },
        })

    return features


def _query_overpass(query: str, timeout: int) -> list:
    """Try each Overpass mirror with retries and exponential back-off."""
    for url in OVERPASS_URLS:
        for attempt in range(1, MAX_RETRIES_PER_ENDPOINT + 1):
            try:
                print(f"  Querying Overpass ({url}, attempt {attempt}) …", flush=True)
                resp = requests.post(
                    url,
                    data={"data": query},
                    timeout=timeout + 60,
                    headers={"User-Agent": "nordic-bench-map/1.0"},
                )
                resp.raise_for_status()
                elements = resp.json().get("elements", [])
                print(f"  → {len(elements)} OSM elements")
                return elements
            except Exception as exc:
                wait = BACKOFF_BASE * (2 ** (attempt - 1))
                print(f"  ⚠ Failed ({exc})", flush=True)
                if attempt < MAX_RETRIES_PER_ENDPOINT:
                    print(f"    Retrying in {wait}s …", flush=True)
                    time.sleep(wait)

        print(f"  Skipping {url} after {MAX_RETRIES_PER_ENDPOINT} attempts.")
        time.sleep(3)

    print("  ✗ All Overpass endpoints failed – skipping OSM data.")
    return []
