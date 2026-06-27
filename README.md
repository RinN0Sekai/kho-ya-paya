# Kho-Ya-Paya — cross-center reunification for Kumbh Mela 2027

> *Kho-Ya-Paya* (खोया-पाया, "lost & found"). A person **found at any lost-and-found center
> becomes instantly searchable at every other center** — offline, multilingual, with a human
> as the only authority that confirms a reunion. Pure-Python stdlib (no pip): the whole node
> runs on an ~$800 offline edge box.

Built for the Claude Impact Lab, Mumbai 2026. Uses all five provided datasets (2,500 missing-
person records, 4,079-camera KML, 14 police stations, 85 risk-rated chokepoints, 32 zones)
plus the official 2027 Amrit Snan calendar.

## Run locally (recommended — this is the real target)
```bash
cd kho-ya-paya && python3 server.py --reset      # no pip, pure stdlib
# open http://localhost:8000  →  press "Load demo" for the 90-second story
python3 test_app.py                              # 20 end-to-end checks
```

## What it does
- **Intake** — operator-mediated, voice + icon first, 10 languages in native script; works with
  no name, no phone, no photo.
- **Match queue** — confirm-only results (no names until an audited reveal); evidence-gated
  bands; a ✨ cross-script name check (Lokkhi = Lakshmi).
- **Operational map** — real KML risk levels, cameras, police; crowd-modulated reachability
  ("how far could they have gone?").
- **Control room** — per-node stats, sync status, risk-weighted snan-aware hotspots, audit.
- **Safety in code** — nothing AUTO-SUGGESTs without a strong identifier; confirm-only search;
  audited PII; minors police-only; reunification routes to a handoff and notifies the family
  with the phone masked and no location in the message.

## Deploy

**Process host (Render / Railway / Fly) — runs the real stateful app as-is, recommended.**
A `Procfile` is included (`web: python3 kho-ya-paya/server.py`; the server honours `$PORT`).
On Render: New → Web Service → connect this repo → Build `pip install -r requirements.txt`
(it's empty) → Start `python3 kho-ya-paya/server.py`. One click, the full demo works.

**Vercel — hosted UI + matching-engine preview.** `vercel.json` + `api/index.py` adapt the
app to Vercel's Python runtime. Search, map, reachability, hotspots and the name-check work
per request; but because Vercel is serverless, the live partition state (records added via
Load demo, the online/offline toggle, courier sync) resets on cold starts. For the full
offline + partition demo, use a process host or run locally.

## Docs
- `kho-ya-paya/README.md` — the app
- `setu/SETU_BLUEPRINT.md` — full production spec
- `setu/CONSTRAINT_REALITY_CHECK.md` — the 12-crore / economics / non-literacy verdict
- `setu/PLAN.md` — the 5-hour build plan
- `kho-ya-paya/Kho-Ya-Paya-pitch.pptx` — pitch deck

Missing-person records are synthetic (no real personal data). Geo data credited to the
Kumbhathon Innovation Foundation.
