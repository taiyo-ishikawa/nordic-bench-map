"""
Nordic Bench Map – City Configuration
======================================
Each city entry defines:
  - bbox           : (south, west, north, east) in WGS84
  - area_km2       : approximate municipality area for density calculation
  - epsg           : native CRS of the municipal open-data source
  - municipal_api  : dict with API details (type, url, params, …)
  - osm_keyword    : local word for "bench" used in OSM tags (informational)

API types currently implemented:
  "wfs_geoserver"   – standard OGC WFS (GeoServer/MapServer)
  "arcgis_rest"     – ESRI ArcGIS Feature Service
  "none"            – no municipal source configured yet
"""

CITIES = {
    "helsinki": {
        "label":    "Helsinki",
        "country":  "Finland",
        "bbox":     (60.10, 24.82, 60.35, 25.25),
        "area_km2": 215,
        "epsg":     "EPSG:3879",
        "osm_keyword": "penkki",
        "municipal_api": {
            "type": "wfs_geoserver",
            "base_url": "https://kartta.hel.fi/ws/geoserver/avoindata/wfs",
            # Two layers: street furniture + park furniture
            "layers": [
                {
                    "name": "avoindata:YLRE_Katuosat_piste",
                    "cql_filter": "alatyyppi LIKE '%enkki%'",
                    "source_tag": "Helsinki_YLRE_street",
                    "field_map": {
                        "feature_id":        "osan_id",
                        "bench_type":        "alatyyppi",
                        "material":          "materiaali",
                        "location_name":     "kadun_nimi",
                        "maintenance_class": "yllapitoluokka",
                        "updated_date":      "paivitetty_pvm",
                    },
                },
                {
                    "name": "avoindata:YLRE_Viherosat_piste",
                    "cql_filter": "alatyyppi LIKE '%enkki%'",
                    "source_tag": "Helsinki_YLRE_park",
                    "field_map": {
                        "feature_id":        "osan_id",
                        "bench_type":        "alatyyppi",
                        "material":          "materiaali",
                        "location_name":     "puiston_nimi",
                        "maintenance_class": "hoitoluokka",
                        "updated_date":      "paivitetty_pvm",
                    },
                },
            ],
        },
    },

    "tallinn": {
        "label":    "Tallinn",
        "country":  "Estonia",
        "bbox":     (59.35, 24.55, 59.52, 24.95),
        "area_km2": 159,
        "epsg":     "EPSG:4326",  # ArcGIS returns WGS84 when outSR=4326
        "osm_keyword": "pink",   # Estonian word for bench
        "municipal_api": {
            # Confirmed (April 2026): Tallinn City ArcGIS FeatureServer at gis.tallinn.ee
            # Two sources combined:
            #   1. linnamööbel – city-wide street furniture registry (118 benches, tyyp='Pink')
            #   2. Põhja_Tallinn_LOV_Pingid – Põhja-Tallinn district bench inventory (547 benches)
            "type": "arcgis_featureserver",
            "layers": [
                {
                    "base_url": (
                        "https://gis.tallinn.ee/arcgis/rest/services/"
                        "Hosted/linnam%C3%B6%C3%B6bel/FeatureServer/0/query"
                    ),
                    "where": "tyyp = 'Pink'",
                    "source_tag": "Tallinn_linnamööbel",
                    "field_map": {
                        "feature_id":        "objectid",
                        "bench_type":        "tyyp",
                        "material":          "mudel",
                        "location_name":     "asukoht",
                        "maintenance_class": None,
                        "updated_date":      None,
                    },
                },
                {
                    "base_url": (
                        "https://gis.tallinn.ee/arcgis/rest/services/"
                        "Hosted/P%C3%B5hja_Tallinn_LOV_Pingid_hooldajale/FeatureServer/40/query"
                    ),
                    "where": "1=1",
                    "source_tag": "Tallinn_PõhjaTallinn",
                    "field_map": {
                        "feature_id":        "objectid",
                        "bench_type":        "tyyp",
                        "material":          "tootja",
                        "location_name":     "markused",
                        "maintenance_class": None,
                        "updated_date":      "editdate",
                    },
                },
            ],
        },
    },

    "copenhagen": {
        "label":    "Copenhagen",
        "country":  "Denmark",
        "bbox":     (55.60, 12.45, 55.75, 12.65),
        "area_km2": 86,
        "epsg":     "EPSG:4326",  # WFS returns WGS84 directly when SRSNAME=EPSG:4326
        "osm_keyword": "bænk",
        "municipal_api": {
            "type": "wfs_geoserver",
            # Confirmed working via GetCapabilities (April 2026)
            "base_url": "https://wfs-kbhkort.kk.dk/k101/ows",
            "layers": [
                {
                    # Confirmed: k101:baenke_borde_puma (PUMA asset management system)
                    # Contains ~9015 bench features (geoobjekttype LIKE '%ænk%')
                    # geoobjekttype values: "Københavnerbænk, enkelt", "Ortho Bænk",
                    #   "Københavnerbænk, rund ø3000", "Københavnerbænk, dobbelt"
                    "name": "k101:baenke_borde_puma",
                    "cql_filter": "geoobjekttype LIKE '%ænk%'",
                    "source_tag": "Copenhagen_KK",
                    "geometry_type": "MultiPoint",  # layer returns MultiPoint, not Point
                    "field_map": {
                        "feature_id":        "puma_geoobjekt_id",
                        "bench_type":        "geoobjekttype",
                        "material":          None,
                        "location_name":     "stednavn",
                        "maintenance_class": "driftsansvarlig_navn",
                        "updated_date":      "oprettet",
                    },
                },
            ],
        },
    },

    "oslo": {
        "label":    "Oslo",
        "country":  "Norway",
        "bbox":     (59.82, 10.65, 59.98, 10.88),
        "area_km2": 454,
        "epsg":     "EPSG:4326",  # requested via outSR=4326
        "osm_keyword": "benk",
        "municipal_api": {
            # Confirmed: Oslo Bymiljøetaten via ArcGIS MapServer (April 2026)
            # Service: geodata/parkanlegg_for_Publikum/MapServer/1 (Punkt layer)
            # Total bench features: 3698 (across Fast benk / Løs benk / Benkebord)
            "type": "arcgis_mapserver",
            "base_url": (
                "https://geodata.bymoslo.no/arcgis/rest/services/"
                "geodata/parkanlegg_for_Publikum/MapServer/1/query"
            ),
            "source_tag": "Oslo_Bymiljøetaten",
            # Server-side SQL WHERE clause
            "where": "objekt IN ('Fast benk', 'Løs benk', 'Benkebord')",
            "field_map": {
                "feature_id":        "objectid",
                "bench_type":        "objekt",
                "material":          None,
                "location_name":     "anlegg",
                "maintenance_class": None,
                "updated_date":      None,
            },
        },
    },
}
