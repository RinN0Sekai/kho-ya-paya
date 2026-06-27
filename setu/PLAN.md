# Setu — 5-hour hackathon execution plan

**Goal:** ship a live, demoable system that closes the one gap — *"a person found at Center
A is invisible to a family at Center B"* — offline, multilingual, safety-gated, and prove it
on stage with the network cable pulled.

**One-line pitch:** *Setu makes a person found at any Kho-Ya-Paya center instantly searchable
at every other center — offline, in 10 languages, with Claude as the matching brain and a
human as the only authority that confirms a reunion.*

**The demo we are building toward (memorize this — every task serves it):**
> Two laptops = Center A and Center B. Pull the network cable. A son reports his lost mother
> at A (voice, no name typed). A volunteer finds a confused elder at B, offline. The match
> surfaces at B — held at AMBER because there's no strong identifier. A look-alike stranger
> stays AMBER too (never auto-confirmed). Reconnect via a USB "courier," the bridge converges,
> the operator confirms via the family. Close on the map + the cost: **$24k + $36/day vs the
> $1.8M camera farm that reunites no one.**

We are NOT starting from zero. The engine already works in Python (`setu_match.py`,
`eval_match.py`, `geo_intel.py`, `kml_ingest.py`, `reachability.py`). The 5 hours wrap it in
an API + a simple operator UI + the two-node offline demo + the pitch.

---

## Scope guardrails — decide once, never relitigate

| ✅ BUILD (core, demo-critical) | ❌ DO NOT BUILD (cut by the reality-check) |
|---|---|
| Two offline edge nodes + cross-center match | YOLO / any CCTV video analytics (no feed exists) |
| Evidence-gated bands (AMBER vs AUTO-SUGGEST) | ML/XGBoost risk prediction (surge isn't learnable) |
| Operator-mediated voice + icon intake | Self-serve family app / proximity-push to volunteers |
| Confirm-only search + audited PII fetch | Face recognition as a search key (missing side has no photo) |
| USB-courier sync (offline convergence) | Real-time always-on backend |
| Map: hotspots + reachability search area | Anything requiring a smartphone for the lost person |
| Live Claude: cross-script name + voice intake | Training any model from scratch |

If a task isn't on the left, it's a distraction. Park it in "stretch."

---

## Team tracks (4 people ideal; solo/2-person notes inline)

- **Track A — Backend/API & sync** (the spine)
- **Track B — Operator/Family UI** (what judges see)
- **Track C — Geo, map & Claude** (the wow)
- **Track D — Data, pitch & demo direction** (also the integrator/tester)

*Solo or 2 people:* do Phase 1 + Phase 2 only, skip the map to a static screenshot, use the
existing CLI output as the "backend" behind a minimal UI. The partition match + the safety
moment + the cost slide is enough to win.

---

## Hour-by-hour

### Phase 0 — Align & set up · `0:00 – 0:30`
**Everyone.**
- [ ] Clone repo, `python3 setu_match.py` runs for all 4 (confirm the engine works on every laptop).
- [ ] Lock the demo script above. Write it on the whiteboard. Nobody builds anything not in it.
- [ ] Decide UI stack: **FastAPI + static HTML/JS** (recommended) *or* **Streamlit** (faster UI, less control). Pick one and commit.
- [ ] Get the `ANTHROPIC_API_KEY` working for Track C (`claude-haiku-4-5` test call).
- [ ] Create 2 SQLite DBs: `node_A.db`, `node_B.db`. Seed both from the 2,500-row CSV split by `reporting_center`.

**Checkpoint 0:30 — engine runs everywhere, scope locked, stack chosen.**

### Phase 1 — Backend API + two-node sync · `0:30 – 1:45`
**Track A (lead) + Track D.**
Wrap the existing engine in FastAPI. Run two instances: `:8001` (Center A), `:8002` (Center B).
- [ ] `POST /intake` → add a MISSING or FOUND record (uses `Person` + `Registry.add`).
- [ ] `GET /search` → returns `search_projection()` (confirm-only: case_id, band, score, age_band, zone — **no names**).
- [ ] `GET /record/{id}` → `get_full_record(actor, role, reason)`, writes to `AUDIT_LOG`.
- [ ] `POST /confirm` → mark a match link confirmed (status → Reunited).
- [ ] `POST /sync` → **the money endpoint:** node pulls the other node's new records (simulates the USB courier). An `online: true/false` flag gates auto-sync so we can demo the partition.
- [ ] Append-only event list per node so sync is just "send events since last cursor."

**Definition of done:** add a record at A → it does NOT appear at B → hit `/sync` → it appears at B and is matchable. Test from `curl` before any UI exists.

**Checkpoint 1:45 — offline cross-center match works at the API level (curl-proven).**

### Phase 2 — Operator + family UI · `0:30 – 3:00` (starts in parallel)
**Track B (lead), wires to A's API once Phase 1 lands ~1:45.**
Three screens, icon-first, big text, photo-forward (this IS the non-literate UX story):
- [ ] **Intake screen:** language picker (10 flags/scripts), big record-type toggle (missing / found), photo upload, age-band + gender as **tappable icons** (not dropdowns), a tap-a-landmark location picker, a "🎤 speak" button (Track C fills the voice logic).
- [ ] **Match queue / results:** side-by-side cards, colored confidence band (GREEN/AMBER/RED), the reason line, thumbnail. **Never render a name in the list** — show the confirm-only projection; reveal PII only on an explicit "view record" click (demonstrates the privacy boundary live).
- [ ] **Confirm flow:** the identity-proof prompt aimed at the *searching family* ("what was she wearing? who did she come with?"), then a confirm button → calls `/confirm`.
- [ ] Mini header stat bar: open cases · pending matches · reunified.

**Definition of done:** an operator can run the whole intake→search→confirm loop in the browser against node A, then node B.

**Checkpoint 3:00 — full UI loop works on one node.**

### Phase 3 — Map, reachability & live Claude · `1:00 – 4:00` (parallel)
**Track C (lead).**
- [ ] **Leaflet map** centered on Nashik; plot from the KML: very-high-risk chokepoints, 14 police stations, zones. (Use `kml_ingest.py` to dump GeoJSON.)
- [ ] **Reachability overlay:** on a selected case, draw the `reachability.py` search circle (snan vs ordinary) + dwell points. This is the "how far could they have gone" wow moment.
- [ ] **`GET /reachability`** and **`GET /hotspots`** endpoints (thin wrappers over the existing functions).
- [ ] **Live Claude (the language story):** wire `claude-haiku-4-5` into the `claude_name_sim` hook in `setu_match.py` so **Lokkhi == Lakshmi** resolves on stage where the deterministic fallback fails. Plus voice-intake: audio → Claude → structured fields + spelling read-back.
- [ ] Keep the **offline fallback visible**: a toggle that "kills" Claude and shows the deterministic path still returns (band-capped) candidates.

**Definition of done:** map shows hotspots + a reachability circle; one live Claude cross-script match works; offline toggle still returns results.

**Checkpoint 4:00 — map + Claude land. FEATURE FREEZE.**

### Phase 4 — Integrate, safety polish & dry-run · `4:00 – 4:35`
**Everyone. No new features.**
- [ ] Wire the two nodes + UI + map into the **single partition demo path**. Walk it end to end twice.
- [ ] Plant the **look-alike stranger** record so the AMBER-not-GREEN safety beat is guaranteed to fire.
- [ ] Plant the **minor case** → show it routes to the police-only queue, invisible to kiosk search (30-second beat, cut if behind).
- [ ] Seed the exact demo records (son@A, mother, found-elder@B) so timing is deterministic — **never live-type during the pitch.**
- [ ] Screenshot/record every screen as a fallback in case live fails.

**Checkpoint 4:35 — the demo runs start-to-finish without a hitch, twice.**

### Phase 5 — Pitch & rehearse · `4:35 – 5:00`
**Track D (lead) + presenter.**
- [ ] 6-slide deck: problem → the one gap → architecture (1 diagram) → live demo → the numbers → the ask.
- [ ] The cost slide: **$24k + $36/day vs $0.6–1.8M YOLO with no feed.** This is the mic-drop.
- [ ] Rehearse the 3-minute demo **twice**, timed. Presenter speaks, one person drives.
- [ ] Have the fallback recording cued.

**5:00 — done.**

---

## The 3-minute demo script (rehearse verbatim)

1. **[0:00] The gap.** "10 lost-and-found centers that can't see each other. Pull the cable."
2. **[0:30] Report at A.** Son reports his mother — voice, Maithili, no name typed, photo, tap-landmark. Record written offline in <2s. *"He gave HIS phone number, not hers — she's phoneless. That's the whole population we serve."*
3. **[1:00] Found at B, offline.** Volunteer logs a confused elder — photo, GPS, tapped age/gender. The match surfaces **AMBER: "visual check required."** *"No name, no phone, no face — we refuse to claim a confident match. Watch the stranger."* Look-alike stays AMBER.
4. **[1:50] Reunite.** USB courier sync → bridge converges. Identity-proof asks the **family** about the mother. Confirm → Reunited. Show the reachability circle: *"on a snan day she couldn't have gone 300m."*
5. **[2:30] The numbers.** Privacy projection (no names) on screen. *"$24k and $36/day. The camera farm other teams demo costs $1.8M and reunites no one."*

---

## Judging-criteria → what proves it

| Criterion | The moment in our demo |
|---|---|
| Deployability | $800 boxes, runs offline, uses existing centers/police/CCTV |
| Real-world fit | Closes the literal cross-center gap from the problem statement |
| UX (phoneless/non-literate) | Voice + icon + photo intake; family needs no device |
| System design | Offline-first, append-only sync, duplicate + incomplete-data handling |
| Responsible data | Confirm-only search, audited PII, AMBER governor, police-only minor queue |

---

## Risk & cut-line (when you're behind — and you will be)

**Must-have (if we only get these, we still win):**
1. Two nodes + offline cross-center match surfacing with a band.
2. The stranger-held-at-AMBER safety beat.
3. The cost slide.

**Cut in this order if time runs out:** minor-queue beat → live voice intake → reachability
overlay → live Claude (fall back to the precomputed cross-script example) → map (static
screenshot). **Never cut:** the partition match, the AMBER safety moment, the cost number.

**Top risks:** (1) frontend↔API integration eats time → freeze the API contract at 1:45 and
mock it. (2) Live Claude flakes on stage → always have the precomputed result. (3) Live-typing
during the demo → everything is pre-seeded. (4) Scope creep into a dashboard → it's on the
"don't build" list.

---

## Setup checklist (do before the clock starts)
- [ ] `python3 setu_match.py` runs on every laptop
- [ ] `ANTHROPIC_API_KEY` exported and a `claude-haiku-4-5` test call returns
- [ ] FastAPI + uvicorn (or Streamlit) installed; Leaflet via CDN
- [ ] Two terminals ready for `:8001` / `:8002`
- [ ] The demo records drafted in a text file, ready to seed

## Stretch (only if green by 4:00)
- Control-room dashboard (queue depth, reunion-time tail, node health)
- Snan-day surge re-ranking on the map (`geo_intel.py` already computes it)
- SMS/PA outbound notification mock for the phoneless family
