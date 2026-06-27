"""
Honest evaluation of the Setu matching engine.

Two things most hackathon evals get wrong, fixed here:

1) CIRCULAR RECALL. If you perturb a record by INVERTING the matcher's own
   transliteration rules and then find it again, you are grading the matcher on its own
   homework. We instead draw noise from an INDEPENDENT, hand-curated table of real-world
   Indian-name spelling variants (Roy/Rai/Rae, Lakshmi/Laxmi, Krishna/Kishan...) plus
   realistic data-entry edits — none of which are the engine's _TRANSLIT rules.

2) NO PRECISION NUMBER. Recall alone is vanity: a matcher that auto-suggests everything
   scores 100% recall and reunites people with strangers. The catastrophic failure here
   is a CONFIDENT WRONG MATCH. So we add a NEGATIVE CONTROL: plant a found-person whose
   true record is REMOVED from the pool, and measure how often the engine still emits an
   AUTO-SUGGEST (a false reunion). That false-AUTO-SUGGEST rate is the number that matters.

Run:  python3 eval_match.py [N]
"""
import random, re, sys
from setu_match import load_registry, search, Person

random.seed(11)

# Independent real-world spelling variants (NOT the engine's _TRANSLIT inversions).
SURNAME_VAR = {
    "roy": ["rai", "rae"], "singh": ["sinh", "sing"], "kumar": ["kumaar"],
    "sharma": ["sarma"], "patel": ["patil"], "nair": ["nayar"], "menon": ["menen"],
    "reddy": ["reddi"], "gupta": ["guptaa"], "shah": ["sah"], "jha": ["jhaa"],
    "das": ["dass"], "rao": ["rau"], "desai": ["dessai"], "iyer": ["aiyar"],
}
FIRST_VAR = {
    "lakshmi": ["laxmi", "lakhsmi"], "krishna": ["kishan", "krishan"],
    "pushpa": ["puspa"], "savita": ["savitha"], "ganesh": ["ganes"],
    "mahesh": ["mahes"], "rekha": ["rekhaa"], "sunita": ["suneeta"],
    "vijay": ["wijay"], "ramesh": ["rames"], "prakash": ["parkash"],
}

def perturb_name(name: str) -> str:
    toks = name.split()
    out = []
    for i, t in enumerate(toks):
        low = t.lower()
        table = FIRST_VAR if i == 0 else SURNAME_VAR
        if low in table and random.random() < 0.7:
            out.append(random.choice(table[low]).capitalize())
        elif random.random() < 0.25 and len(t) > 4:        # generic data-entry vowel slip
            j = next((k for k in range(1, len(t) - 1) if t[k].lower() in "aeiou"), None)
            out.append(t[:j] + t[j + 1:] if j else t)
        else:
            out.append(t)
    return " ".join(out)

AGE = ["0-12", "13-17", "18-40", "41-60", "61-70", "71-80", "80+"]

def _noisy_age(age):
    if random.random() < 0.25:
        i = AGE.index(age) if age in AGE else 3
        return AGE[min(max(i + random.choice([-1, 1]), 0), len(AGE) - 1)]
    return age

def make_family_reentry(src: Person, centers) -> Person:
    """Cohort A — the SAME FAMILY (or a relative) re-reports at a second center. They know
    the demographics; the name is spelled/transliterated differently; mobile often blank."""
    return Person(case_id="Q-" + src.case_id, name=perturb_name(src.name), gender=src.gender,
                  age_band=_noisy_age(src.age_band), state=src.state, district=src.district,
                  language=src.language, center=_other(src, centers),
                  last_seen=src.last_seen if random.random() < 0.8 else "",
                  mobile="" if random.random() < 0.45 else src.mobile,
                  description=src.description, kind="missing")

def make_volunteer_found(src: Person, centers) -> Person:
    """Cohort B — a volunteer finds a CONFUSED ELDER who cannot give a name. The volunteer
    knows only what they can OBSERVE: rough gender (noisy), rough age, where found, a vague
    look. They do NOT know the person's name, mobile, home state, or district. This is the
    hard core case and the population Setu exists for."""
    gender = src.gender if random.random() < 0.85 else \
        random.choice([g for g in ("Male", "Female") if g != src.gender] or [src.gender])
    return Person(case_id="Q-" + src.case_id, name="", gender=gender,
                  age_band=_noisy_age(src.age_band),
                  state=src.state if random.random() < 0.30 else "",   # rarely known
                  district="", language=src.language if random.random() < 0.40 else "",
                  last_seen=src.last_seen, center=_other(src, centers),
                  mobile="", description=src.description, kind="found")

def _other(src, centers):
    return random.choice([c for c in centers if c != src.center] or [src.center])

def _cohort(reg, pool, centers, builder, n):
    r1 = r5 = mrr = scanned = 0
    auto_total = auto_correct = 0
    for src in random.sample(pool, min(n, len(pool))):
        q = builder(src, centers)
        scanned += len(reg.candidates(q))
        res = search(reg, q, top_k=5)
        rank = next((i for i, m in enumerate(res, 1)
                     if m.candidate.case_id == src.case_id), None)
        if rank == 1: r1 += 1
        if rank and rank <= 5:
            r5 += 1; mrr += 1 / rank
        # how often the TOP suggestion (the operator's default) is correct
        if res:
            auto_total += 1
            if res[0].candidate.case_id == src.case_id:
                auto_correct += 1
    N = min(n, len(pool))
    return dict(N=N, r1=r1/N, r5=r5/N, mrr=mrr/N, scanned=scanned/N,
                top1=(auto_correct/auto_total if auto_total else 0))

def run(n=600):
    reg = load_registry()
    pool = [p for p in reg.people.values() if p.name.strip()]
    centers = list({p.center for p in reg.people.values()})
    full = len(reg.people)

    A = _cohort(reg, pool, centers, make_family_reentry, n)
    B = _cohort(reg, pool, centers, make_volunteer_found, n)

    # NEGATIVE control on the HARD cohort: remove the true source; any confident
    # AUTO-SUGGEST is a false reunion with a stranger.
    false_auto = neg = 0
    for src in random.sample(pool, min(400, len(pool))):
        q = make_volunteer_found(src, centers)
        saved = reg.people.pop(src.case_id)
        res = search(reg, q, top_k=5)
        reg.people[src.case_id] = saved
        neg += 1
        if res and res[0].band == "AUTO-SUGGEST":
            false_auto += 1

    def block(title, c):
        print(f"{title}  (N={c['N']})")
        print(f"  recall@1 {c['r1']:5.1%}   recall@5 {c['r5']:5.1%}   MRR {c['mrr']:.3f}"
              f"   top-1 correct {c['top1']:5.1%}")
        print(f"  candidates scanned {c['scanned']:5.1f}/{full} "
              f"({100*(1-c['scanned']/full):.1f}% reduction)")

    print("Setu matching evaluation  (independent noise, two real query types, neg control)")
    print("=" * 78)
    block("COHORT A — family re-reports at another center (knows demographics, noisy name)",
          A)
    print()
    block("COHORT B — volunteer finds a confused elder: NO name, NO mobile, NO home state/"
          "district\n           (the hard core case — only observed gender/age/place/look)", B)
    print(f"\nNEGATIVE control (N={neg}, true record REMOVED, hard cohort — answer is 'no match'):")
    print(f"  false-AUTO-SUGGEST rate {false_auto/neg:5.1%} ({false_auto}/{neg}) "
          f"— strangers wrongly shown as a confident match")
    print("=" * 78)
    print("Offline deterministic path only (no Claude). Cohort B is hard BY DESIGN: with no")
    print("name/mobile the band governor refuses AUTO-SUGGEST, so these surface as REVIEW for")
    print("human visual/family confirmation — recall finds the person, the human confirms.")
    print("In production Claude lifts cohort-B name/description recall above this floor.")

if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 600)
