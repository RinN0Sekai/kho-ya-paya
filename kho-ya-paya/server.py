"""
Kho-Ya-Paya — unified cross-center reunification node (pure stdlib HTTP server).

Runs TWO Kho-Ya-Paya centers (A and B) in one process, each with its own SQLite replica,
so you can demonstrate the core gap live: a person found at Center B surfaces against a
family's report at Center A — even while the network is "offline" — then converges on a
"USB courier" sync. Wraps the Setu engine (matching, geo-intelligence, reachability).

Run:  python3 server.py [--port 8000] [--reset]
Open: http://localhost:8000
"""
import os, sys, json, argparse, urllib.parse, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "setu"))

import setu_match as eng
import geo_intel, reachability, kml_ingest
import claude_client
from store import Store

# Split the 10 centers across two nodes so the cross-center gap is real from t=0.
CENTERS_A = ["Adgaon Kho-Ya-Paya", "Panchavati Center", "Ramkund Kho-Ya-Paya Kendra",
             "Bharat Bharati Control Room", "Central Control Room"]
CENTERS_B = ["Rajur Bahula Center", "Trimbakeshwar Kho-Ya-Paya Kendra", "Nashik Road Center",
             "Sadhugram Lost Found", "Police Main Control Room"]

STATE = {"online": True}
NODES = {}
_REG_CACHE = {}


def build_registry(node):
    st = NODES[node]
    reg = eng.Registry()
    for r in st.all_records():
        reg.add(eng.Person(
            case_id=r["case_id"], name=r["name"] or "", gender=r["gender"] or "",
            age_band=r["age_band"] or "", state=r["state"] or "", district=r["district"] or "",
            language=r["language"] or "", last_seen=r["last_seen"] or "",
            center=r["center"] or "", mobile=r["mobile"] or "",
            description=r["description"] or "", kind=r["kind"] or "missing"))
    return reg


def registry(node):
    if node not in _REG_CACHE:
        _REG_CACHE[node] = build_registry(node)
    return _REG_CACHE[node]


def invalidate(node=None):
    if node:
        _REG_CACHE.pop(node, None)
    else:
        _REG_CACHE.clear()


def _hour(ts):
    try:
        return float(ts[11:13]) + float(ts[14:16]) / 60.0
    except Exception:
        return None


def _date(ts):
    return ts[:10] if ts and len(ts) >= 10 else "2027-09-11"


def candidate_view(node, q, m):
    """Confirm-only projection of one match, enriched with reachability when possible."""
    c = m.candidate
    rec = NODES[node].get(c.case_id) or {}
    out = {
        "case_id": c.case_id, "band": m.band, "score": m.score, "note": m.note,
        "strong_identifier": m.strong_identifier, "kind": rec.get("kind"),
        "age_band": c.age_band, "gender_obscured": True,
        "last_seen_zone": c.last_seen, "center": c.center,
        "status": rec.get("status"), "origin_node": rec.get("origin_node"),
    }
    # geographic plausibility: was the FOUND person reachable from this MISSING last-seen?
    try:
        if q.kind == "found" and rec.get("kind") == "missing":
            fr = resolve = reachability.resolve_place(q.last_seen)
            mp = reachability.resolve_place(c.last_seen)
            if fr and mp:
                date = _date(rec.get("reported_at"))
                sh = _hour(rec.get("reported_at")) or 12.0
                fh = (sh + 2.0)
                out["reach_plausibility"] = round(
                    reachability.reach_plausibility(c.last_seen, date, sh, fr[1], fr[2], fh), 2)
    except Exception:
        pass
    return out


def search_node(node, q, top_k=6):
    reg = registry(node)
    cand_ids = reg.candidates(q)
    # Description-only / semantic search: free-text description is NOT a blocking key, so a
    # search with just a description blocks to nothing. Fall back to a bounded full scan
    # (the pool is only thousands of rows) scored by description + any demographics.
    if not cand_ids and (q.description or q.name):
        cand_ids = set(reg.people.keys())
    cand_ids.discard(q.case_id)
    scored = []
    for cid in cand_ids:
        p = reg.people.get(cid)
        if not p:
            continue
        m = eng.score_pair(q, p)
        if m.band != "NONE":
            scored.append(m)
    scored.sort(key=lambda m: m.score, reverse=True)
    views = []
    for m in scored:
        rec = NODES[node].get(m.candidate.case_id) or {}
        # a FOUND person reunites with a MISSING report — found↔found is not a reunion
        if q.kind == "found" and rec.get("kind") == "found":
            continue
        views.append(candidate_view(node, q, m))
        if len(views) >= top_k:
            break
    return views


def person_from(d):
    return eng.Person(
        case_id=d.get("case_id", "QUERY"), name=d.get("name", ""), gender=d.get("gender", ""),
        age_band=d.get("age_band", ""), state=d.get("state", ""), district=d.get("district", ""),
        language=d.get("language", ""), last_seen=d.get("last_seen", ""),
        center=d.get("center", ""), mobile=d.get("mobile", ""),
        description=d.get("description", ""), kind=d.get("kind", "found"))


def do_sync():
    """USB-courier sync: copy every record each node is missing, both directions."""
    a, b = NODES["A"], NODES["B"]
    a2b = sum(1 for r in a.all_records() if b.import_record(r))
    b2a = sum(1 for r in b.all_records() if a.import_record(r))
    if a2b or b2a:
        invalidate()
    return {"A_to_B": a2b, "B_to_A": b2a}


def _mask_mobile(m):
    d = "".join(ch for ch in (m or "") if ch.isdigit())
    return f"+91 {d[-10:-5]} XXXXX" if len(d) >= 10 else (m or "no number on file")

def reunion_notification(found_rec, missing_rec):
    """Reunification orchestration: route both parties to the nearest common handoff
    point and notify the (phoneless) family WITHOUT putting the person's location in a
    message — location resolves operator-to-operator only, closing the trafficking lure."""
    loc = (found_rec or missing_rec or {}).get("last_seen", "") or "Ramkund Ghat"
    place = reachability.resolve_place(loc)
    handoff = "the nearest staffed help point"
    if place:
        hn, d = geo_intel.nearest(place[1], place[2], geo_intel.police)
        handoff = f"{hn} ({d:.1f} km away)"
    fam = _mask_mobile((missing_rec or {}).get("mobile"))
    who = (missing_rec or {}).get("name") or "your relative"
    return {
        "handoff": handoff,
        "pa_announcement": f"📢 PA (10 languages): Family of {who} — a possible match has been "
                           f"found. Please come to {handoff} to confirm.",
        "sms_to_family": f"SMS → {fam}: A possible match for {who} has been found at a "
                         f"Kho-Ya-Paya help point. Please come to {handoff} to confirm. "
                         f"For their safety we never send their location by message.",
        "safeguard": "Location is shared operator-to-operator only — never to a raw phone "
                     "number — so a spoofed message can't lure a family or a child.",
    }


# --------------------------------------------------------------------------- #
# Geo / map data
# --------------------------------------------------------------------------- #
def geojson():
    feats = []
    for c in geo_intel.choke:
        feats.append({"t": "choke", "name": c["name"], "risk": c["risk"],
                      "lat": c["lat"], "lng": c["lng"], "category": c["category"]})
    for p in geo_intel.police:
        feats.append({"t": "police", "name": p["name"], "lat": p["lat"], "lng": p["lng"]})
    # sample cameras so the payload stays light (every 8th of ~4,079)
    for i, cam in enumerate(geo_intel.cameras):
        if i % 8 == 0:
            feats.append({"t": "cam", "lat": cam["lat"], "lng": cam["lng"], "kind": cam["kind"]})
    return feats


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return {}

    def _qs(self):
        return {k: v[0] for k, v in
                urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()}

    # ---- routing ---- #
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/" or path == "":
            return self._file("index.html")
        if path.startswith("/static/"):
            return self._file(path[len("/static/"):])
        if path.startswith("/api/"):
            return self._api_get(path, self._qs())
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/"):
            return self._api_post(path, self._body())
        return self._send(404, {"error": "not found"})

    def _file(self, rel):
        fp = os.path.normpath(os.path.join(HERE, "static", rel))
        if not fp.startswith(os.path.join(HERE, "static")) or not os.path.isfile(fp):
            return self._send(404, "not found", "text/plain")
        ctype = ("text/html" if fp.endswith(".html") else "text/css" if fp.endswith(".css")
                 else "application/javascript" if fp.endswith(".js") else "text/plain")
        with open(fp, "rb") as f:
            self._send(200, f.read(), ctype)

    def _api_get(self, path, qs):
        try:
            if path == "/api/state":
                return self._send(200, {
                    "online": STATE["online"],
                    "nodes": {n: {**NODES[n].stats(), "centers": list(NODES[n].centers)}
                              for n in NODES}})
            if path == "/api/search":
                node = qs.get("node", "A")
                return self._send(200, {"matches": search_node(node, person_from(qs))})
            if path == "/api/cases":
                node = qs.get("node", "A")
                kind = qs.get("kind")
                rows = [r for r in NODES[node].all_records()
                        if (not kind or r["kind"] == kind)]
                rows = sorted(rows, key=lambda r: r.get("created_at", ""), reverse=True)[:40]
                return self._send(200, {"cases": [
                    {"case_id": r["case_id"], "kind": r["kind"], "band": "",
                     "age_band": r["age_band"], "gender": r["gender"], "status": r["status"],
                     "last_seen": r["last_seen"], "origin_node": r["origin_node"],
                     "has_name": bool(r["name"])} for r in rows]})
            if path.startswith("/api/record/"):
                _, _, _, node, cid = path.split("/", 4)
                actor = qs.get("actor", "op-demo")
                role = qs.get("role", "operator")
                rec = NODES[node].get(cid)
                NODES[node].audit(actor, role, cid, "PII_FETCH", qs.get("reason", "match review"))
                if not rec:
                    return self._send(404, {"error": "not found"})
                if rec["age_band"] in ("0-12", "13-17") and role != "police":
                    NODES[node].audit(actor, role, cid, "PII_DENIED_MINOR", "")
                    return self._send(403, {"error": "minor — police-only queue",
                                            "minor_block": True})
                return self._send(200, {"record": rec})
            if path == "/api/hotspots":
                mult = float(qs.get("snan", "1") or 1)
                hs = geo_intel.hotspots(snan_mult=mult)[:12]
                return self._send(200, {"hotspots": [
                    {"name": h["name"], "risk": h["risk"], "lat": h["lat"], "lng": h["lng"],
                     "reports": h["live"], "cams": h["cams"], "score": round(h["score"], 1)}
                    for h in hs]})
            if path == "/api/reachability":
                place = qs.get("place", "Ramkund Ghat")
                date = qs.get("date", "2027-09-11")
                t0 = float(qs.get("t0", "12")); t1 = float(qs.get("t1", "14"))
                s = reachability.search_area(place, date, t0, t1)
                if not s:
                    return self._send(404, {"error": "place not in gazetteer"})
                s = dict(s)
                s["priority_points"] = [{"name": n, "category": cat, "dist_km": round(d, 2)}
                                        for _, d, n, cat in s["priority_points"]]
                return self._send(200, s)
            if path == "/api/geojson":
                return self._send(200, {"features": geojson()})
            if path == "/api/audit":
                node = qs.get("node", "A")
                return self._send(200, {"audit": NODES[node].recent_audit()})
            if path == "/api/places":
                return self._send(200, {"places": list(reachability.GAZETTEER.keys())})
            if path == "/api/snan":
                return self._send(200, {"snan": kml_ingest.SNAN_2027})
            if path == "/api/claude/status":
                return self._send(200, {"available": claude_client.available()})
            if path == "/api/claude/name":
                return self._send(200, claude_client.name_equivalence(
                    qs.get("a", ""), qs.get("b", "")))
            return self._send(404, {"error": "unknown endpoint"})
        except Exception as e:
            return self._send(500, {"error": str(e)})

    def _api_post(self, path, body):
        try:
            if path == "/api/online":
                STATE["online"] = bool(body.get("online", True))
                return self._send(200, {"online": STATE["online"]})
            if path == "/api/claude/voice":
                return self._send(200, claude_client.voice_extract(
                    body.get("text", ""), body.get("language", "Hindi")))
            if path == "/api/sync":
                return self._send(200, {"synced": do_sync(), "online": STATE["online"]})
            if path == "/api/scenario":
                # Plant a clean, known cross-center demo: a mother reported missing at A,
                # network forced OFFLINE so B cannot see her until the courier sync.
                STATE["online"] = False
                mid = NODES["A"].add({
                    "kind": "missing", "name": "Lakshmi Jha", "gender": "Female",
                    "age_band": "71-80", "state": "Bihar", "district": "Madhubani",
                    "language": "Maithili", "last_seen": "Ramkund Ghat",
                    "center": "Ramkund Kho-Ya-Paya Kendra", "mobile": "+91 90000 12345",
                    "description": "old woman white saree walks with a stick hard of hearing",
                    "reported_at": time.strftime("%Y-%m-%d %H:%M")})
                invalidate("A")
                return self._send(200, {"missing_id": mid, "online": STATE["online"],
                    "found_suggestion": {"node": "B", "kind": "found", "gender": "Female",
                        "age_band": "71-80", "language": "Maithili", "last_seen": "Ramkund Ghat",
                        "name": "", "description": "old woman white saree, walks with a stick, confused"}})
            if path == "/api/intake":
                node = body.get("node", "A")
                rec = {k: body.get(k, "") for k in
                       ["kind", "name", "gender", "age_band", "state", "district", "language",
                        "last_seen", "center", "mobile", "description", "photo"]}
                rec["reported_at"] = time.strftime("%Y-%m-%d %H:%M")
                cid = NODES[node].add(rec)
                invalidate(node)
                # if online, auto-propagate to the peer (gossip); else it waits for courier
                if STATE["online"]:
                    do_sync()
                q = person_from({**rec, "case_id": cid})
                # a FOUND record searches the missing pool; a MISSING report searches found+dupes
                matches = search_node(node, q)
                return self._send(200, {"case_id": cid, "matches": matches})
            if path == "/api/confirm":
                node = body.get("node", "A")
                found_id, missing_id = body.get("found_id"), body.get("missing_id")
                actor = body.get("actor", "op-demo")
                grp = f"MG-{found_id}-{missing_id}"
                missing_rec = found_rec = None
                for n in NODES:
                    for cid in (found_id, missing_id):
                        r = NODES[n].get(cid)
                        if r:
                            NODES[n].set_status(cid, "Reunited", grp)
                            NODES[n].audit(actor, "operator", cid, "REUNION_CONFIRMED", grp)
                            if r["kind"] == "missing":
                                missing_rec = r
                            else:
                                found_rec = r
                invalidate()
                return self._send(200, {"ok": True, "match_group": grp,
                                        "notification": reunion_notification(found_rec, missing_rec)})
            return self._send(404, {"error": "unknown endpoint"})
        except Exception as e:
            return self._send(500, {"error": str(e)})


def boot(dbdir=HERE, reset=False):
    """Seed the two center replicas. Importable so a serverless host (Vercel) can call it
    once at cold start with dbdir='/tmp'. Idempotent — skips reseed if a DB already has rows."""
    os.makedirs(dbdir, exist_ok=True)
    for node, centers in (("A", CENTERS_A), ("B", CENTERS_B)):
        db = os.path.join(dbdir, f"kyp_{node}.db")
        if reset and os.path.exists(db):
            os.remove(db)
        st = Store(node, db, centers)
        st.seed_if_empty()
        NODES[node] = st
    return NODES


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--reset", action="store_true", help="wipe node DBs and reseed")
    ap.add_argument("--dbdir", default=HERE, help="where to store the node SQLite files")
    args = ap.parse_args()

    boot(args.dbdir, args.reset)
    for node in NODES:
        print(f"  node {node}: {NODES[node].count()} records")

    port = int(os.environ.get("PORT", args.port))   # process hosts (Render/Railway) set $PORT
    srv = ThreadingHTTPServer(("0.0.0.0", port), H)
    print(f"\n  Kho-Ya-Paya running →  http://localhost:{port}\n")
    srv.serve_forever()


if __name__ == "__main__":
    main()
