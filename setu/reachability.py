"""
Setu — crowd-modulated reachability / search-area model (zero-dependency).

The question this answers: "Person X was last seen at Ramkund at 12:00 and only reported
missing at 14:00. Given the crowd, how far could they have gone — and WHERE do we look?"

This is classic search-and-rescue Probability-of-Area theory, with one twist that matters
at a Kumbh: CROWD DENSITY INVERTS THE RADIUS.
  * On a snan day in a crush, a confused elder physically CANNOT walk — reachable area is
    tiny (~150 m), so search TIGHT and review the cameras right there.
  * On a low-density day the same 2-hour gap means a ~3 km radius — search WIDE.

It also feeds the matcher: a "found" person 8 km away within 2 h of a crush-bound last-seen
is geographically implausible and should be down-weighted (see reach_plausibility()).

Models, grounded in pedestrian-flow (Fruin Level-of-Service) + lost-person behaviour:
  - effective_speed = elder_walking_speed x crowd_speed_factor(density)
  - density estimated from the nearest chokepoint's REAL risk level (KML) x snan-calendar
    multiplier x time-of-day, so it is high exactly where/when separations actually happen.
  - confused elders don't egress rationally: the probability surface is biased toward DWELL
    magnets (water, ghats, transfer nodes, shade) rather than a uniform ring.
"""
from __future__ import annotations
import math, os, re, sys
from kml_ingest import load_chokepoints, snan_multiplier, load_cctv

sys.path.insert(0, os.path.dirname(__file__))

def haversine_km(lat1, lng1, lat2, lng2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

# --------------------------------------------------------------------------- #
# Gazetteer for the 20 free-text last-seen names. Coordinates are APPROXIMATE
# seeds (real Nashik/Trimbak landmarks) with an uncertainty radius in metres —
# to be replaced by the two-person GPS walk the design calls for. `dwell` marks
# places a confused elder drifts toward (water/ghat/transit/shade).
# --------------------------------------------------------------------------- #
GAZETTEER = {
    # name:                (lat,      lng,      uncert_m, dwell, base_density)
    # core bathing crush (coords aligned to the KML Ramkund/Godavari chokepoints):
    "Ramkund Ghat":        (20.00670, 73.79060,   150, True, 1.00),
    "Panchavati Circle":   (20.00750, 73.79100,   250, True, 1.00),
    "Laxmi Narayan Ghat":  (20.00640, 73.79020,   180, True, 1.00),
    "Gauri Patangan":      (20.00600, 73.79250,   220, True, 0.95),
    "Kushavart Kund":      (19.93200, 73.52950,   150, True, 1.00),   # Trimbakeshwar
    "Trimbakeshwar Approach": (19.93350, 73.53200, 500, True, 1.00),
    # riverside ghats / sangams (high):
    "Kapila Sangam":       (20.00800, 73.81200,   300, True, 0.85),
    "Takli Sangam":        (19.94500, 73.83500,   350, True, 0.85),
    "Dasak Ghat":          (19.97600, 73.82700,   300, True, 0.80),
    "Nandur Ghat":         (20.04700, 73.80100,   400, True, 0.80),
    # sadhu camp + transit nodes (high):
    "Sadhugram Gate 1":    (20.01100, 73.81600,   300, True, 0.80),
    "Sadhugram Gate 2":    (20.00900, 73.81400,   300, True, 0.80),
    "Madsangvi Transit":   (20.01900, 73.84300,   450, False, 0.75),
    "Nashik Road Station": (19.94600, 73.83800,   300, False, 0.75),
    "Bus Stand Nashik":    (19.99800, 73.77900,   250, False, 0.75),
    "Main Police Chowki":  (19.99700, 73.78500,   200, True, 0.70),
    # outer / corridor (medium):
    "Adgaon Parking":      (20.01550, 73.82700,   400, False, 0.55),
    "Dindori Road Crossing": (20.03500, 73.76500, 500, False, 0.50),
    "Rajur Bahula":        (19.97000, 73.70000,   600, False, 0.50),
    "Trimbak Road":        (19.96000, 73.68000,  4000, False, 0.50),  # ~18km corridor
}

def _norm(s): return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()

def resolve_place(text):
    """Fuzzy-resolve a free-text last-seen string to a gazetteer entry."""
    n = _norm(text)
    if not n:
        return None
    for name, v in GAZETTEER.items():
        if n == _norm(name):
            return (name, *v)
    for name, v in GAZETTEER.items():
        gn = _norm(name)
        if n in gn or gn in n or (n.split()[0] in gn.split()):
            return (name, *v)
    return None

# --------------------------------------------------------------------------- #
# Crowd density -> walking-speed factor (Fruin Level-of-Service, simplified)
# --------------------------------------------------------------------------- #
ELDER_WALK_KMH = 2.6        # free-space elderly walking speed
WANDER_EFF     = 0.55       # net-displacement efficiency of confused wandering

_CHOKE = load_chokepoints()

def _time_factor(hour):
    if 3 <= hour < 11:  return 1.00      # bathing peak
    if 11 <= hour < 16: return 0.70
    if 16 <= hour < 21: return 0.60
    return 0.35                          # night

def density_index(base_density, date, hour):
    """0 (empty) .. 1 (crush). Structural crowd weight x snan-calendar x time-of-day."""
    snan = 0.5 + 0.5 * (snan_multiplier(date) - 1) / 4   # 0.5 normal .. 1.0 snan
    return max(0.0, min(1.0, base_density * snan * _time_factor(hour) * 1.25))

def speed_factor(d):
    if d < 0.30: return 1.00
    if d < 0.50: return 0.60
    if d < 0.70: return 0.35
    if d < 0.85: return 0.15
    return 0.05                          # crush: involuntary motion only

# --------------------------------------------------------------------------- #
# Reachability + search area
# --------------------------------------------------------------------------- #
def reachable(last_seen_text, date, seen_hour, now_hour):
    place = resolve_place(last_seen_text)
    if not place:
        return None
    name, lat, lng, uncert, dwell, base_dens = place
    elapsed = max(0.0, now_hour - seen_hour)
    dens = density_index(base_dens, date, seen_hour)
    sf = speed_factor(dens)
    max_km = ELDER_WALK_KMH * sf * elapsed * WANDER_EFF
    max_km += uncert / 1000.0            # add last-seen positional uncertainty
    return {"place": name, "lat": lat, "lng": lng, "elapsed_h": elapsed,
            "density": round(dens, 2), "speed_factor": sf,
            "max_radius_km": round(max_km, 2),
            "likely_radius_km": round(max(0.05, max_km * 0.45), 2),
            "dwell_origin": dwell}

# search targets: zone centroids + cameras + chokepoints, probability-weighted
def _zone_centroids():
    import csv
    base = os.path.join(os.path.dirname(__file__), "..",
                        "claude-impact-labs-data", "claude-impact-lab-mumbai-2026", "data")
    with open(os.path.join(base, "Zone_Boundaries.csv")) as f:
        return [{"name": r["zone_name"], "lat": float(r["centroid_lat"]),
                 "lng": float(r["centroid_lng"])} for r in csv.DictReader(f)]

_ZONES = _zone_centroids()
_CCTV = load_cctv()["cameras"]

def search_area(last_seen_text, date, seen_hour, now_hour, top=6):
    r = reachable(last_seen_text, date, seen_hour, now_hour)
    if not r:
        return None
    R = max(r["max_radius_km"], 0.1)
    ranked = []
    for c in _CHOKE:
        d = haversine_km(r["lat"], r["lng"], c["lat"], c["lng"])
        if d > R:
            continue
        w = math.exp(-(d / (0.6 * R)) ** 2)
        # confused elders drift toward water/ghats/transit (familiar sound, shade), NOT parking
        dwell = c["category"] in ("Transfer node", "No-vehicle pressure zone")
        w *= 1.6 if dwell else 1.0
        ranked.append((w, d, c["name"], c["category"]))
    ranked.sort(reverse=True)
    cams = sum(1 for c in _CCTV if haversine_km(r["lat"], r["lng"], c["lat"], c["lng"]) <= R)
    zones = sorted(_ZONES, key=lambda z: haversine_km(r["lat"], r["lng"], z["lat"], z["lng"]))
    zones_in = [z["name"] for z in zones
                if haversine_km(r["lat"], r["lng"], z["lat"], z["lng"]) <= R][:4]
    if not zones_in and zones:                       # tight radius: at least the containing zone
        zones_in = [zones[0]["name"]]
    if not ranked:                                    # no chokepoint in range: anchor on origin
        ranked = [(1.0, 0.0, r["place"], "last-seen point")]
    return {**r, "cameras_to_review": cams, "zones_in_area": zones_in,
            "priority_points": ranked[:top]}

# --------------------------------------------------------------------------- #
# Matcher integration: geographic plausibility of a candidate match
# --------------------------------------------------------------------------- #
def reach_plausibility(missing_last_seen, date, seen_hour, found_lat, found_lng, found_hour):
    """0..1 — how plausible is it that the missing person (last seen at a place/time) is the
    person now FOUND at (found_lat,found_lng,found_hour)? Down-weights matches that are
    physically impossible given the crowd. Multiply into the match score as a soft gate."""
    r = reachable(missing_last_seen, date, seen_hour, max(found_hour, seen_hour))
    if not r:
        return 1.0                        # unknown place -> don't penalize
    d = haversine_km(r["lat"], r["lng"], found_lat, found_lng)
    if d <= r["likely_radius_km"]:
        return 1.0
    if d <= r["max_radius_km"]:
        span = max(0.01, r["max_radius_km"] - r["likely_radius_km"])
        return 1.0 - 0.6 * (d - r["likely_radius_km"]) / span
    return max(0.1, 0.4 * math.exp(-(d - r["max_radius_km"]) / max(0.3, r["max_radius_km"])))


if __name__ == "__main__":
    print("CROWD-MODULATED REACHABILITY — same person, same 2h gap, different crowd\n")
    scenarios = [
        ("Ramkund Ghat", "2027-09-11", 12.0, 14.0, "3rd Amrit Snan (CRUSH)"),
        ("Ramkund Ghat", "2027-07-20", 12.0, 14.0, "ordinary day"),
        ("Ramkund Ghat", "2027-09-11", 12.0, 16.0, "snan, 4h elapsed"),
        ("Madsangvi Transit", "2027-08-31", 5.0, 8.0, "2nd Amrit Snan, dawn peak"),
    ]
    for place, date, t0, t1, label in scenarios:
        s = search_area(place, date, t0, t1)
        print(f"• {place} | last seen {t0:.0f}:00, now {t1:.0f}:00 | {label}")
        print(f"    density={s['density']} -> speed x{s['speed_factor']} | "
              f"REACHABLE max {s['max_radius_km']} km (search-tight {s['likely_radius_km']} km)")
        print(f"    cameras to review: {s['cameras_to_review']} | zones: {', '.join(s['zones_in_area']) or '—'}")
        pts = ", ".join(f"{n}" for _, _, n, _ in s['priority_points'][:3])
        print(f"    search these first: {pts}\n")

    print("MATCHER INTEGRATION — the SAME found person, judged by the crowd at last-seen:")
    AT, NEAR, FAR = (20.0067, 73.7906), (20.0089, 73.7906), (20.0202, 73.7906)  # 0m, 250m, 1.5km
    for label, date in [("SNAN-DAY crush (radius 0.29km)", "2027-09-11"),
                        ("ORDINARY day (radius 1.87km)", "2027-07-20")]:
        base = ("Ramkund Ghat", date, 12.0)
        pa = reach_plausibility(*base, *AT, 14.0)
        pn = reach_plausibility(*base, *NEAR, 14.0)
        pf = reach_plausibility(*base, *FAR, 14.0)
        print(f"    {label:34} | at-site {pa:.2f} | 250m {pn:.2f} | 1.5km {pf:.2f}")
    print("    -> a found person 1.5km away is plausible on a normal day, IMPLAUSIBLE in a crush")
    print("       (same distance, opposite verdict) — this down-weights wrong-location matches.")
