"""
Normalize raw municipal GeoJSON features to the common Nordic Bench schema.

Common schema fields
--------------------
city            : city key (e.g. "helsinki")
source          : "municipal" | "osm" | "municipal+osm"
raw_source      : original source tag (e.g. "Helsinki_YLRE_street")
bench_type      : bench subtype in original language (or None)
material        : material description (or None)
backrest        : "yes" | "no" | None  (OSM tag; None for municipal-only)
seats           : integer or None
location_name   : street / park / area name
maintenance_class: maintenance grade (or None)
updated_date    : ISO-ish date string (or None)
osm_id          : OSM node/way id (or None)
"""

from pyproj import Transformer


# Cache transformers to avoid repeated construction
_transformers: dict[str, Transformer] = {}


def _get_transformer(epsg: str) -> Transformer:
    if epsg not in _transformers:
        _transformers[epsg] = Transformer.from_crs(epsg, "EPSG:4326", always_xy=True)
    return _transformers[epsg]


def reproject(x: float, y: float, epsg: str) -> tuple[float, float]:
    """Convert projected coordinates to WGS84 (lon, lat)."""
    t = _get_transformer(epsg)
    lon, lat = t.transform(x, y)
    return lon, lat


def normalize_municipal_feature(
    raw_feature: dict,
    city_key: str,
    source_tag: str,
    field_map: dict,
    epsg: str,
) -> dict | None:
    """
    Convert a raw WFS/ArcGIS GeoJSON feature to the common schema.

    field_map keys are common schema names; values are raw property names.
    Returns None if geometry is missing or invalid.
    """
    geom = raw_feature.get("geometry")
    if not geom:
        return None

    gtype = geom.get("type")
    if gtype == "Point":
        coords = geom["coordinates"]
    elif gtype == "MultiPoint":
        # Use the first coordinate of the MultiPoint (Copenhagen PUMA data)
        coords_list = geom.get("coordinates", [])
        if not coords_list:
            return None
        coords = coords_list[0]
    else:
        return None

    if epsg.upper() == "EPSG:4326":
        lon, lat = coords[0], coords[1]
    else:
        lon, lat = reproject(coords[0], coords[1], epsg)

    raw_props = raw_feature.get("properties", {})

    def get(key: str):
        raw_key = field_map.get(key)
        return raw_props.get(raw_key) if raw_key else None

    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "city":              city_key,
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
