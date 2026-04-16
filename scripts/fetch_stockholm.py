"""
Stockholm municipal bench fetcher.

STATUS (April 2026)
--------------------
The Trafikkontoret WFS (openstreetgs.stockholm.se) does NOT contain bench data.
Its 87 layers cover road/traffic infrastructure (NVDB), cycling, waste bins,
toilets and lighting – but no park furniture or benches.

API key (ba3fc144-2f3c-46a0-9a0d-79256c75a9be) is stored in config.py and
confirmed working. Full layer list obtained via GetCapabilities – no bänk/
sittmöbler layer found.

Stockholm bench data appears to be managed by a separate city department
(Exploateringskontoret / Parkförvaltningen) and is not currently published
as open data.  → Stockholm uses OSM data only.

To re-check for new layers in the future:
  python -c "
  import requests, re
  KEY = 'ba3fc144-2f3c-46a0-9a0d-79256c75a9be'
  r = requests.get(
      f'https://openstreetgs.stockholm.se/geoservice/api/{KEY}/wfs',
      params={'service':'WFS','version':'2.0.0','request':'GetCapabilities'})
  names = re.findall(r'<Name>(od_gis:[^<]+)</Name>', r.text)
  hits = [n for n in names if any(k in n.lower() for k in ['nk','park','sittm','möbel'])]
  print(hits or 'No bench layers found')
  "
"""


def fetch(city_cfg: dict) -> list[dict]:
    """Stockholm municipal bench data is not available – returns empty list."""
    print("  Stockholm: no municipal bench layer in Trafikkontoret WFS.")
    print("    OSM data will be used as the sole source for Stockholm.")
    return []
