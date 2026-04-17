#!/usr/bin/env python3
"""
Nordic Bench Map – Main Data Pipeline
======================================
Fetches bench data for each Nordic city from:
  1. Municipal open data APIs (WFS / ArcGIS REST)
  2. OpenStreetMap (Overpass API)

Then deduplicates overlapping records within each city and writes one
GeoJSON file per city to the data/ directory.

Usage
-----
  # All cities:
  python fetch_all.py

  # Specific cities:
  python fetch_all.py helsinki copenhagen

  # Skip municipal data (OSM only – no API keys needed):
  python fetch_all.py --osm-only

  # Skip deduplication:
  python fetch_all.py --no-dedup

Output files
------------
  docs/data/{city}_benches.geojson   – deduplicated, normalized GeoJSON
  docs/data/summary.json             – count statistics for the web dashboard
"""

import argparse
import json
import sys
import time
from pathlib import Path

from config import CITIES
from scripts import fetch_helsinki, fetch_tallinn, fetch_copenhagen, fetch_oslo
from scripts.fetch_osm import fetch_osm_benches
from scripts.deduplicate import deduplicate, print_stats

DATA_DIR = Path("docs/data")

# Map city key → municipal fetcher module
FETCHERS = {
    "helsinki":   fetch_helsinki,
    "tallinn":    fetch_tallinn,
    "copenhagen": fetch_copenhagen,
    "oslo":       fetch_oslo,
}


def write_geojson(features: list[dict], path: Path) -> None:
    geojson = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        },
        "features": features,
    }
    path.write_text(json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8")


def compute_summary(all_results: dict[str, list[dict]]) -> dict:
    """Build the summary.json payload consumed by the web dashboard."""
    summary = {}
    for city_key, features in all_results.items():
        cfg = CITIES[city_key]
        n_total   = len(features)
        n_mun     = sum(1 for f in features if "municipal" in f["properties"].get("source", ""))
        n_osm_only= sum(1 for f in features if f["properties"].get("source") == "osm")
        n_merged  = sum(1 for f in features if f["properties"].get("source") == "municipal+osm")
        area      = cfg["area_km2"]
        summary[city_key] = {
            "label":           cfg["label"],
            "country":         cfg["country"],
            "total":           n_total,
            "municipal_only":  n_mun - n_merged,
            "osm_only":        n_osm_only,
            "municipal_osm":   n_merged,
            "density_per_km2": round(n_total / area, 2) if area else None,
            "area_km2":        area,
            "osm_coverage_pct": round(100 * (n_merged + n_osm_only) / n_total, 1) if n_total else 0,
        }
    return summary


def process_city(
    city_key: str,
    osm_only: bool = False,
    no_dedup: bool = False,
) -> list[dict]:
    cfg = CITIES[city_key]
    label = cfg["label"]
    print(f"\n{'='*60}")
    print(f"  {label.upper()}")
    print(f"{'='*60}")

    features = []

    # --- Municipal data ---
    if not osm_only:
        fetcher = FETCHERS[city_key]
        print(f"\n[Municipal] {label}")
        try:
            mun_features = fetcher.fetch(cfg)
            print(f"  Municipal total: {len(mun_features)}")
            features.extend(mun_features)
        except Exception as exc:
            print(f"  ✗ Municipal fetch failed: {exc}")
            print("    Continuing with OSM only …")

    # --- OSM data ---
    print(f"\n[OSM] {label}")
    osm_features = fetch_osm_benches(city_key, cfg["bbox"])
    features.extend(osm_features)

    # --- Deduplication ---
    if not no_dedup and features:
        print(f"\n[Dedup] {label} (threshold={10} m)")
        features = deduplicate(features)

    print_stats(label, features)
    return features


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Nordic bench data")
    parser.add_argument(
        "cities",
        nargs="*",
        metavar="CITY",
        help=f"Cities to process: {', '.join(CITIES.keys())} (default: all)",
    )
    parser.add_argument("--osm-only",  action="store_true", help="Skip municipal APIs")
    parser.add_argument("--no-dedup",  action="store_true", help="Skip deduplication")
    args = parser.parse_args()

    # Validate city names and default to all
    valid = set(CITIES.keys())
    if args.cities:
        unknown = [c for c in args.cities if c not in valid]
        if unknown:
            parser.error(f"Unknown cities: {unknown}. Choose from: {', '.join(valid)}")
    else:
        args.cities = list(CITIES.keys())

    DATA_DIR.mkdir(exist_ok=True)
    all_results: dict[str, list[dict]] = {}

    for city_key in args.cities:
        t0 = time.time()
        features = process_city(city_key, osm_only=args.osm_only, no_dedup=args.no_dedup)
        all_results[city_key] = features

        out_path = DATA_DIR / f"{city_key}_benches.geojson"
        write_geojson(features, out_path)
        elapsed = time.time() - t0
        print(f"  → Saved {len(features)} features to {out_path}  ({elapsed:.1f}s)")

    # Write summary for web dashboard
    summary = compute_summary(all_results)
    summary_path = DATA_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSummary saved to {summary_path}")

    # Print comparison table
    print(f"\n{'City':<14} {'Total':>7} {'Mun-only':>10} {'OSM-only':>10} "
          f"{'Merged':>8} {'Density/km²':>12} {'OSM cov%':>9}")
    print("-" * 75)
    for city_key, s in summary.items():
        print(f"{s['label']:<14} {s['total']:>7} {s['municipal_only']:>10} "
              f"{s['osm_only']:>10} {s['municipal_osm']:>8} "
              f"{str(s['density_per_km2']):>12} {s['osm_coverage_pct']:>8}%")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
