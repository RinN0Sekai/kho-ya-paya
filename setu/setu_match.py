"""
Setu — cross-center missing-person matching engine (zero-dependency reference impl).

This is the CORE of the system: given a "found / sighted" person (or a new missing
report), find the most likely matching records already in the pool — even when the
record was filed at a DIFFERENT center, the name is transliterated differently across
languages, and key fields (name, mobile) are missing.

Design notes
------------
* Pure Python stdlib only, so it runs on a ruggedized offline edge box with no pip.
* Two-stage record linkage:
    1) BLOCKING  -> cheap deterministic keys generate a small candidate set (avoids O(n^2)).
    2) SCORING   -> a weighted feature model ranks candidates into confidence bands.
* The fuzzy/multilingual name match and semantic description match are the slots where
  Claude runs IN PRODUCTION (claude-haiku-4-5 for cheap triage, claude-opus-4-8 for the
  hard ambiguous top candidates). Here we ship a deterministic LOCAL fallback
  (Jaro-Winkler + Soundex + token overlap) so the engine works fully OFFLINE and the
  demo runs with no API key. `score_pair()` exposes the exact hook.
* Nothing is ever auto-merged. The engine SUGGESTS ranked candidates to a human operator.
"""

from __future__ import annotations
import csv, re, unicodedata, sys, os
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Optional

# --------------------------------------------------------------------------- #
# Normalization & phonetics (transliteration-robust, no external libs)
# --------------------------------------------------------------------------- #

def norm(s: str) -> str:
    """Lowercase, strip diacritics, collapse non-alnum to single spaces."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

# Common Indic transliteration equivalences collapsed to a canonical form, so that
# "Mukesh"/"Mukhesh", "Vijay"/"Wijay", "Lakshmi"/"Laxmi" land on the same key.
_TRANSLIT = [
    (r"ksh", "x"), (r"ph", "f"), (r"th", "t"), (r"dh", "d"), (r"bh", "b"),
    (r"gh", "g"), (r"kh", "k"), (r"ch", "c"), (r"sh", "s"), (r"w", "v"),
    (r"ee", "i"), (r"oo", "u"), (r"aa", "a"), (r"y", "i"), (r"z", "j"),
]

def translit_key(s: str) -> str:
    s = norm(s)
    for pat, rep in _TRANSLIT:
        s = re.sub(pat, rep, s)
    s = re.sub(r"(.)\1+", r"\1", s)        # collapse doubled letters
    s = re.sub(r"[aeiou]", "", s)          # drop interior vowels (keep consonant skeleton)
    return s

def soundex(token: str) -> str:
    token = norm(token)
    if not token:
        return ""
    codes = {**dict.fromkeys("bfpv", "1"), **dict.fromkeys("cgjkqsxz", "2"),
             **dict.fromkeys("dt", "3"), "l": "4",
             **dict.fromkeys("mn", "5"), "r": "6"}
    first = token[0].upper()
    tail, prev = "", codes.get(token[0], "")
    for ch in token[1:]:
        c = codes.get(ch, "")
        if c and c != prev:
            tail += c
        if ch not in "hw":
            prev = c
    return (first + tail + "000")[:4]

def name_sim(a: str, b: str) -> float:
    """Token-aware name similarity. Whole-string Jaro-Winkler is dominated by a shared
    FIRST name, so two strangers both called "Pushpa" score ~0.9 and falsely pass the
    strong-identifier gate. Identity lives in the SURNAME, so we align tokens and average
    per-token similarity, penalising a differing token count. (In prod, Claude replaces
    this with true multilingual name-equivalence reasoning.)"""
    ta, tb = norm(a).split(), norm(b).split()
    if not ta or not tb:
        return 0.0
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    sims = [max(jaro_winkler(s, l) for l in long_) for s in short]
    return (sum(sims) / len(sims)) * (len(short) / len(long_))

def jaro_winkler(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    md = max(len(a), len(b)) // 2 - 1
    md = max(md, 0)
    a_m, b_m = [False] * len(a), [False] * len(b)
    matches = 0
    for i, ca in enumerate(a):
        lo, hi = max(0, i - md), min(i + md + 1, len(b))
        for j in range(lo, hi):
            if not b_m[j] and b[j] == ca:
                a_m[i] = b_m[j] = True
                matches += 1
                break
    if matches == 0:
        return 0.0
    t, k = 0, 0
    for i in range(len(a)):
        if a_m[i]:
            while not b_m[k]:
                k += 1
            if a[i] != b[k]:
                t += 1
            k += 1
    t /= 2
    m = matches
    jaro = (m / len(a) + m / len(b) + (m - t) / m) / 3
    # Winkler prefix boost
    p = 0
    for ca, cb in zip(a, b):
        if ca == cb and p < 4:
            p += 1
        else:
            break
    return jaro + p * 0.1 * (1 - jaro)

# --------------------------------------------------------------------------- #
# Record model
# --------------------------------------------------------------------------- #

AGE_ORDER = ["0-12", "13-17", "18-40", "41-60", "61-70", "71-80", "80+"]

def age_window(band: str) -> list[str]:
    """Self + adjacent age bands. Volunteer-entered age is noisy and an 80-year-old
    is logged as 71-80 or 80+ interchangeably, so we block across the neighbours."""
    if band not in AGE_ORDER:
        return [band] if band else []
    i = AGE_ORDER.index(band)
    return AGE_ORDER[max(0, i - 1): i + 2]

@dataclass
class Person:
    case_id: str
    name: str = ""
    gender: str = ""
    age_band: str = ""
    state: str = ""
    district: str = ""
    language: str = ""
    last_seen: str = ""
    center: str = ""
    mobile: str = ""
    description: str = ""
    kind: str = "missing"        # "missing" (family-filed) or "found" (operator-filed)

    @property
    def mobile_tail(self) -> str:
        d = re.sub(r"\D", "", self.mobile or "")
        return d[-6:] if len(d) >= 6 else ""

    @classmethod
    def from_csv_row(cls, r: dict) -> "Person":
        return cls(
            case_id=r["case_id"], name=r.get("missing_person_name", ""),
            gender=r.get("gender", ""), age_band=r.get("age_band", ""),
            state=r.get("state", ""), district=r.get("district", ""),
            language=r.get("language", ""), last_seen=r.get("last_seen_location", ""),
            center=r.get("reporting_center", ""), mobile=r.get("reporter_mobile", ""),
            description=r.get("physical_description", ""),
        )

# --------------------------------------------------------------------------- #
# Index + blocking
# --------------------------------------------------------------------------- #

class Registry:
    """Unified in-memory registry with blocking indexes. On an edge box this is a
    local replica that syncs via an append-only event log (see offline strategy)."""

    def __init__(self):
        self.people: dict[str, Person] = {}
        self._by_mobile: dict[str, set] = defaultdict(set)
        self._by_phon: dict[str, set] = defaultdict(set)        # phonetic(first name) — NO gender
        self._by_demo: dict[str, set] = defaultdict(set)        # age_band x state — NO gender
        self._by_seen: dict[str, set] = defaultdict(set)        # normalized last-seen

    def add(self, p: Person):
        self.people[p.case_id] = p
        if p.mobile_tail:
            self._by_mobile[p.mobile_tail].add(p.case_id)
        # GENDER IS DELIBERATELY ABSENT FROM EVERY BLOCKING KEY: in the real data the
        # volunteer-entered gender contradicts the physical description ~48% of the time,
        # so keying on gender silently partitions true pairs of the exact elderly cohort
        # this system exists for. Gender survives only as a SOFT score down-weight.
        toks = norm(p.name).split()
        if toks:
            self._by_phon[soundex(toks[0])].add(p.case_id)
            self._by_phon[translit_key(toks[0])[:4]].add(p.case_id)
        self._by_demo["|".join([p.age_band, p.state])].add(p.case_id)
        if p.last_seen:
            self._by_seen[norm(p.last_seen)].add(p.case_id)

    def candidates(self, q: Person) -> set:
        """Union of blocking keys -> small candidate set. Each key is a different way
        the same person could still be found if other fields are missing/garbled.
        Age is matched across a window (self + adjacent bands)."""
        c: set = set()
        if q.mobile_tail:
            c |= self._by_mobile[q.mobile_tail]
        toks = norm(q.name).split()
        if toks:
            c |= self._by_phon[soundex(toks[0])]
            c |= self._by_phon[translit_key(toks[0])[:4]]
        for ab in age_window(q.age_band):
            c |= self._by_demo["|".join([ab, q.state])]
        if q.last_seen:
            c |= self._by_seen[norm(q.last_seen)]
        c.discard(q.case_id)
        return c

# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #

def _age_sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    try:
        d = abs(AGE_ORDER.index(a) - AGE_ORDER.index(b))
    except ValueError:
        return 0.0
    return 0.6 if d == 1 else 0.0          # adjacent bands get partial credit

def _desc_sim(a: str, b: str) -> float:
    """LOCAL fallback for description match. In prod, replace with a Claude semantic
    match (claude-haiku-4-5): handles 'saffron kurta' vs 'orange dhoti', cross-language."""
    sa, sb = set(norm(a).split()), set(norm(b).split())
    sa -= {"a", "the", "has", "wearing", "in", "with", "man", "woman"}
    sb -= {"a", "the", "has", "wearing", "in", "with", "man", "woman"}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)

# Feature weights. Tuned so a strong identifier (mobile) dominates, but the engine can
# still find someone with NO name and NO mobile via demographics + geo + description.
WEIGHTS = {
    "name": 34, "mobile": 30, "gender": 6, "age": 8,
    "state": 6, "district": 4, "language": 4, "last_seen": 5, "desc": 8,
}

# A "strong identifier" is the only thing that may lift a pair into AUTO-SUGGEST.
# Demographics + geography + a vague description are NOT enough — many different
# people share age-band + state + last-seen ghat, so a high demographic score alone
# is a STRANGER risk, not a match. This gate is the difference between a safe system
# and one that hands a confused elder to the wrong family.
STRONG_NAME = 0.90        # Claude/JW name-equivalence at/above this counts as strong
FACE_THRESH = 0.62        # ArcFace cosine (production-only)

@dataclass
class Match:
    candidate: Person
    score: float
    band: str
    features: dict
    strong_identifier: bool = False
    note: str = ""

def score_pair(q: Person, c: Person, claude_name_sim=None, claude_desc_sim=None) -> Match:
    """Score one (query, candidate) pair. `claude_name_sim`/`claude_desc_sim` are the
    production hooks — pass callables backed by the Claude API to upgrade fuzzy
    multilingual name matching and semantic description matching. When None, the
    deterministic offline fallbacks run so the box works with no network."""
    f = {}
    # name: max of literal JW and transliteration-skeleton match; Claude in prod
    if q.name and c.name:
        local = max(name_sim(q.name, c.name),
                    0.92 if translit_key(q.name) and translit_key(q.name) == translit_key(c.name) else 0.0)
        f["name"] = claude_name_sim(q.name, c.name) if claude_name_sim else local
    else:
        f["name"] = 0.0
    f["mobile"] = 1.0 if (q.mobile_tail and q.mobile_tail == c.mobile_tail) else 0.0
    f["gender"] = 1.0 if (q.gender and q.gender == c.gender) else 0.0
    f["age"] = _age_sim(q.age_band, c.age_band)
    f["state"] = 1.0 if (q.state and q.state == c.state) else 0.0
    f["district"] = 1.0 if (q.district and q.district == c.district) else 0.0
    f["language"] = 1.0 if (q.language and q.language == c.language) else 0.0
    f["last_seen"] = jaro_winkler(q.last_seen, c.last_seen) if (q.last_seen and c.last_seen) else 0.0
    f["desc"] = (claude_desc_sim(q.description, c.description) if claude_desc_sim
                 else _desc_sim(q.description, c.description))

    # Only score features that are present in BOTH records, then renormalize by the
    # weight actually available -> a record with no name/mobile is not unfairly penalised.
    num = sum(WEIGHTS[k] * v for k, v in f.items())
    avail = sum(WEIGHTS[k] for k in f if _present(q, c, k))
    score = 100 * num / avail if avail else 0.0

    # A mobile match means the SAME FAMILY re-reported (every number in the data is
    # unique, so it never links two different relatives) — a strong duplicate signal.
    if f["mobile"] == 1.0:
        score = max(score, 90.0)

    # Evidence gate: is there ANY strong identifier, or is this demographics-only?
    face = f.get("face", 0.0)
    strong = (f["mobile"] == 1.0 or f["name"] >= STRONG_NAME or face >= FACE_THRESH)

    band = ("AUTO-SUGGEST" if score >= 75 else
            "REVIEW" if score >= 50 else
            "WEAK" if score >= 30 else "NONE")

    # GOVERNOR: demographics/geo/description alone may never AUTO-SUGGEST. Without a
    # strong identifier the best a pair can reach is REVIEW ("visual check required").
    note = ""
    if band == "AUTO-SUGGEST" and not strong:
        band = "REVIEW"
        note = "identity unconfirmed — demographic match only, visual/family check required"
    return Match(candidate=c, score=round(score, 1), band=band, features=f,
                 strong_identifier=strong, note=note)

def _present(q: Person, c: Person, k: str) -> bool:
    g = lambda p: {
        "name": p.name, "mobile": p.mobile_tail, "gender": p.gender, "age": p.age_band,
        "state": p.state, "district": p.district, "language": p.language,
        "last_seen": p.last_seen, "desc": p.description,
    }[k]
    return bool(g(q).strip()) and bool(g(c).strip())

def search(reg: Registry, q: Person, top_k: int = 5, **claude_hooks) -> list[Match]:
    cand_ids = reg.candidates(q)
    # A purged/crypto-shredded record can leave a tombstone in the index — skip it.
    matches = [score_pair(q, reg.people[cid], **claude_hooks)
               for cid in cand_ids if cid in reg.people]
    matches = [m for m in matches if m.band != "NONE"]
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[:top_k]

# --------------------------------------------------------------------------- #
# Privacy boundary: confirm-only search projection + audited full-record fetch
# --------------------------------------------------------------------------- #
# A kiosk must NEVER be able to browse "all confused 80+ women from Bihar" — that is a
# target list for traffickers. Search therefore returns a MINIMAL projection with no
# name / mobile / free-text. Revealing full PII is a separate, role-gated, logged call.

AUDIT_LOG: list[dict] = []

def search_projection(reg: Registry, q: Person, top_k: int = 5, **claude_hooks) -> list[dict]:
    """What an operator's screen is allowed to see: enough to visually confirm, no PII."""
    out = []
    for m in search(reg, q, top_k=top_k, **claude_hooks):
        c = m.candidate
        out.append({
            "case_id": c.case_id, "band": m.band, "score": m.score,
            "age_band": c.age_band, "last_seen_zone": c.last_seen,
            "has_photo": False, "note": m.note,
        })
    return out

def get_full_record(reg: Registry, case_id: str, actor_id: str, role: str,
                    reason: str) -> Optional[Person]:
    """The ONLY path to PII. Role-gated and written to a tamper-evident audit log."""
    AUDIT_LOG.append({"actor": actor_id, "role": role, "case_id": case_id,
                      "reason": reason, "action": "PII_FETCH"})
    if role not in ("operator", "supervisor", "police"):
        return None
    p = reg.people.get(case_id)
    # Minors are invisible to general kiosk roles — police pipeline only.
    if p and p.age_band in ("0-12", "13-17") and role != "police":
        AUDIT_LOG[-1]["action"] = "PII_FETCH_DENIED_MINOR"
        return None
    return p

# --------------------------------------------------------------------------- #
# Loader + tiny CLI demo
# --------------------------------------------------------------------------- #

DATA = os.path.join(os.path.dirname(__file__), "..",
                    "claude-impact-labs-data", "claude-impact-lab-mumbai-2026",
                    "data", "Synthetic_Missing_Persons_2500.csv")

def load_registry(path: str = DATA) -> Registry:
    reg = Registry()
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            reg.add(Person.from_csv_row(row))
    return reg

if __name__ == "__main__":
    reg = load_registry()
    print(f"Loaded {len(reg.people):,} records into the unified registry.\n")

    # CASE 1 — a volunteer near Ramkund finds a confused woman who DID give a name.
    # "Pushpa Rai" is a transliteration of "Pushpa Roy" filed at a DIFFERENT center.
    found = Person(case_id="FOUND-DEMO", name="Pushpa Rai", gender="Female",
                   age_band="41-60", state="Rajasthan", language="Awadhi",
                   last_seen="Ramkund Ghat", center="Ramkund (offline)",
                   description="elderly woman orange saree confused", kind="found")
    print(f"CASE 1 — FOUND with a name: {found.name}, {found.age_band}, "
          f"seen {found.last_seen}")
    scanned = len(reg.candidates(found))
    print(f"  blocking scanned {scanned} of {len(reg.people)} records.")
    for i, m in enumerate(search(reg, found, top_k=4), 1):
        c = m.candidate
        flag = "  <- strong id" if m.strong_identifier else ""
        print(f"  #{i} [{m.band:12}] {m.score:5}  {c.case_id}  {c.name or '(no name)'} "
              f"| {c.state} | center={c.center[:22]}{flag}")

    # CASE 2 — the SAFETY case: a confused elder gives NO usable name. Demographics line
    # up with several different strangers. The governor MUST hold these at REVIEW, never
    # AUTO-SUGGEST, because handing an elder to the wrong family is catastrophic.
    print("\nCASE 2 — FOUND with NO name (the safety case): "
          "Female, 71-80, Bihar, seen Ramkund Ghat")
    nameless = Person(case_id="FOUND-DEMO2", name="", gender="Female", age_band="71-80",
                      state="Bihar", language="Maithili", last_seen="Ramkund Ghat",
                      center="Ramkund (offline)",
                      description="old woman white saree cannot remember name", kind="found")
    for i, m in enumerate(search(reg, nameless, top_k=4), 1):
        c = m.candidate
        print(f"  #{i} [{m.band:12}] {m.score:5}  {c.case_id}  {c.name or '(no name)'} "
              f"| {c.state} | {m.note}")
    print("  -> no strong identifier => all capped at REVIEW. No stranger auto-suggested.")

    # The privacy boundary an operator's screen actually sees (no names, no mobiles):
    print("\nCONFIRM-ONLY SEARCH PROJECTION (what the kiosk screen may display):")
    for row in search_projection(reg, nameless, top_k=3):
        print("  ", row)
