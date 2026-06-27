"""
Setu — KML ingestion layer (zero-dependency, stdlib xml only).

The organizers shipped three Google-Earth KML layers that are RICHER than the flat CSVs:

  * nashik_kumbh_chokepoints_parking_map.kml — 85 chokepoints/parking nodes, each with a
    real RISK LEVEL (very high / high / medium), a category, a source URL and a field note.
    The CSV had none of this. Risk is the single most valuable upgrade to the hotspot model.
  * CCTV Dataset.kml — the 1,280 zone-grid cameras PLUS ~2,800 more planned camera points
    (ring-road `RRC`, gate `G-`, corridor `C-`/`M-`), ring-road LineStrings, and named
    ghat/transit-hub anchors usable as a geo gazetteer.
  * Police Stations.kml — the 14 stations with surveyed GPS.

This module parses them into plain dicts the rest of Setu consumes. Names like C-0001 /
G-001 / RRC 1 are uncoded in the file, so we classify cameras only by geometry + prefix
and never over-claim a meaning the data doesn't carry.
"""
from __future__ import annotations
import xml.etree.ElementTree as ET, re, os
from collections import Counter

KML_DIR = os.path.join(os.path.dirname(__file__), "kml")
_K = "{http://www.opengis.net/kml/2.2}"

# Real risk levels from the chokepoint KML -> a separation-pressure weight. This REPLACES
# the old hand-guessed category heuristic with the organizers' own risk assessment.
RISK_WEIGHT = {"very high": 1.0, "high": 0.7, "medium": 0.45, "low": 0.3}

# Official 2027 Amrit Snan (royal-bath) calendar — the 4-5x surge is NOT learnable from
# the synthetic file and must be supplied as a static input (per the geo-intel design).
# Source: nashikkumbhmela.co.in / mahakumbh.in published schedule.
SNAN_2027 = {
    "2027-08-02": ("1st Amrit Snan", "Ashadh Somvati Amavasya", 4.5),
    "2027-08-31": ("2nd Amrit Snan", "Shravan Amavasya", 4.5),
    "2027-09-11": ("3rd Amrit Snan (Ramkund / Vaishnava)", "Bhadrapada Shukla Ekadashi", 5.0),
    "2027-09-12": ("3rd Amrit Snan (Kushavarta / Shaiva)", "Trimbakeshwar", 5.0),
}
KUMBH_PERIOD = ("2026-10-31", "2028-07-24")   # flag-hoist -> flag-lower

def snan_multiplier(date_str: str) -> float:
    """Crowd multiplier for a YYYY-MM-DD date (1.0 normal day)."""
    return SNAN_2027.get(date_str, (None, None, 1.0))[2]


def _coords(pm):
    c = pm.find(".//" + _K + "coordinates")
    if c is None or not c.text:
        return None
    pts = [tuple(map(float, p.split(",")[:2])) for p in c.text.split() if p.strip()]
    return pts  # list of (lng, lat)

def _geom(pm):
    if pm.find(".//" + _K + "LineString") is not None: return "line"
    if pm.find(".//" + _K + "Polygon") is not None:     return "polygon"
    if pm.find(".//" + _K + "Point") is not None:       return "point"
    return "?"

def _iter_placemarks(path):
    for pm in ET.parse(path).iter(_K + "Placemark"):
        nm = pm.find(_K + "name")
        ds = pm.find(_K + "description")
        yield (nm.text if nm is not None else "",
               ds.text if ds is not None else "",
               _geom(pm), _coords(pm))


def load_chokepoints(path=None):
    """-> list of {name, category, risk, risk_weight, lng, lat, source, note}."""
    path = path or os.path.join(KML_DIR, "nashik_kumbh_chokepoints_parking_map.kml")
    out = []
    for name, desc, g, pts in _iter_placemarks(path):
        if not pts:
            continue
        d = desc or ""
        def field(k):
            m = re.search(rf"{k}:\s*([^|]+)", d)
            return m.group(1).strip() if m else ""
        risk = field("Risk").lower()
        lng, lat = pts[0]
        out.append({"name": name, "category": field("Category"), "risk": risk,
                    "risk_weight": RISK_WEIGHT.get(risk, 0.4),
                    "lng": lng, "lat": lat,
                    "source": field("Source"), "note": field("Note")})
    return out


def load_police(path=None):
    path = path or os.path.join(KML_DIR, "Police Stations.kml")
    return [{"name": n, "lng": pts[0][0], "lat": pts[0][1]}
            for n, d, g, pts in _iter_placemarks(path) if pts]


def load_cctv(path=None):
    """-> dict with cameras (list of {id, kind, lng, lat}), ring_road (lines),
    zones (Zone Area markers), landmarks (named ghats/hubs). Camera 'kind' is inferred
    from the name prefix only: zone-grid / ring-road / gate / corridor."""
    path = path or os.path.join(KML_DIR, "CCTV Dataset.kml")
    cams, lines, zones, landmarks = [], [], [], []
    for name, desc, g, pts in _iter_placemarks(path):
        if not pts:
            continue
        nm = name or ""
        if g == "line":
            lines.append({"name": nm, "path": pts}); continue
        if g == "polygon":
            landmarks.append({"name": nm, "kind": "area", "path": pts}); continue
        lng, lat = pts[0]
        if re.match(r"Z\d+-C\d+", nm):
            kind = "zone-grid"
        elif nm.startswith("RRC"):
            kind = "ring-road"
        elif nm.startswith("G-"):
            kind = "gate"
        elif nm.startswith(("C-", "M-")):
            kind = "corridor"
        elif nm.startswith("Zone Area"):
            zones.append({"name": nm, "lng": lng, "lat": lat}); continue
        else:
            landmarks.append({"name": nm, "kind": "landmark", "lng": lng, "lat": lat}); continue
        cams.append({"id": nm, "kind": kind, "lng": lng, "lat": lat})
    return {"cameras": cams, "ring_road": lines, "zones": zones, "landmarks": landmarks}


if __name__ == "__main__":
    ch = load_chokepoints()
    print(f"CHOKEPOINTS: {len(ch)}")
    by_risk = Counter(c["risk"] for c in ch)
    print("  by risk:", dict(by_risk))
    print("  highest-risk points:")
    for c in sorted(ch, key=lambda x: -x["risk_weight"])[:6]:
        print(f"    [{c['risk']:9}] {c['name'][:38]:38} {c['category']}")

    pol = load_police()
    print(f"\nPOLICE STATIONS: {len(pol)}")

    cc = load_cctv()
    kinds = Counter(c["kind"] for c in cc["cameras"])
    print(f"\nCCTV camera points: {len(cc['cameras'])}  by kind: {dict(kinds)}")
    print(f"  ring-road segments: {len(cc['ring_road'])} | zone markers: {len(cc['zones'])}"
          f" | named landmarks: {len(cc['landmarks'])}")
    print(f"  sample landmarks: {[l['name'] for l in cc['landmarks'][:8] if l.get('name')]}")

    print(f"\nOFFICIAL 2027 AMRIT SNAN CALENDAR (surge input):")
    for d, (label, occ, mult) in SNAN_2027.items():
        print(f"    {d}  x{mult}  {label}")
