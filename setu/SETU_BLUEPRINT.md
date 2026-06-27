# Setu — Production System Blueprint

> An offline-first, human-operated reunification network that makes a person found at any Kho-Ya-Paya center instantly searchable at every other center — built for phoneless, non-literate, multilingual elderly pilgrims, with Claude as the multilingual matching brain and a human (and police for minors) as the only authority that ever confirms a reunion.


## North star

Median time-to-confirmed-reunion for the hard cohort (no-name OR no-mobile elderly, the population this exists for), with a hard guardrail of zero confirmed false reunifications. We optimize the long tail (current max ~29h, mean 4.0h) for this cohort, not the already-fast median — and we will not trade a single wrong handoff for speed.


## Architecture overview

Setu is one append-only, event-sourced registry replicated to a rugged edge box at each of the 10 (designed for 30+) Kho-Ya-Paya centers, plus capture-only roving volunteer tablets. Every report — whether a family-filed MISSING record or an operator-filed FOUND record — is the same polymorphic person-record written locally first, assigned a center-prefixed ULID, and appended to a signed, content-addressed event log. The product is not a database; it is the closing of one specific gap: a FOUND person at Center A must surface to a family searching at Center B even when cellular has collapsed on an Amrit Snan day. That gap closes because every node holds a replica and matches locally, and because nodes converge over whatever transport is alive — center LAN, 5GHz point-to-point backhaul between line-of-sight centers, store-and-forward over dual-SIM modems, sealed-USB sneakernet on a courier loop, and LoRa only for tiny tokenized beacons.

Matching is a two-stage funnel that is deliberately humble about what the data contains. A deterministic blocking stage escapes O(n^2) using keys that survive missing fields (age-band-window x state, phonetic/transliterated name, geo-node, time-window) — critically with gender REMOVED from the blocking key, because 16-30% of records carry a gender that contradicts the description and gender-in-the-key silently partitions true pairs. Surviving candidates (hard-capped, with multi-call fan-out for oversized blocks) are scored by a fusion model whose name/description/transliteration features are computed by Claude (haiku on the hot path, opus for ambiguous escalation), with deterministic offline fallbacks so the box never blocks. Scores map to evidence-gated confidence bands: nothing reaches the top band on demographics alone — GREEN requires at least one strong identifier (exact mobile of a same-family re-report, face cosine over threshold, or Claude name-equivalence >=0.9). The engine only ever SUGGESTS; a human operator confirms every link, and any reunion involving a minor or a non-lucid person requires police co-sign (with an offline co-sign path so safety never blocks on the network).

Privacy is enforced as a code boundary, not a policy footnote: search returns a confirm-only projection (case_id, score, band, age_band, last-seen-zone, thumbnail) — never a browsable directory of separated women and children; full PII is a separate role-gated, audit-logged fetch; PII is replicated as keys-plus-case-ids while full records are pulled on-demand from origin during active review; per-case encryption keys enable crypto-shredding so the append-only log and the right-to-erasure coexist; and minor records live in a police-only queue invisible to general kiosk search. Claude only ever sees k-anonymized, name-redacted structured text and is strictly advisory — it can rank and explain but can never authorize a handoff.


## Components

- **Edge Node** — Source of truth for local intake plus a hot full replica of the global case index; runs intake UI, deterministic blocker, on-device phonetic/embedding fallbacks, local Claude-response cache, and the operator queue. Fully functional with zero network.

  - *Tech:* Intel N100/N305 mini-PC (Pi 5 fallback), 16GB/512GB NVMe, IP65 enclosure, LiFePO4 UPS + solar trickle, dual-SIM modem, 5GHz directional radio, LoRa module; SQLite (WAL) materialized from the event log

- **Roving Capture Tablet** — Volunteer-carried capture-and-relay device for FOUND-person and field intake; holds NO searchable PII registry and no local PII cache — write-through to nearest node, fast auto-lock, remote-wipe, named check-in/out.

  - *Tech:* Rugged Android tablet, noise-cancelling handset mic, camera, BLE printer for pre-encoded wristbands; offline PWA, sealed-to-node encryption

- **Sync Fabric** — Converges the append-only signed event log across nodes over any live transport; replicates blocking-keys + case-ids broadly and full PII on-demand; carries only tokenized beacons over LoRa.

  - *Tech:* Anti-entropy gossip with Merkle/event-frontier digests, blake3 content-addressing, ed25519 per-node signatures, Lamport clocks; libsodium sealed-box deltas; store-and-forward + courier sneakernet

- **Matching Engine** — Two-stage entity resolution: deterministic blocking (gender removed from key, geo-snapped, time-windowed, hard-capped) then evidence-gated hybrid scoring; suggests ranked candidates with per-feature rationale to the operator queue.

  - *Tech:* Python/FastAPI daemon; Jaro-Winkler+Double-Metaphone+token-overlap offline fallback; logistic fusion learned from confirm/reject labels; pgvector/FAISS for optional face cosine

- **Claude Orchestrator** — Cost-tiered multilingual brain: insert-time description structuring + name transliteration, batched candidate pair scoring, ambiguous escalation, kiosk voice intake; strictly advisory, k-anonymized redacted input only.

  - *Tech:* claude-haiku-4-5 (hot path, batched, prompt-cached), claude-opus-4-8 (escalation + nightly dedup audit); hard $ budget guard with auto-downshift

- **Geo Intelligence Layer** — Uncertainty-aware gazetteer snapping free-text last-seen to nodes, crowd-aware separation-risk heatmap, capacitated kiosk/wristband placement, nearest-help routing, and operator-in-the-loop CCTV camera-list assist (never auto face-rec).

  - *Tech:* Local equirectangular projection, NumPy grid-KDE, cKDTree, Shapely PIP on buffered zones, greedy max-coverage/p-median; restricted to authenticated operators

- **Reunification Orchestrator** — Turns a confirmed match into a physical reunion: claim/lock so two centers don't both act, identity-verify the claimant, route both parties to a nearest common handoff point, notify the phoneless family, confirm identity at handoff.

  - *Tech:* State machine over the event log; PA + cross-center operator notification; police-station / transfer-node handoff routing

- **Privacy & Safety Kernel** — Confirm-only search projection, role-gated PII fetch, per-case crypto-shredding, minor-only restricted queue with dual sign-off, query auditing + rate-limiting against insider fishing, k-anonymity gate before any Claude egress.

  - *Tech:* SQLCipher/AES-256 with per-record keys wrapped by per-zone keys wrapped by per-event master; per-device hash-chained audit log; outbound k-anonymity coarsening

- **Control-Room Dashboard** — Supervisor view of open cases, queue depth, reunion rate, time-to-reunion trend, node health/last-sync, restricted hotspot map, and long-tail aging/child-safety escalation alerts.

  - *Tech:* Cloud (ap-south-1) FastAPI + cached snapshot pushed to edge; non-critical-path, degrades to each node's cached dashboard


## Core matching spec

SCHEMA (one append-only table, record_type discriminator). global_case_id (center-prefixed ULID, legacy KMP-2027-NNNNN as alt_id); record_type MISSING|FOUND|SIGHTING; subject fields name_raw (nullable 14.8%), name_script, name_translit_latin (derived), name_phonetic (derived Double-Metaphone over Latin), gender, age_band (7 bands), state, district, language; event fields last_seen_node / found_node (snapped to a node, with uncertainty geometry), captured_at_lat/lng + captured_at_time (NEW — the kiosk/volunteer's own trusted GPS on every FOUND record, the cleanest coordinate in the system), event_time; companion/group field traveling_with (NEW — families are found through their group, e.g. "lost husband", "woman with three children", akhada flag); current_custody_location (NEW — a found elder gets moved; 73 already "transferred to hospital", so an old FOUND record is a LEAD not a location); provenance reporting_center, operator_id, reporter_mobile (nullable 19.7%, FAMILY's number), entry_channel; lifecycle status, linked_case_ids[], match_group_id, confidence_band, resolution_hours; derived desc_struct (Claude-extracted garment/color/build/marks/accompanied_by/mobility), face_embedding[512] (nullable, session-only by default); sensitivity class is_minor/is_at_risk/is_gender_unknown; consent_audio_ref; per-case encryption metadata.

BLOCKING KEYS (deterministic, ms, gender REMOVED from the key). K1 mobile_suffix4 — last 4 digits (spec/impl drift fixed: code currently uses last-6; standardize on suffix4 to absorb leading-digit typos). CRITICAL CORRECTION from verified data: reporter_mobile is the FAMILY member's number and all ~2,008 present numbers are 100% distinct with zero collisions, so mobile dedups REPORTERS not PERSONS — K1 only fires for the same family re-reporting at a second center, NOT for the dominant duplicate path (two different relatives). K2 name_phonetic (Double-Metaphone on Latin transliteration; null 14.8%). K3 age_band-window (self + adjacent bands) x state — replaces the old age x gender x state so a gender-contradicted record is still retrieved. K4 geo_node with neighbor-node expansion (snap free-text last-seen to the ~20 real nodes via uncertainty-aware gazetteer, NOT exact string equality — "Ram kund" and "Ramkund Ghat" must collide). K5 time-window (Open cases within rolling 36h, 48h on snan). NEW secondary keys to sub-divide the hard no-ID block (verified to hit 108-163 candidates today): reported_at hour-bucket x geo, desc template-class (garment+mobility+accompanied_by), state-of-origin, and traveling_with token. Candidate set = (K1..K4 NEW-secondary) ∩ K5, HARD-CAPPED at ~25 with multi-call fan-out for oversized generic-description blocks; target verified median candidate set <=25 for the no-name+no-mobile subset specifically.

FEATURE SET. Deterministic (free, on-box): f_mobile (1.0 exact suffix4, treated as same-family re-report signal only), f_age (1.0 same / 0.6 adjacent), f_gender (SOFT down-weight on contradiction, NEVER a veto — named "gender↔description noise channel", measured 16-30% conflict), f_state/f_district/f_language, f_phonetic (metaphone match or Jaro-Winkler on Latin), f_geo (node match / neighbor decay, plus captured_at vs last_seen directional displacement feature), f_time (recency decay). Claude features (claude-haiku-4-5, batched ~25 pairs/call, JSON-in/JSON-out): f_name_llm (multilingual fuzzy-name + transliteration equivalence across 10 languages), f_desc_llm (semantic same-person plausibility of two vague descriptions; desc_struct pre-extracted at insert so most comparisons are cheap structured overlaps), f_consistency (contradiction flag as SOFT down-weight). Optional f_face (ArcFace cosine, production-only, highest single weight when present, privacy-gated, never auto-confirms). The FIRST-CLASS match type is FOUND<->MISSING (a present person meets a searching family); missing<->missing dedup (the 8.1%) is the same machinery at lower queue priority.

SCORING & EVIDENCE-GATED BANDS. Weighted log-odds fusion, weights learned from operator confirm/reject labels. The renormalize-by-available-weight trick is RETAINED but CONSTRAINED, because verified testing showed it lets a record with only age+gender+state+last-seen hit "AUTO-SUGGEST 91.5" on a stranger (Saroj Patel / Pushpa Roy-vs-Nair-vs-Sinha). FIX: GREEN requires >=1 strong identifier (exact mobile same-family, face cosine >= threshold, OR Claude name-equivalence >=0.9). Demographics+geo-only matches are HARD-CAPPED at AMBER ("identity unconfirmed — visual check required") and never AUTO-SUGGEST. GREEN = top of queue; AMBER = show with differing fields highlighted; RED = hidden, manual deep-search only.

CLAUDE'S ROLE. Three precise points, never the decider: (1) insert-time desc_struct extraction + name transliteration (cached); (2) batched pair scoring returning 0-1 sub-scores with one-line rationales surfaced verbatim to the operator; (3) opus escalation for deferred AMBER pairs + nightly cross-center dedup audit. Offline, deterministic fallbacks run and Claude features are marked pending and back-filled on reconnect — the operator is never blocked.

HUMAN-IN-THE-LOOP CONFIRM FLOW. (1) Engine pushes GREEN/AMBER to the operator queue at the FOUND center, mirrored to the MISSING center. (2) Side-by-side card: missing vs found, per-feature contributions, Claude rationale, thumbnail if allowed. (3) Identity-proof FLIPPED to interrogate the SEARCHING FAMILY about the found person (a mark, clothing, who they came with, photo confirmation), NOT the confused 80+ subject who often cannot answer ("Old man confused, keeps asking for Ramkund" — 114 such records). Capacity fallback for non-lucid subjects: skip person-side consent, lean on face two-way match + a second independent family identifier. (4) CONFIRM -> claim/lock the match (so two centers don't both act), create confirmed-link edge, replicate so the pair never resurfaces. REJECT -> negative label, suppress pair. DEFER -> stays AMBER, escalate to opus. (5) Minors / non-lucid / gender-unknown require police co-sign (offline hardware token path on snan days) and dual sign-off; high-stakes confirms for tired rotating volunteers default to the SAFE action (don't merge, escalate) requiring zero skill. (6) Confirms/rejects retrain fusion weights, tune thresholds, become Claude few-shot exemplars. Identities are NEVER auto-merged by CRDT/LWW — source records stay immutable, only operator-confirmed match_group links merge, and any minor merge is reversible with dual sign-off.

CONFIDENCE BANDS: GREEN (strong identifier present, >=0.85) = very likely same person; AMBER (0.55-0.85 OR demographics-only ceiling) = operator judgment with differences highlighted; RED (<0.55) = hidden. The headline metric is PRECISION-at-GREEN / false-link rate from a hand-built adversarial look-alike set (same age_band x state x last-seen, different surname/mobile) — NOT the circular self-recall the shipped eval_match.py produces by planting a perturbed copy and finding it back.


## End-to-end data flow

DAY 0 — Family reports grandmother missing at Center A (Adgaon), online. A son walks up to the Adgaon kiosk. He has no smartphone for his mother but has his own basic phone. The volunteer picks Maithili as the conversation language; a pre-recorded human prompt asks the family to "tell us everything." The son speaks; on-device ASR transcribes the noisy code-mixed Maithili, and because raw ASR cannot be trusted for the identity field, Claude-haiku cleans it, extracts structured fields, proposes name spellings ("Lakshmi"/"Laxmi"/"Lokkhi"), and the operator reads the parsed fields back for the son to confirm by ear. The record is written: record_type=MISSING, name_raw="Lakshmi Jha" (with name_phonetic + name_translit_latin derived ON-BOX so it is matchable instantly even if Claude were offline), age_band=71-80, gender=Female, state=Bihar, language=Maithili, last_seen snapped by the gazetteer to "Ramkund Ghat", traveling_with="came with son and grandson", reporter_mobile = the SON's number (a same-family re-report signal only, not a person key), desc_struct={white saree, widow marks, walks with stick, hard of hearing}. A center-prefixed ULID is minted; the event is signed and appended to the log. The blocking keys + case_id propagate immediately over the center LAN and 5GHz backhaul; full PII stays at origin, pulled on-demand only during active review. Adgaon runs an instant cross-search against the live FOUND pool — no match yet. The son leaves with a tear-off slip (case number + which kiosk + icons), is added to the PA list and the aging-alert watch, and his phone is registered for outbound notification.

LATER — Volunteer finds a confused elderly woman near a ghat, logged at Center B (Ramkund), OFFLINE on a snan day. Cellular has collapsed. A roving volunteer near Ramkund finds a disoriented woman in a white saree who keeps asking for "Ramkund" and cannot reliably state her name. On the capture tablet (capture-and-relay, no local PII browse): PHOTO FIRST (face embedding computed in-memory for this match session, not persisted), captured_at_lat/lng stamped from the tablet GPS (the most trustworthy coordinate available), tap gender + age-band + last-seen pin, and 10s of mumbled audio Claude extracts what it can. record_type=FOUND, current_custody_location set to the medical/holding tent she is walked to. The tablet writes through to the nearest Ramkund edge node. Because cellular is down, the node matches LOCALLY against its full last-synced replica — which already includes Adgaon's MISSING record, because the blocking keys gossiped over the 5GHz backhaul / courier loop before the blackout, or arrive within the courier interval.

MATCH — Local engine surfaces the link offline. Ramkund's blocker generates candidates WITHOUT gender in the key (so the volunteer-observed "Female" landing differently from any mis-tag does not partition the pair): K3 age-window(71-80,80+) x Bihar, K4 geo Ramkund + neighbors, K5 within window, plus desc-template (white saree + stick + widow marks) and traveling_with. The hard no-ID block is sub-divided to ~20 candidates, not 150. Deterministic scoring runs immediately; Claude features are marked pending (offline). f_name is weak (found person gave no usable name) so the demographics+geo+desc match is HARD-CAPPED AT AMBER — "identity unconfirmed, visual check required" — exactly as designed to prevent a confident stranger match. Lakshmi Jha's MISSING record appears at the top of the Ramkund operator's AMBER queue with the white-saree/stick/widow-marks overlap and the thumbnail.

REUNION — Human confirms, claimant verified, physical handoff. The Ramkund operator claims/locks the match so Adgaon cannot double-act. Because the subject is non-lucid and elderly (not a minor), the protocol leans on the SEARCHING family: a cross-center notification fires to Adgaon's operator and an outbound call/PA goes to the son's registered phone — "a candidate match for your mother may be at Ramkund; come to confirm," with NO location/identity broadcast to the raw phone number (the location resolves only operator-side, killing the trafficking-lure vector). The son arrives (or is routed via the reunification orchestrator to the nearest common handoff point — a police station or transfer node, since Adgaon and Ramkund can be kilometers apart through crowd crush). He answers withheld questions about HER (the stick, who she came with, a mark) and confirms her face. Two independent identifiers plus operator confirmation flip status to Reunited; resolution_hours recorded; the confirmed-link edge replicates so the pair never resurfaces at a third center. The in-memory face embedding is discarded on resolution; her PII enters the crypto-shred TTL. When connectivity returns, Claude back-fills the name/description sub-scores and the confirm/reject becomes a training label. Had she been a MINOR, the same flow would have routed to a police-only queue with mandatory officer co-sign (offline hardware token) and dual sign-off before any release.


## Offline-first strategy

Edge-primary, cloud-secondary — cloud is NEVER on the life-safety path. Every node holds a full local replica (the entire mela is low hundreds of thousands of ~1KB rows; a daily delta is <15MB), so local intake and full cross-center search work with zero network. The source of truth is an append-only, content-addressed, ed25519-signed event log; merge is commutative set-union with Lamport-clock ordering only for inherently-ordered field assertions — never LWW destruction of a report and never auto-merge of identities (the 8.1% duplicate is a reversible operator-confirmed link, not an overwrite).

TRANSPORT LADDER, realistically re-budgeted: (1) center LAN/fiber where it exists; (2) 5GHz point-to-point backhaul between LINE-OF-SIGHT centers only — explicitly NOT a 10-center LOS mesh, because verified geography shows police stations span ~17.8km and Trimbakeshwar sits in the Brahmagiri hills with no LOS to Nashik Road; (3) store-and-forward over dual-SIM modems in opportunistic LTE windows; (4) sealed-USB sneakernet courier on a 30-60min loop as the guaranteed-eventual, partition-proof fallback (a <15MB delta fits any USB/phone on the shuttle); (5) LoRa DEMOTED to tokenized presence/frontier beacons only, re-budgeted against the India 865-867MHz ~1% duty-cycle cap and sub-500m non-LOS range in crowd — it carries a case-id hash "sync available, fetch over trusted channel," never PII and never an actionable "match at Gate X."

BLOCKING-KEY DERIVATION IS FULLY ON-BOX so a case is matchable the instant it is created even at total isolation: phonetic/transliteration keys are computed locally; Claude romanization is a REFINEMENT event that re-blocks on arrival, never a prerequisite. Claude pair-scoring features degrade to deterministic Jaro-Winkler+metaphone+token-overlap fallbacks and are marked pending, then back-filled on reconnect.

DEGRADATION ORDER (shed in exact sequence as queue depth / API budget crosses thresholds), with face REMOVED from this order until the photo flow ships: shed opus adjudication (haiku-only ranking with operator confirm) -> shed cross-language enrichment (within-language matching) -> throttle large-block re-ranking/re-indexing. NEVER shed: local case capture, local+mesh cross-center search, FOUND beacons. An offline ANNOUNCEMENT path drives a zone-local PA / runner dispatch from the zone box so a confirmed match triggers a reunion at L1/L2 without the cloud. Police co-sign has an OFFLINE mode: an on-site liaison at each center holds a hardware co-sign token valid on the local mesh, plus a "provisional supervised safe-hold" so a minor is HELD safely (never handed off, never indefinitely blocked) until an officer is physically present.

Power/hardware reality: LiFePO4 UPS sized for a realistic 12-18h snan blackout (not 8h), solar de-rated under dust/tarp, fanless thermal-derating accepted at 40C, hardware watchdog auto-restart, nightly self-image, hot-spare with cold re-gossip in minutes; and a PRINTED fallback at every kiosk (paper nearest-kiosk/police map + pre-coded case slips with QR/short-code) so a dead tablet never loses a found person — slips sync when power/network return.


## Privacy & safety

Privacy is enforced in CODE, not prose — the most important correction to the shipped artifact, whose search() currently prints full names of multiple different separated women on one query (the exact "directory of separated women" harvest the design claims to prevent).

CONFIRM-ONLY SEARCH. search() returns a DTO {case_id, score, band, age_band, last_seen_zone, thumbnail_ref} with NO name/mobile/description. Full PII is a separate getFullRecord(case_id, actor_id, role, reason) call that enforces role checks and writes a per-device hash-chained audit entry — the only path to PII. Kiosks answer "does any record match THIS present person/this specific described relative," never free-browse "list all confused 80+ women from Bihar." Every query is logged, rate-limited, reason-required, and anchored to a present claimant or present found-person; demographic-filter fishing toward minors raises real-time alerts.

DATA MINIMIZATION & RE-IDENTIFICATION. Collect only reunion-necessary fields; never collect address, Aadhaar/ID, caste/religion, fingerprint/iris, GPS trails, or the at-risk person's own phone. The geo layer is NOT claimed PII-free — a case_id+coordinate+timestamp trace IS personal data; persisted locations are coarsened to node granularity, time-bucketed, and purged on resolution. Before any Claude egress, the outbound tuple is k-anonymized: name redacted to [NAME], language coarsened to a family, last-seen to a zone not a node, state to a region — because "Maithili speaker from a Bihar district at a named transit node" is uniquely identifying at 80M scale even with the name stripped. Claude is strictly advisory and cannot authorize a handoff.

ENCRYPTION & ERASURE THAT COEXISTS WITH AN APPEND-ONLY LOG. Per-record data keys wrapped by per-zone keys wrapped by a per-event master (key hierarchy, so one stolen tablet or zone is revocable, not the whole event). "Purge resolved case" = destroy the per-case key everywhere, leaving an un-decryptable tombstone in the immutable log (crypto-shredding) — this is what makes append-only and right-to-erasure compatible. Two-key, TTL-backstopped purge: PII purges on (operator marks Reunited) AND (supervisor/claimant-audio second confirmation), with a hard max-PII-TTL (~72h) regardless of status so nothing lingers; escalated/hospital/unresolved go on the documented 30-day police-register track; ALL operational PII crypto-shredded at mela close + 7 days. Claimant photos and consent audio are encrypted under the same per-case key. Replicate only blocking-keys+case-ids broadly; pull full PII on-demand from origin during active review to minimize blast radius. Roving tablets are capture-and-relay only with no PII cache, fast auto-lock, named check-in/out, and remote-wipe.

ANTI-TRAFFICKING / WRONGFUL-CLAIM. False reunification is the catastrophic failure and the band design is hardened to prevent the verified 40%-strangers-in-GREEN problem (GREEN requires a strong identifier). Identity-proof interrogates the SEARCHING FAMILY about withheld details, never the confused subject; for thin 6-word descriptions, two-way reciprocal recognition + a second independent family identifier is the primary verifier, with police co-sign for any thin/at-risk record. MINORS (288 in data, 11.5%) get a SEPARATE pipeline: a police-only restricted queue invisible to general kiosk search; any FOUND-minor record immediately and irrevocably pages police and triggers a staffed safe-hold regardless of who filed it; the person who FILES a found-minor cannot be in the chain that CLAIMS it; duplicate found-minor records across centers auto-freeze all copies pending police reconciliation; release requires officer co-sign + dual sign-off + recorded claimant ID + a relationship challenge. Risk flags are derived from the UNION of signals (age_band OR child-words-in-description OR "cannot remember name" OR no-name OR gender-Unknown OR field-contradiction), because volunteer-entered age/gender are demonstrably wrong in the data and a mis-bucketed trafficked teen must not silently lose the police gate. Wristbands carry only an opaque random token printed with nothing but a case number — an unauthenticated scan reveals NOTHING (no name, no family phone); resolution to contact happens server-side, operator-authenticated, logged, and notifications fire outbound so a scanner never sees the family's number. Footage pulls require two-person authorization, are single-case/single-window/time-boxed, claimant-verified, and audited; no automated face-rec on public CCTV, ever — enforced as a code boundary. Audit logs are per-device hash chains (each node signs its own chain) co-anchored at central so offline concurrent appends stay tamper-evident. The live risk heatmap is restricted to authenticated operators (it is, by construction, a map of where lone vulnerable people cluster) and never exposes individual case dots to volunteers. Physical layer: privacy-film screens, single-candidate reveal (never a top-5 face grid), idle auto-dim, queue-facing-away layout.


## Geographic intelligence

The load-bearing fact: last_seen values are free-text NAMES (only ~20 distinct, only 1 matching a chokepoint name), not coordinates. Everything is anchored by an UNCERTAINTY-AWARE gazetteer: each of the 20 names gets a geometry (a 150m disc for "Ramkund Ghat", a 2km corridor for "Trimbak Road" which is an 18km road, not a point), a confidence score, and a version hash. Coordinates are validated against the 10 centers' and 14 police stations' REAL surveyed GPS as anchor truth (they are physical, surveyable assets) — and a two-person physical GPS walk of the top-10 high-frequency points before go-live. Claude (opus, once, offline) does first-pass fuzzy alignment across the 10 languages; a human signs off; the table is frozen and versioned, and every placement decision logs which gazetteer version produced it. Live kiosk free-text last-seen is snapped by Claude-haiku (offline-queued), defaulting to nearest-by-edit-distance, never dropped — and paired with a LANGUAGE-FREE, LITERACY-FREE tap-a-landmark/photo picker so location can be entered with zero shared language. Critically, every FOUND record stamps captured_at_lat/lng from the device GPS — the single most reliable coordinate in the system — powering reverse-location for non-verbal found persons and a directional displacement feature for matching.

Local equirectangular projection (cos-lat scaling, <0.3% error over the 18km box, ~50x faster than haversine) keeps everything real-time on an offline CPU. SEPARATION-RISK HEATMAP: grid-KDE fusing a static chokepoint prior (transfer nodes weighted highest — Madsangvi Transit is the #1 last-seen at 149), a live 3h-window report-density term (tau=90min), and a SnanMult from the published royal-bath calendar (4.5x on bath dates) — because the synthetic daily counts are deliberately flat (40-78/day) and the 4-5x surge is NOT learnable from the file; it must be a static input. Uncertainty radius propagates into the KDE sigma. Auto-reweights to static+snan when the live feed is stale (offline).

CROWD-AWARE placement and routing (the key correction): at peak ghat density a person physically cannot cross 600m, so coverage uses snan-day REACHABLE-distance (~100-150m near ghats, density of kiosks as the lever rather than radius) and placement biases toward the DOWNSTREAM/deposit side of unidirectional flow, reporting coverage at BOTH normal and snan reachable-radius so the 95% number is not a peak-day illusion. Routing inflates graph edge weights through crush zones to route AROUND, not through. Capacitated facility-location (greedy max-coverage, explainable) places kiosks seeded with the 10 existing centers as already-open; wristband issuance is PUSH-based (volunteers roving ghat steps, langars, akhada camps, medical tents where the elderly actually dwell) NOT a gate funnel, because 80M pilgrims do not pass 8-12 countable gates. Surge staffing models TWO queues per kiosk — intake AND active-custody — because the 29h tail is dominated by the custody/verification phase, sizing custody staff on concurrent-held-persons (a stock = arrivals x mean-hold-time), with min 2 operators + 1 child-safety-trained per high-risk site on snan days.

CCTV zone-assist is honestly reframed as a LONG-TAIL INVESTIGATION aid for the unresolved ~3% / 12-29h cases (contingent on a negotiated fast police footage-pull SLA), NOT a real-time find tool — it outputs only camera IDs + zone for a logged, authorized, two-person, single-case/single-window human request, never pulls or analyzes footage, and NEVER runs auto face-rec (a hard code invariant). Movement priors search OUTWARD and toward DWELL points (water, shade, langars, the person's own akhada flag) rather than betting on rational egress, since confused elders sit, backtrack, or follow familiar sounds.


## Tech stack

- Python 3 + FastAPI matching daemon (stdlib-only offline fallback path so it runs on a bare edge box with no pip)

- SQLite (WAL) on edge as a rebuildable materialized projection of the canonical append-only event log; PostgreSQL 16 / RDS Multi-AZ as durable cloud merge target

- Append-only event-sourced log: blake3 content-addressing, ed25519 per-node signatures, Lamport clocks, anti-entropy gossip with Merkle/event-frontier digests

- libsodium sealed-box encrypted sync deltas + SQLCipher/AES-256 per-record keys (key hierarchy: per-record < per-zone < per-event master) for revocation and crypto-shredding

- Double-Metaphone + Jaro-Winkler + token-overlap deterministic on-box matching fallback; indic-transliteration / aksharamukha rule-based script->Latin

- claude-haiku-4-5 (batched, prompt-cached hot path) and claude-opus-4-8 (escalation + nightly dedup audit) via API, k-anonymized redacted input only

- Anthropic prompt caching for the static matching-rules + 10-language transliteration guide (no PII) so only variable case text is billed; hard $ budget guard with auto-downshift

- On-device Whisper-class multilingual ASR with operator read-back + Claude spelling-variant selection (never trust raw ASR for identity fields); noise-cancelling handset mic

- InsightFace/ArcFace buffalo_l ONNX (CPU) + pgvector/FAISS for optional face cosine — PRODUCTION-ONLY, session-only embeddings, requires a kiosk-photo capture flow not in the current dataset

- NumPy grid-KDE + SciPy cKDTree + Shapely point-in-polygon on buffered zones; greedy max-coverage / p-median placement; coarse-graph Dijkstra routing (all-pairs <0.2MB cached per node)

- Edge box: Intel N100/N305 (Pi 5 fallback), 16GB/512GB NVMe, IP65 enclosure, LiFePO4 UPS + solar, dual-SIM modem, 5GHz directional radio, LoRa (beacons only)

- Offline-first PWA kiosk app (icon + pre-recorded-voice UI, 10 languages) + capture-and-relay roving tablet with remote-wipe; BLE thermal printer for pre-encoded opaque-token wristbands

- Redis Streams / SQS match-job queue as snan-spike backpressure; cloud FastAPI dashboard (ap-south-1) with cached snapshot pushed to edge; per-device hash-chained audit log co-anchored centrally


## Where Claude is used

- claude-haiku-4-5 — INSERT-time structuring: convert each noisy free-text physical_description into desc_struct JSON (garment/color/build/marks/accompanied_by/mobility) and transliterate ambiguous names to Latin + native + phonetic; one short cached call per new record. Why haiku: bounded, high-volume, cheap.

- claude-haiku-4-5 — BATCHED pair scoring (the core): after deterministic blocking, score up to ~25 candidate pairs per call returning f_name_llm, f_desc_llm, f_consistency as 0-1 sub-scores with one-line rationales surfaced verbatim to the operator. Why haiku: ~1/15th opus cost, bounded comparison task, runs at snan-spike volume; multi-call fan-out for oversized blocks.

- claude-haiku-4-5 — kiosk VOICE intake: clean noisy on-device ASR of dialectal/code-mixed speech, schema-locked structured extraction (unheard fields stay null, never hallucinate a name), propose name spelling variants for operator read-back, and live speech translation for the 10-language operator<->family conversation. Why haiku: real-time, per-intake, cost-sensitive.

- claude-opus-4-8 — ESCALATION: re-adjudicate mid-confidence (~0.4-0.75) AMBER pairs the operator defers — cross-language names, no-mobile, vague-description — returning a calibrated verdict + human-readable rationale shown before any reunion. Why opus: higher reasoning where a wrong link is catastrophic; small volume (~hundreds/day, ~5x on snan).

- claude-opus-4-8 — NIGHTLY cross-center MISSING<->MISSING dedup audit over the 8.1% duplicate cluster and the daily backlog of pending-feature pairs back-filled after offline windows. Why opus: batch, off-peak, accuracy over latency.

- claude-opus-4-8 — ONE-TIME offline gazetteer alignment: fuzzy-match the 20 free-text last-seen names (and 10-language transliteration variants) to the 85 chokepoints / 32 zones to seed the uncertainty-aware gazetteer; human verifies and freezes. Why opus: one-off, high-stakes anchoring of the whole geo layer.

- claude-haiku-4-5 — intake CONSISTENCY check on redacted structured fields, flagging records where age/gender/description disagree (verified 16-30% of the data) for re-capture and forcing the at-risk gate. Why haiku: cheap per-record guardrail.

- ALL Claude calls receive only k-anonymized, name-redacted structured text (language->family, node->zone, state->region) and are STRICTLY ADVISORY — Claude can rank, structure, translate, and explain but can NEVER authorize a handoff; the operator (and police for minors/non-lucid) is always the final authority. Offline, deterministic fallbacks run and Claude features back-fill on reconnect.


## Scale & cost

Volume reality: ~2,500 base cases/day across 10 centers (~55/center), spiking 4-5x to ~10-12k on Amrit Snan; the whole 30-45 day mela is low hundreds of thousands of ~1KB rows — index size is never the bottleneck, blocking quality is. Every node holds the full replica; a daily sync delta is <15MB, trivial even on degraded links; cold full resync <30s over Wi-Fi.

Claude cost, corrected for the verified data (mobile does NOT skim off easy duplicates because all reporter numbers are distinct, so Claude is on the critical path MORE than the optimistic model assumed): Stage-1 haiku candidate-ranking ~2,500 batched calls/day (~2-4k tokens in / ~0.5k out), prompt-caching the large static matching+transliteration prefix so only variable case text bills -> order ~$10-20/day normal. Stage-2 opus escalation ~hundreds/day -> ~$20-35/day. Voice intake haiku ~$5-10/day. Total ~$35-65/day normal, capped by a hard $ budget guard at ~$150-200/day on a 5x snan day with auto-downshift opus->haiku->deterministic-only when the ceiling or queue depth crosses thresholds. Cost levers: prompt caching of the shared static prefix, batching ~25 candidates/call, caching identical description-template comparisons (only ~25 distinct strings), and pre-extracting desc_struct at insert so most comparisons are cheap structured overlaps.

Hardware capex: ~$800-1,000 per edge box, 10 centers + 2 spares ≈ $10-12K total field capex — deliberately cheap and repairable. Cloud is a small non-critical-path control plane (a single r6g.large + replica for the global index handles the volume with room to spare; API layer autoscales 2-4 -> ~12 on snan via queue-depth backpressure). The binding constraint at scale is HUMAN throughput, not data propagation or index size: a non-literate elderly intake takes 5-10 minutes, so the snan-day plan budgets operators x seconds/decision across two queues (intake + custody), pre-positions a mobile reserve to predicted hotspots, and uses a batched triage UI sorting candidates by the single most-differentiating field plus a fast "broadcast to all centers" path for unambiguous strong-identifier hits that skips full review.


## Hackathon MVP (this weekend)

Build and demo THIS weekend against the 2,500-row CSV, on a laptop, fully offline-capable, with two corrections that win the system-design and responsible-data criteria over teams that ship the naive version:

1) Two simulated edge nodes (two SQLite files / two browser-tab PWAs) + a tiny cloud Postgres merge, proving a FOUND person logged at Center A surfaces at Center B with a Claude-explained match — the core gap, closed live.

2) Fix the matcher's two demonstrated safety bugs in setu_match.py: (a) REMOVE gender from the blocking keys (lines 173-174, 187-189) and block on age-band-window x state + phonetic name + geo-node instead — recovers the ~16-30% gender-contradicted true pairs that are currently un-retrievable; (b) add the evidence-gated band governor in score_pair(): when neither name nor mobile nor face is present, HARD-CAP the band at REVIEW/AMBER ("identity unconfirmed — visual check required"), never AUTO-SUGGEST — this kills the reproducible "Saroj Patel / Pushpa Roy-vs-Nair-vs-Sinha stranger at 91.5 GREEN" false positive. Also align mobile to suffix-4 (currently last-6) and treat it as a same-family re-report signal, not a person key.

3) Wire the confirm-only privacy projection: search() returns {case_id, score, band, age_band, last_seen_zone, thumbnail} only; a separate getFullRecord(actor, role, reason) is the audit-logged PII path — so judges SEE the projection in code, not just prose (the single biggest gap between the current artifact and the design).

4) Replace the circular eval: keep recall@k from the controlled-perturbation harness BUT generate transliteration noise from an INDEPENDENT source (Claude producing real cross-script spellings) instead of inverting the matcher's own _TRANSLIT rules, AND add a NEGATIVE-CONTROL eval — query found-people genuinely absent from the pool and report the false-AUTO-SUGGEST rate / precision@1. Headline the PRECISION/false-link number, not self-recall.

5) Live Claude in the loop on a handful of real rows: haiku scoring a batch of candidate pairs with rationales, and haiku doing voice-intake extraction on a spoken Maithili/Bhojpuri sample with operator read-back. Demo the offline fallback by killing the API key mid-run and showing the deterministic path still suggests (band-capped) candidates.

The demo narrative is the data_flow_walkthrough: family reports grandmother at A, volunteer finds her offline at B, the band-capped AMBER match surfaces, the operator confirms via family identity-proof, status flips Reunited — with the stranger-false-positive shown being correctly held at AMBER instead of AUTO-SUGGEST.


## Production roadmap

0. Phase 0 (weekend MVP): two-node offline cross-center match on the 2,500-row CSV; gender removed from blocking; evidence-gated band governor; confirm-only search projection + audit-logged PII fetch; independent-noise + negative-control eval reporting precision/false-link; live haiku scoring + voice intake with offline fallback.

1. Phase 1 (pilot, 2 busiest centers Adgaon+Rajur Bahula): rugged edge boxes + 5GHz backhaul between just those two; build the uncertainty-aware gazetteer with real GPS anchor-truth for the 10 centers + 14 stations and a two-person walk of the top-10 nodes; ship the icon+voice PWA and capture-only roving tablet; per-device hash-chained audit log.

2. Phase 2 (mesh + safety kernel): add Central + Police control rooms as backhaul hubs; implement the event log (blake3/ed25519/Lamport), anti-entropy gossip, store-and-forward + sealed-USB courier, LoRa tokenized beacons; per-record crypto-shredding key hierarchy; minor-only police queue with dual sign-off and offline hardware co-sign token; k-anonymity gate before Claude egress.

3. Phase 3 (all 10 centers + reunification orchestrator): claim/lock match state machine, claimant identity verification, nearest-common-handoff routing to police/transfer nodes, offline PA/runner dispatch from the zone box, phoneless outbound notification with no PII to the raw phone number.

4. Phase 4 (geo + surge ops): crowd-aware reachable-distance coverage and routing, separation-risk heatmap from the snan calendar, push-based wristband issuance at dwell points, two-queue (intake+custody) surge staffing with mobile reserve, restricted-access hotspot dashboard.

5. Phase 5 (face pipeline, production-only): kiosk-photo capture flow, on-device ArcFace embeddings (session-only, no minor faces persisted ever, privacy-gated, re-rank only), negotiated fast police CCTV footage-pull SLA for the long-tail unresolved cohort with two-person authorization.

6. Phase 6 (learning loop + hardening): logistic fusion weights and band thresholds retrained from accumulated operator confirm/reject labels; nightly opus dedup audit; LoRa duty-cycle re-budget validated in field; full power/dust/device-loss drills; post-mela crypto-shred + secure-destruction of the entire registry.


## Risks & mitigations

- **Risk:** Confident false reunification of a stranger (verified: 40% of GREEN links were different-surname people; demographics-only hit 91.5 AUTO-SUGGEST) — catastrophic for a vulnerable elder and a trafficking vector.

  - **Mitigation:** Evidence-gated bands: GREEN requires a strong identifier (mobile same-family / face cosine / Claude name-equivalence >=0.9); demographics+geo-only hard-capped at AMBER 'visual check required'. Never auto-merge identities; mandatory operator confirm via family identity-proof; police co-sign + dual sign-off for minors/non-lucid.

- **Risk:** Gender-in-blocking-key silently partitions the 16-30% of records whose volunteer-entered gender contradicts the description — the exact phoneless-elderly cohort the system exists for becomes un-retrievable.

  - **Mitigation:** Remove gender from blocking keys; block on age-band-window x state + phonetic name + geo-node; keep gender as a SOFT scoring down-weight (named 'gender↔description noise channel'), never a veto.

- **Risk:** Mobile assumed to be a person-dedup key, but it is the family member's number and all ~2,008 present numbers are 100% distinct — Stage-0 mobile-match catches ZERO of the cross-center duplicates, blowing the cost model and matching plan.

  - **Mitigation:** Treat mobile as a same-family re-report signal only; make FOUND<->MISSING and phonetic+geo+Claude-semantic the primary path; re-budget Claude as on-critical-path with the corrected higher volume.

- **Risk:** Offline mesh replicates the full PII corpus to every dusty volunteer box / sneakernet USB — one theft leaks the entire vulnerable population; append-only log makes deletion impossible.

  - **Mitigation:** Replicate only blocking-keys+case-ids broadly, pull full PII on-demand from origin during review; sealed-to-destination encrypted deltas (stolen USB is ciphertext); per-record crypto-shredding key hierarchy so 'purge' destroys a key and leaves a tombstone; capture-only roving tablets with remote-wipe.

- **Risk:** SMS/LoRa 'a match exists at Center A' signal is forgeable/replayable — a trafficker manufactures 'your child matched at Gate X' to lure a family/child.

  - **Mitigation:** Downgrade beacons to a pure tokenized 'sync available, fetch over trusted channel' with full authenticated frames + monotonic counter (no replay) and NO location/identity; actionable match detail only over authenticated encrypted transport; wristband scan reveals nothing unauthenticated; notifications fire outbound server-side.

- **Risk:** Headline recall (99.5%) is circular — the eval plants a perturbed copy whose noise inverts the matcher's own rules and finds it back; no precision/false-link number exists, and is_duplicate_report has no linkable twins.

  - **Mitigation:** Generate transliteration noise from an independent source; add a negative-control eval on found-people genuinely absent from the pool; headline PRECISION-at-GREEN / false-link rate from a hand-built adversarial look-alike set.

- **Risk:** Snan-day operator queue, not data sync, is the real bottleneck (5-10 min per non-literate intake; custody/verification dominates the 29h tail); police co-sign blocks reunions exactly when police are stretched and the network is partitioned.

  - **Mitigation:** Two-queue (intake+custody) staffing sized on concurrent-held-persons + mobile reserve; batched triage UI sorted by most-differentiating field; fast broadcast path for strong-identifier hits; offline hardware co-sign token + provisional supervised safe-hold so minors are held safely, never indefinitely blocked.

- **Risk:** Voice intake fails in 100+dB ghat crowds on low-resource dialects (Bhojpuri/Awadhi/Maithili); a mis-transcribed name silently poisons the blocking key.

  - **Mitigation:** Never trust raw ASR for identity fields — operator reads parsed fields back and selects Claude-proposed spelling variants; flow COMPLETES on photo + tapped gender/age/last-seen alone; tap-a-landmark/photo location picker needs zero shared language; store raw audio for later re-processing.

- **Risk:** Minors (288, 11.5%) treated as a flag on a uniform pipeline; volunteer-entered age/gender mis-buckets a trafficked teen out of the police gate; QR band or kiosk search exposes a child to predators.

  - **Mitigation:** Separate police-only minor queue invisible to general search; at-risk flag from UNION of signals (age OR child-words OR no-name OR 'cannot remember' OR contradiction); FOUND-minor auto-pages police + safe-hold regardless of filer; filer-cannot-claim; opaque non-resolving wristband; release needs officer co-sign + relationship challenge + recorded claimant ID.

- **Risk:** Geo layer falsely claimed PII-free while holding a re-identifiable movement trace; gazetteer point-snapping ('Trimbak Road' is an 18km road) biases every downstream decision; 600m walk coverage is fiction at snan crush density.

  - **Mitigation:** Stop the PII-free claim; coarsen stored locations to node granularity, time-bucket, purge on resolution; uncertainty-aware gazetteer geometries (disc/corridor/polygon) with version hash and real-GPS anchor-truth; crowd-aware reachable-distance (~100-150m) coverage biased downstream of unidirectional flow.


## 3-minute demo script

[0:00] "Today at the Kumbh, thousands go missing every day — mostly elderly. There are 10 lost-and-found centers, and they cannot see each other. A grandmother found at Ramkund is invisible to her family searching at Adgaon. That one gap is what Setu closes." Show two laptop windows side by side: Center A and Center B, each an offline edge node.

[0:25] "Center A — the family." A son reports his 75-year-old mother. We speak Maithili into the mic; Claude-haiku cleans the noisy ASR, extracts structured fields, and proposes name spellings — the operator reads them back, the son nods. The record is written, a center-prefixed ULID minted, blocking keys derived ON-BOX. "Notice he gave HIS phone number — not hers. In the real data every reporter number is unique, so a phone can never be our identity key. The mother is phoneless. This is the whole population we serve."

[1:00] "Now pull the network cable." We physically go offline. "Cellular collapses on royal-bath days — this is the default, not the exception." Center B — a volunteer finds a confused woman near the ghat. Photo first, GPS auto-stamped, tap gender/age/last-seen, 10 seconds of mumbled audio. She gives no usable name.

[1:30] "Watch the match — fully offline, against the last-synced replica." Center B surfaces the mother at the TOP of the queue. "Two things most teams get wrong, and we fixed in code: First, we removed gender from the blocking key. In this dataset 16 to 30 percent of records have a gender that contradicts the description — block on gender and you lose exactly these people. Second —" point to the band — "this is AMBER, 'identity unconfirmed, visual check required.' We have NO name, NO phone, NO face match. The naive engine — and we'll show you — returns a STRANGER at 91.5 'very likely same person.'" Flip to the before/after: the Saroj-Patel false positive, now correctly held at AMBER.

[2:10] "Reunion is a HUMAN act." The operator claims the match so Center A can't double-act. Because she's a confused elder, we interrogate the SEARCHING family, not her — withheld questions about the stick she walks with, who she came with. An outbound call fires to the son's phone — with NO location in the message, so a trafficker who spoofs the number learns nothing. He arrives, confirms her face and two details, status flips to Reunited.

[2:35] "And privacy is in the code, not the slides." Run search() live: it returns case_id, score, band, age band, zone, thumbnail — never a browsable list of names of separated women. "Full PII is a separate, role-gated, audit-logged call. Minors live in a police-only queue this kiosk can't even see."

[2:50] "Setu: 800-dollar boxes, runs offline, Claude as the multilingual brain, a human as the only authority — closing the one gap that reunites a phoneless grandmother with her family. Our north star isn't the easy median; it's the 29-hour tail, with zero wrong handoffs."
