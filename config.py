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

    "stockholm": {
        "label":    "Stockholm",
        "country":  "Sweden",
        "bbox":     (59.20, 17.80, 59.45, 18.20),
        "area_km2": 188,
        "epsg":     "EPSG:3006",  # SWEREF 99 TM
        "osm_keyword": "bänk",
        "municipal_api": {
            "type": "wfs_geoserver",
            # Requires a free API key from: https://openstreetgs.stockholm.se/
            # Set env var STOCKHOLM_API_KEY or replace the placeholder below.
            "base_url": "https://openstreetgs.stockholm.se/geoservice/api/{api_key}/wfs",
            "api_key_env": "STOCKHOLM_API_KEY",
            "layers": [
                {
                    # Exact layer name to confirm via GetCapabilities.
                    # Likely candidates: od_gis:Parkinventarier_Punkt
                    # or od_gis:Sittmobler_Punkt
                    # Run: GET base_url?request=GetCapabilities to list all layers.
                    "name": "od_gis:Parkinventarier_Punkt",
                    "cql_filter": None,  # Filter client-side after fetch
                    "source_tag": "Stockholm_open_data",
                    "field_map": {
                        # Update these after inspecting the actual schema via GetCapabilities
                        "feature_id":        "OBJECTID",
                        "bench_type":        "KATEGORI",
                        "material":          "MATERIAL",
                        "location_name":     "NAMN",
                        "maintenance_class": None,
                        "updated_date":      "LAST_EDITED_DATE",
                    },
                    "bench_filter_field": "KATEGORI",   # field to filter on client-side
                    "bench_filter_values": ["Bänk", "Sittelement", "Bänkbord"],
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
