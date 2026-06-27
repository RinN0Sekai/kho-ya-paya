"""
Setu — geographic intelligence layer (zero-dependency), upgraded with the KML data.

Now driven by the organizers' richer KML layers (see kml_ingest.py):
  * REAL chokepoint risk levels (very high / high / medium) instead of a guessed heuristic.
  * The full ~4,079-point planned camera network instead of the 1,280-camera CSV grid.
  * The official 2027 Amrit Snan calendar as the surge input.

Produces: a risk-weighted predicted-separation hotspot ranking (snan-aware), kiosk
placement at high-risk under-covered points, nearest-facility routing, and CCTV
zone-assist — all on stdlib math so it runs on the offline edge box.
"""
import csv, os, math
from collections import Counter
from kml_ingest import (load_chokepoints, load_police, load_cctv,
                        snan_multiplier, SNAN_2027)

BASE = os.path.join(os.path.dirname(__file__), "..",
                    "claude-impact-labs-data", "claude-impact-lab-mumbai-2026", "data")

def _load_csv(name):
    with open(os.path.join(BASE, name), newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))

def haversine_km(lat1, lng1, lat2, lng2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

# ---- assets (KML-first, richer than the CSVs) ----------------------------- #
choke   = load_chokepoints()          # now carries .risk / .risk_weight
police  = load_police()
cc      = load_cctv()
cameras = cc["cameras"]               # ~4,079 points
reports = _load_csv("Synthetic_Missing_Persons_2500.csv")

seen_counts = Counter(r["last_seen_location"].strip() for r in reports
                      if r["last_seen_location"].strip())

def report_pressure(name):
    pn = (name or "").lower()
    return sum(c for loc, c in seen_counts.items()
               if pn and (pn in loc.lower() or loc.lower() in pn or
                          any(w in loc.lower() for w in pn.split("/")[0].split()[:1])))

def cams_within(lat, lng, km=0.4):
    return sum(1 for c in cameras
               if haversine_km(lat, lng, c["lat"], c["lng"]) <= km)

def hotspots(snan_mult=1.0):
    """Risk-weighted separation hotspots. score = risk_weight x (1 + live reports)
    x snan_mult, with an uncovered-point boost (no nearby camera -> blinder spot)."""
    out = []
    for c in choke:
        cams = cams_within(c["lat"], c["lng"])
        live = report_pressure(c["name"])
        score = c["risk_weight"] * (1 + live) * snan_mult * (1.0 if cams else 1.4)
        out.append({**c, "cams": cams, "live": live, "score": score})
    out.sort(key=lambda h: -h["score"])
    return out

def nearest(lat, lng, facilities):
    best = min(facilities, key=lambda f: haversine_km(lat, lng, f["lat"], f["lng"]))
    return best["name"], haversine_km(lat, lng, best["lat"], best["lng"])


if __name__ == "__main__":
    print(f"Assets (KML): {len(choke)} chokepoints w/ risk, {len(police)} police stations, "
          f"{len(cameras)} cameras, {len(reports)} reports.\n")

    print("TOP 10 PREDICTED SEPARATION HOTSPOTS — NORMAL DAY (risk-weighted)")
    print("-" * 76)
    print(f"  {'risk':10} {'point':36} {'reports':>7} {'cams≤400m':>9}")
    for h in hotspots()[:10]:
        print(f"  {h['risk']:10} {h['name'][:36]:36} {h['live']:>7} {h['cams']:>9}")

    print("\nSAME RANKING ON 2027-09-11 (3rd Amrit Snan, x5.0) — surge re-prioritization")
    print("-" * 76)
    for h in hotspots(snan_mult=snan_multiplier("2027-09-11"))[:5]:
        print(f"  {h['risk']:10} {h['name'][:40]:40} score={h['score']:.1f}")

    print("\nKIOSK PLACEMENT — highest-risk points with NO camera within 400m:")
    for h in [x for x in hotspots() if x["cams"] == 0][:5]:
        ps, d = nearest(h["lat"], h["lng"], police)
        print(f"  • [{h['risk']:9}] {h['name'][:34]:34} -> nearest police {ps[:22]:22} ({d:.1f} km)")

    print("\nROUTING DEMO — found person at 'Ramkund':")
    rk = next((c for c in choke if c["name"].lower().startswith("ramkund")), choke[0])
    ps, d = nearest(rk["lat"], rk["lng"], police)
    nc = cams_within(rk["lat"], rk["lng"], km=0.5)
    print(f"  nearest police station : {ps} ({d:.1f} km)")
    print(f"  cameras within 500m    : {nc} (request footage from these for a manual review)")

    print("\nSNAN-DAY STAFFING CALENDAR (official 2027 Amrit Snan dates):")
    for d, (label, occ, mult) in SNAN_2027.items():
        vh = sum(1 for h in hotspots(mult) if h["risk"] == "very high")
        print(f"  {d}  x{mult}  {label} — pre-position for {vh} very-high-risk hotspots")
