"""
Kho-Ya-Paya — self-contained end-to-end test.

Spins up its own server on a test port with a temp DB, exercises the full partition
flow + safety rules over HTTP, then tears down. Pure stdlib. Run: python3 test_app.py
Exits non-zero on any failure.
"""
import subprocess, sys, os, time, json, urllib.request, urllib.error, urllib.parse, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8099
BASE = f"http://localhost:{PORT}"

def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=10) as resp:
        return json.loads(resp.read())

PASS, FAIL = 0, 0
def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  \033[32mPASS\033[0m {name}")
    else:
        FAIL += 1; print(f"  \033[31mFAIL\033[0m {name}  {detail}")

def main():
    tmp = tempfile.mkdtemp()
    # run server with DBs in a temp dir by copying server but pointing DB via cwd trick:
    # server writes kyp_*.db next to server.py; use --reset to guarantee clean seed.
    proc = subprocess.Popen([sys.executable, os.path.join(HERE, "server.py"),
                             "--reset", "--port", str(PORT), "--dbdir", tmp],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # wait for boot
        for _ in range(40):
            try:
                req("GET", "/api/state"); break
            except Exception:
                time.sleep(0.25)
        else:
            print("server did not start"); sys.exit(2)

        print("\n1. seeding & state")
        st = req("GET", "/api/state")
        check("two nodes seeded", set(st["nodes"]) == {"A", "B"})
        check("node A has records", st["nodes"]["A"]["total"] > 1000, st["nodes"]["A"]["total"])
        check("node B has records", st["nodes"]["B"]["total"] > 1000, st["nodes"]["B"]["total"])

        print("\n2. partition: offline scenario")
        req("POST", "/api/online", {"online": False})
        sc = req("POST", "/api/scenario", {})
        mid = sc["missing_id"]
        check("planted missing at A", mid.startswith("KYP-A"))
        check("scenario forced offline", sc["online"] is False)
        f = sc["found_suggestion"]
        intake = req("POST", "/api/intake", {**f})
        from_a = [m for m in intake["matches"] if m["origin_node"] == "A"]
        check("OFFLINE: 0 cross-center matches from A", len(from_a) == 0,
              f"got {len(from_a)}")

        print("\n3. courier sync closes the gap")
        sy = req("POST", "/api/sync", {})
        check("sync moved records A->B", sy["synced"]["A_to_B"] > 0, sy["synced"])
        res = req("GET", "/api/search?" + "&".join(
            f"{k}={urllib.parse.quote(str(v))}" for k, v in
            {"node": "B", "kind": "found", "gender": "Female", "age_band": "71-80",
             "language": "Maithili", "last_seen": "Ramkund Ghat"}.items()))
        a_hits = [m for m in res["matches"] if m["origin_node"] == "A"]
        check("AFTER SYNC: Center-A record now visible at B", len(a_hits) > 0,
              f"got {len(a_hits)}")

        print("\n4. evidence-gated safety (no-name -> never AUTO-SUGGEST)")
        nameless = req("POST", "/api/intake", {"node": "B", "kind": "found",
            "gender": "Female", "age_band": "71-80", "language": "Maithili",
            "last_seen": "Ramkund Ghat", "description": "old woman white saree"})
        autos = [m for m in nameless["matches"] if m["band"] == "AUTO-SUGGEST"]
        check("no-name found never AUTO-SUGGESTs a stranger", len(autos) == 0,
              f"{len(autos)} auto-suggested")
        check("candidates are held at REVIEW", any(m["band"] == "REVIEW" for m in nameless["matches"]))

        print("\n5. reachability: crowd inverts the radius")
        snan = req("GET", "/api/reachability?place=Ramkund%20Ghat&date=2027-09-11&t0=12&t1=14")
        ordn = req("GET", "/api/reachability?place=Ramkund%20Ghat&date=2027-07-20&t0=12&t1=14")
        check("snan radius < ordinary radius (crush shrinks search)",
              snan["max_radius_km"] < ordn["max_radius_km"],
              f"snan {snan['max_radius_km']} vs ordinary {ordn['max_radius_km']}")
        check("snan density higher", snan["density"] > ordn["density"])

        print("\n6. privacy: minor is police-only, confirm-only search hides names")
        cases = req("GET", "/api/cases?node=A&kind=missing")["cases"]
        minor = next((c for c in cases if c["age_band"] in ("0-12", "13-17")), None)
        if minor:
            try:
                req("GET", f"/api/record/A/{minor['case_id']}?role=operator&reason=t")
                check("minor blocked for operator", False, "no 403 raised")
            except urllib.error.HTTPError as e:
                check("minor blocked for operator", e.code == 403, f"code {e.code}")
        check("search projection carries no name field",
              all("name" not in m for m in res["matches"]))

        print("\n7. confirm reunion")
        if a_hits:
            ok = req("POST", "/api/confirm", {"node": "B", "found_id": intake["case_id"],
                                              "missing_id": a_hits[0]["case_id"]})
            check("confirm returns match group", "match_group" in ok)
            n = ok.get("notification", {})
            check("reunion routes to a handoff point", bool(n.get("handoff")), n)
            check("family SMS withholds the person's location",
                  "operator-to-operator" in n.get("safeguard", ""))

        print("\n8. Claude layer (offline fallback)")
        st2 = req("GET", "/api/claude/status")
        check("claude status endpoint", "available" in st2)
        ne = req("GET", "/api/claude/name?a=Lakshmi%20Jha&b=Laxmi%20Jha")
        check("cross-script same-name scores high", ne["equiv"] >= 0.85, ne)
        nd = req("GET", "/api/claude/name?a=Pushpa%20Roy&b=Pushpa%20Nair")
        check("different surnames score low", nd["equiv"] < 0.7, nd)

    finally:
        proc.terminate()
        try: proc.wait(timeout=5)
        except Exception: proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{'='*44}\n  {PASS} passed, {FAIL} failed\n{'='*44}")
    sys.exit(1 if FAIL else 0)

if __name__ == "__main__":
    main()
