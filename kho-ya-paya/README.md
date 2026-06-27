# Kho-Ya-Paya — cross-center reunification for Kumbh Mela 2027

> *Kho-Ya-Paya* (खोया-पाया, "lost & found"). A live web app that closes the one gap:
> **a person found at any Kho-Ya-Paya center is instantly searchable at every other
> center** — offline, multilingual, with a human as the only authority that confirms a
> reunion. Pure-Python stdlib server, so the whole node runs on an $800 offline box.

Built on the Setu engine (`../setu/`). Uses **all the data**: the 2,500 missing-person
records, the 4,079-camera KML, 14 police stations, 85 risk-rated chokepoints, 32 zones,
and the official 2027 Amrit Snan calendar.

## Run it

```bash
cd kho-ya-paya
python3 server.py --reset      # --reset wipes & reseeds the two node DBs
# open http://localhost:8000
```

No `pip install`. Pure stdlib (`http.server` + `sqlite3`). The map needs internet for
OpenStreetMap tiles + Leaflet; everything else works fully offline.

## What it does

Two Kho-Ya-Paya centers (**A** and **B**) run as two SQLite replicas in one process, so
you can demonstrate the partition live.

- **Intake** — operator-mediated, voice + icon first, 10 languages in native script.
  Works with **no name, no phone, no photo**. Age/gender are tappable icons; location is a
  picker; description has a 🎤 (Claude voice-intake hook).
- **Match queue** — search by description; **confirm-only** results (no names shown) until
  an operator opens a record, which writes to the **audit log**. Minors route to a
  police-only block.
- **Operational map** — real KML risk levels, sampled cameras, police; pick a place + time
  to draw the **crowd-modulated reachable area** ("how far could they have gone?").
- **Control room** — per-node stats, sync status, risk-weighted snan-aware hotspots, audit.

### Safety, in code
- **Evidence-gated bands** — nothing reaches `AUTO-SUGGEST` without a strong identifier;
  a no-name demographic match is capped at `REVIEW` ("visual check required").
- **Reach plausibility** — a found person too far from a last-seen (given the crowd) is
  down-weighted before an operator ever sees it.
- **Confirm-only projection + audited PII fetch**; **minors hidden** from kiosk search.
- **Reunification orchestration** — on confirm, routes both parties to the nearest handoff
  (police/transfer node) and notifies the family with the phone **masked** and **no
  location in the message** (closes the trafficking-lure vector).

### The Claude layer (optional, graceful fallback)
- `claude_client.py` calls `claude-haiku-4-5` over stdlib `urllib` **if** `ANTHROPIC_API_KEY`
  is set — for **cross-script name equivalence** (Lokkhi = Lakshmi) and **voice-intake**
  structuring — and falls back to the deterministic matcher when offline. The Match-queue
  "✨ Cross-script name check" widget shows the result + whether Claude is live.

## The 90-second demo (one click)

1. Press **🎬 Load demo** → plants a missing mother (*Lakshmi Jha*) at **Center A** and
   pulls the network **OFFLINE**; pre-fills a found-elder intake at **Center B**.
2. Press **Register & search** → B searches its local replica → **0 matches from Center A**
   (she's invisible across the partition — *the gap, live*).
3. Press **📨 Courier sync** → the USB-courier propagates records both ways.
4. Press **🔁 Re-search all centers** → *Lakshmi Jha (Center A)* now appears — held at
   **REVIEW** because the elder gave no name, so the operator confirms via the **family**
   (never the confused person). The cross-center bridge is closed.

Then open **Operational map** → *Ramkund Ghat* on `2027-09-11 (3rd Amrit Snan)` shows a
tight **0.29 km** reachable circle (crush), vs **1.87 km** on an ordinary day.

## Test
```bash
python3 test_app.py     # 20 end-to-end checks (spins up its own isolated server)
```
Covers: seeding, the offline→sync partition flow, evidence-gated bands, reachability
inversion, minor block, confirm + reunification notification, and the Claude layer.

## Files
- `server.py` — stdlib HTTP server, two nodes, partition toggle, courier sync, REST API
- `store.py` — per-node SQLite store, seed-from-CSV, sync
- `claude_client.py` — optional Claude brain (name equivalence + voice), deterministic fallback
- `static/` — `index.html` · `style.css` · `app.js` (no framework, no build)
- `test_app.py` — self-contained end-to-end test harness
- `gen_deck.js` → `Kho-Ya-Paya-pitch.pptx` — the 7-slide pitch deck
- `kyp_A.db` / `kyp_B.db` — created on first run (gitignore-able)

## API (for reference)
`GET /api/state · /api/search · /api/record/{node}/{id} · /api/cases · /api/hotspots ·
/api/reachability · /api/geojson · /api/audit` ·
`POST /api/intake · /api/confirm · /api/sync · /api/online · /api/scenario`
