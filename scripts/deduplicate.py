"""
Spatial deduplication for a single city's bench dataset.

Matches OSM benches to municipal benches within MATCH_THRESHOLD_M metres.
Merged features keep municipal geometry (authoritative) and carry fields
from both sources prefixed with  mun_  and  osm_  respectively.

Source values in output:
  "municipal"      – only in municipal data
  "osm"            – only in OSM data
  "municipal+osm"  – matched in both
"""

from scipy.spatial import cKDTree
from pyproj import Transformer

MATCH_THRESHOLD_M = 10.0  # metres; slightly larger than Helsinki (5 m) to account
                           # for positional uncertainty in diverse city datasets

# Project to an equal-area metric CRS for distance calculations
_to_metric = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)


def _to_xy(lon: float, lat: float) -> tuple[float, float]:
    return _to_metric.transform(lon, lat)


def _split(features: list[dict]) -> tuple[list, list]:
    municipal, osm = [], []
    for f in features:
        src = f["properties"].get("source", "")
        if src == "municipal":
            municipal.append(f)
        elif src == "osm":
            osm.append(f)
    return municipal, osm


def _coords(features: list[dict]) -> list[tuple]:
    return [_to_xy(*f["geometry"]["coordinates"]) for f in features]


def _merge_props(mun_props: dict, osm_props: dict, dist_m: float) -> dict:
    merged = {"source": "municipal+osm", "city": mun_props.get("city")}
    skip = {"source", "city"}
    for k, v in mun_props.items():
        if k not in skip:
            merged[f"mun_{k}"] = v
    for k, v in osm_props.items():
        if k not in skip:
            merged[f"osm_{k}"] = v
    merged["match_distance_m"] = round(float(dist_m), 2)
    return merged


def deduplicate(features: list[dict]) -> list[dict]:
    """
    Deduplicate a mixed list of municipal + OSM features for one city.
    Returns a new list where matched pairs are merged into one feature.
    """
    municipal, osm = _split(features)

    if not municipal:
        return [f for f in features if f["properties"].get("source") == "osm"]
    if not osm:
        return municipal

    mun_coords = _coords(municipal)
    osm_coords  = _coords(osm)

    tree = cKDTree(mun_coords)
    distances, indices = tree.query(osm_coords, k=1, workers=-1)

    merged = []
    matched_mun = set()
    unmatched_osm = []

    for osm_i, (dist, mun_i) in enumerate(zip(distances, indices)):
        if dist <= MATCH_THRESHOLD_M and mun_i not in matched_mun:
            props = _merge_props(
                municipal[mun_i]["properties"],
                osm[osm_i]["properties"],
                dist,
            )
            # Prefer backrest / seats from OSM (rarely in municipal data)
            props["backrest"] = osm[osm_i]["properties"].get("osm_backrest") or \
                                 osm[osm_i]["properties"].get("backrest")
            props["seats"]    = osm[osm_i]["properties"].get("osm_seats") or \
                                 osm[osm_i]["properties"].get("seats")
            merged.append({
                "type":     "Feature",
                "geometry": municipal[mun_i]["geometry"],  # authoritative
                "properties": props,
            })
            matched_mun.add(mun_i)
        else:
            unmatched_osm.append(osm[osm_i])

    unmatched_mun = [f for i, f in enumerate(municipal) if i not in matched_mun]
    return merged + unmatched_mun + unmatched_osm


def print_stats(city: str, features: list[dict]) -> None:
    n_merged = sum(1 for f in features if f["properties"]["source"] == "municipal+osm")
    n_mun    = sum(1 for f in features if f["properties"]["source"] == "municipal")
    n_osm    = sum(1 for f in features if f["properties"]["source"] == "osm")
    print(f"  {city}: {len(features)} total  "
          f"[municipal+OSM={n_merged}, municipal only={n_mun}, OSM only={n_osm}]")
