# Setu — cross-center reunification network for Kumbh Mela 2027

> *Setu* (सेतु, "bridge"). An offline-first, human-operated system that makes a person
> **found at any lost-and-found center instantly searchable at every other center** —
> built for the phoneless, non-literate, multilingual elderly pilgrims who actually go
> missing, with **Claude as the multilingual matching brain** and a **human (and police
> for minors) as the only authority that ever confirms a reunion.**

Claude Impact Lab Mumbai 2026 · Missing Persons at Nashik–Trimbakeshwar Simhastha (80M pilgrims)

---

## The one gap we close

There are ~10 manual *Kho-Ya-Paya* (lost-and-found) centers. **They cannot see each
other.** A grandmother found at Ramkund is invisible to her family searching at Adgaon.
Today that gap is bridged by paper, PA announcements, and luck.

We verified the problem against the 2,500-record dataset and built the fix as runnable code.

### What the data actually says (and what most teams get wrong)

| Finding (verified in `claude-impact-labs-data`) | Design consequence |
|---|---|
| **2,008 reporter mobiles, 2,008 distinct, 0 collisions** | Mobile is the *family's* number → it can **never** be a person-dedup key. Most teams block on it and catch zero cross-center duplicates. |
| **Gender contradicts the description in 47.7%** of checkable rows | Putting gender in the blocking key silently drops ~half the true pairs. We **remove gender from blocking**, keep it as a soft score only. |
| **14.8% no name · 19.7% no mobile** | The strongest identifiers are missing exactly for the at-risk cohort. Matching must work on demographics + geography + description. |
| **288 minors (11.5%), 45 with no name, 20 gender-Unknown** | Minors get a **separate police-only pipeline**, invisible to general kiosk search. |
| **61–80 age bands = 49%**, 10 languages, names transliterate many ways | Multilingual fuzzy/transliteration matching is the core technical problem → Claude. |
| `is_duplicate_report` flag has **no linkable twin records** | You cannot compute recall against it. We evaluate by **controlled perturbation + a negative control** instead. |
| **KML layers** add real **risk levels** (6 very-high / 24 high / 55 medium chokepoints), a **4,079-point planned camera network**, ring-road geometry, and the **official 2027 Amrit Snan calendar** | The hotspot model uses the organizers' own risk weights + the real surge dates, not guesses. See [`kml_ingest.py`](kml_ingest.py). |

---

## System architecture

```
        ┌─────────────────────────── REGIONAL CLOUD (ap-south-1) ───────────────────────────┐
        │   Postgres durable merge · control-room dashboard · nightly opus dedup audit       │
        │                       (NEVER on the life-safety path)                              │
        └───────────────▲───────────────────────────────────────────────▲────────────────────┘
                        │  store-and-forward over dual-SIM, opportunistic │
   ┌────────────────────┴────────────────┐                  ┌────────────┴───────────────────┐
   │  EDGE NODE  ·  Center A (Adgaon)     │   5GHz LOS /     │  EDGE NODE · Center B (Ramkund) │
   │  ~$800 rugged box, IP65, solar+UPS   │◀── sneakernet ──▶│  full local replica, matches   │
   │  full replica · matches OFFLINE      │   USB courier ·  │  OFFLINE on a snan day          │
   │  intake UI · blocker · Claude cache  │   LoRa beacons   │                                 │
   └───▲─────────────────────────────▲────┘                  └───────▲─────────────────────────┘
       │ write-through                │                              │
  ┌────┴─────┐                  ┌─────┴───────────┐          ┌───────┴─────────────┐
  │ Operator │                  │ Roving capture  │          │ Family search       │
  │ kiosk    │  voice + icons   │ tablet (FOUND)  │  photo   │ (phoneless OK)      │
  │ 10 langs │  Claude ASR      │ no PII cache    │  + GPS   │                     │
  └──────────┘                  └─────────────────┘          └─────────────────────┘

  Append-only, ed25519-signed, content-addressed EVENT LOG  ·  CRDT set-union merge
  (identities are NEVER auto-merged — only operator-confirmed links; minors need police co-sign)
```

**8 components:** Edge Node · Roving Capture Tablet · Sync Fabric · Matching Engine ·
Claude Orchestrator · Geo-Intelligence · Reunification Orchestrator · Privacy & Safety Kernel.
See [`SETU_BLUEPRINT.md`](SETU_BLUEPRINT.md) for the full spec of each.

---

## The core: cross-center matching engine (`setu_match.py`)

Reunification is **bipartite entity resolution**: a FOUND record (person is present) must
meet a MISSING report (family is searching), across centers, with fields missing and
names transliterated. Two stages:

1. **Blocking** — cheap deterministic keys generate a small candidate set (avoids O(n²)):
   phonetic + transliteration name keys, `age-band-window × state` (**no gender**), geo-node,
   mobile-suffix. *94% search reduction* on the real data.
2. **Evidence-gated scoring** — a weighted feature model (name, mobile, age, geo,
   description, …) maps to confidence **bands**. The safety-critical rule:

   > **Nothing reaches AUTO-SUGGEST without a strong identifier** (exact mobile, a face
   > match, or name-equivalence ≥ 0.90). Demographics + geography + a vague description are
   > capped at **REVIEW — "visual/family check required."** Many different people share
   > *Female / 71-80 / Bihar / Ramkund Ghat*; a confident match there is a stranger risk.

The engine **only suggests** — a human confirms every link; minors and non-lucid adults
require police co-sign. Claude is advisory and **can never authorize a handoff.**

```
$ python3 setu_match.py
CASE 1 — FOUND with a name: Pushpa Rai, 41-60, seen Ramkund Ghat
  #1 [AUTO-SUGGEST]  84.9  Pushpa Roy  | Rajasthan | Panchavati Center   <- strong id (true cross-center match)
  #2 [REVIEW      ]  73.3  Pushpa Nair | Uttarakhand                     (stranger — correctly held)
CASE 2 — FOUND with NO name: Female, 71-80, Bihar, seen Ramkund Ghat
  #1..#4 all [REVIEW] "identity unconfirmed — visual/family check required"  (no stranger auto-suggested)
```

### Where Claude runs (production)
- **haiku** — insert-time description→struct + name transliteration; **batched pair
  scoring** (~25 candidates/call) with rationales; multilingual voice intake.
- **opus** — escalation for ambiguous deferred pairs; nightly cross-center dedup audit;
  one-time geo-gazetteer alignment.
- Every call gets **k-anonymized, name-redacted** input. Offline, deterministic fallbacks
  run and Claude scores back-fill on reconnect — **the operator is never blocked.**

---

## Honest evaluation (`eval_match.py`)

We don't grade the matcher on its own homework. Noise comes from an **independent** table
of real-world spelling variants (Roy/Rai/Rae, Lakshmi/Laxmi…), and we add a **negative
control**: remove the true record and check the engine doesn't confidently match a stranger.

```
COHORT A — family re-reports at another center (noisy transliterated name)
  recall@1 100.0%   recall@5 100.0%   MRR 1.000
COHORT B — volunteer finds a confused elder (NO name, NO mobile, NO origin — the hard case)
  recall@1  69.2%   recall@5  95.0%   MRR 0.798
NEGATIVE control (true record REMOVED — correct answer is "no match")
  false-AUTO-SUGGEST rate  0.0%  (0/400 strangers wrongly auto-suggested)
```

**Recall finds the person; the human confirms; the governor refuses to be confidently
wrong.** That 0% false-confident rate is the difference between a safe system and one that
hands an elder to the wrong family.

---

## Geographic intelligence (`geo_intel.py` + `kml_ingest.py`)

Driven by the organizers' richer **KML layers**: real chokepoint **risk levels**, the
**4,079-point** planned camera network, and the **official 2027 Amrit Snan calendar**
(Aug 2 · Aug 31 · Sep 11–12) — plus live report density.

- **Risk-weighted hotspots** — `risk_weight × (1 + live reports) × snan_multiplier`, with
  an uncovered-point boost. The ranking **re-prioritizes on snan days** for the surge.
- **Kiosk placement** at high-risk points with **no camera within 400m** — real blind
  spots: *Trimbak Road exit* and *Adgaon* have 0 cameras nearby, while Ramkund has 300+.
- **Nearest-facility routing** for a found person / anxious family.
- **CCTV zone-assist** — which cameras cover a last-seen location, for an *authorized,
  logged, human* footage request. **No automated face-rec on public CCTV, ever.**

```
$ python3 geo_intel.py
TOP HOTSPOTS (risk-weighted): Nashik Road–Dwarka corridor [very high], Ramkund [very high] …
2027-09-11 (3rd Amrit Snan ×5.0): scores surge ~5×, 6 very-high-risk hotspots to pre-staff
ROUTING: found@Ramkund → Bhadrakali PS (1.0 km), 319 cameras within 500m for footage review
```

---

## Crowd-modulated reachability — "how far could they have gone?" (`reachability.py`)

If person X was last seen at Ramkund at 12:00 and only reported at 14:00, where do we look?
This is search-and-rescue **probability-of-area** theory with the Kumbh twist that **crowd
density inverts the radius**: `effective_speed = elder_walking_speed × crowd_factor(density)`,
where density comes from the place's real risk level × the snan-calendar multiplier × time of day.

```
Ramkund, last seen 12:00, reported 14:00:
  3rd Amrit Snan (CRUSH)  density 0.88 → speed ×0.05 → reachable 0.29 km  (search-tight 130m, 258 cams)
  Ordinary day            density 0.44 → speed ×0.60 → reachable 1.87 km  (6× larger area)
```

Same 2-hour gap, **6× difference in search area** — because in a crush a confused elder
physically *cannot* move. The probability surface is biased toward **dwell magnets** (water,
ghats, transit) since confused elders drift there, not toward a uniform ring. It outputs the
**cameras and zones to review first** and the points to send volunteers.

It also feeds the matcher (`reach_plausibility()`): the *same* found person 1.5 km away is
**plausible on a normal day (0.61) but implausible in a crush (0.10)** — so a wrong-location
match is down-weighted before it ever reaches an operator.

> Last-seen names are ~20 free-text places, so `reachability.py` ships a seed **gazetteer**
> with approximate GPS + uncertainty radii — to be replaced by the two-person GPS walk the
> blueprint specifies.

## Privacy & safety — enforced in code, not slides

- **Confirm-only search**: `search_projection()` returns `{case_id, band, score, age_band,
  zone}` — **no names, no mobiles**. A kiosk can never browse "all confused 80+ women from
  Bihar" (a trafficker's target list). Full PII is a separate, role-gated, **audit-logged**
  `get_full_record()` call — and **minors are invisible to non-police roles.**
- **Anti-wrongful-claim**: identity is proven by interrogating the **searching family**
  about withheld details, not the confused subject. Notifications fire **outbound** with no
  location in the message, so a spoofed number learns nothing.
- **Crypto-shredding**: per-case keys let an append-only log coexist with right-to-erasure;
  all PII destroyed at mela close.

---

## Run it

```bash
python3 setu_match.py     # cross-center matching + safety governor + privacy projection
python3 eval_match.py     # honest two-cohort eval + negative control
python3 kml_ingest.py     # parse the 3 KML layers (risk levels, 4,079 cameras, snan calendar)
python3 geo_intel.py      # risk-weighted, snan-aware hotspots, kiosk placement, routing
python3 reachability.py   # crowd-modulated "how far could they have gone" search area
```
Pure Python 3 stdlib — **no pip, no network** — because it has to run on a dusty offline
edge box. The Claude hooks (`claude_name_sim`, `claude_desc_sim`) are explicit slots;
the deterministic fallback runs when offline.

## Build plan
- **Weekend MVP**: two simulated edge nodes proving the offline cross-center match, the
  band governor, the confirm-only projection, and a live haiku scoring + voice-intake demo.
- **Roadmap**: pilot 2 centers → mesh + safety kernel → all 10 + reunification orchestrator
  → geo/surge ops → face pipeline (production-only). Full phases in the blueprint.

> North star: **median time-to-confirmed-reunion for the hard cohort** (no-name/no-mobile
> elderly), with a hard guardrail of **zero confirmed false reunifications.** We optimize
> the 29-hour tail, not the already-fast median — and never trade a wrong handoff for speed.
