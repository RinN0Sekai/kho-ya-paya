"""
Kho-Ya-Paya — optional Claude brain (stdlib urllib, no SDK).

This is the multilingual layer: cross-script name equivalence (Lokkhi == Lakshmi) and
voice-intake structuring. It calls claude-haiku-4-5 over the Anthropic API IF
ANTHROPIC_API_KEY is set; otherwise it returns a deterministic offline fallback so the
node never blocks and the demo runs with no network. Claude is strictly advisory —
it ranks/structures/translates but never authorizes a reunion.
"""
import os, json, urllib.request, urllib.error, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "setu"))
from setu_match import name_sim, translit_key   # deterministic fallback

API = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5"
KEY = os.environ.get("ANTHROPIC_API_KEY", "")

def available():
    return bool(KEY)

def _call(system, user, max_tokens=400):
    if not KEY:
        return None
    body = json.dumps({"model": MODEL, "max_tokens": max_tokens,
                       "system": system, "messages": [{"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read())
        return "".join(b.get("text", "") for b in data.get("content", []))
    except Exception:
        return None

def _json_from(text):
    if not text:
        return None
    try:
        i, j = text.index("{"), text.rindex("}") + 1
        return json.loads(text[i:j])
    except Exception:
        return None

# --------------------------------------------------------------------------- #
def name_equivalence(a, b):
    """Are two names the same person across scripts/transliterations? -> dict."""
    if not (a and b):
        return {"equiv": 0.0, "rationale": "a name is missing", "source": "offline"}
    out = _json_from(_call(
        "You judge whether two Indian names refer to the same person across languages, "
        "scripts and transliteration variants (e.g. Lakshmi/Laxmi/Lokkhi are the same; "
        "Pushpa Roy vs Pushpa Nair are different — surnames matter). "
        'Reply ONLY JSON: {"equiv":0.0-1.0,"rationale":"short"}.',
        f'Name A: "{a}"\nName B: "{b}"'))
    if out and "equiv" in out:
        return {"equiv": float(out["equiv"]), "rationale": out.get("rationale", ""),
                "source": "claude"}
    # offline fallback: deterministic transliteration + token similarity
    eq = max(name_sim(a, b), 0.92 if translit_key(a) and translit_key(a) == translit_key(b) else 0.0)
    return {"equiv": round(eq, 2),
            "rationale": "deterministic transliteration/phonetic match (Claude offline)",
            "source": "offline"}

def voice_extract(text, language="Hindi"):
    """Turn noisy spoken intake into structured fields. Never invents a name."""
    out = _json_from(_call(
        "You clean noisy ASR of a lost/found person described by a volunteer at the Kumbh "
        "Mela and extract structured fields. NEVER invent a name — if not clearly stated, "
        'leave it empty. Reply ONLY JSON with keys: name, gender (Male/Female/Unknown), '
        'age_band (one of 0-12,13-17,18-40,41-60,61-70,71-80,80+), description, '
        'spelling_variants (array of romanizations of the name if any).',
        f"Language: {language}\nSpoken: \"{text}\""))
    if out:
        out["source"] = "claude"
        return out
    return {"name": "", "gender": "", "age_band": "", "description": text,
            "spelling_variants": [], "source": "offline"}

if __name__ == "__main__":
    print("Claude available:", available())
    for a, b in [("Lakshmi", "Lokkhi"), ("Lakshmi Jha", "Laxmi Jha"),
                 ("Pushpa Roy", "Pushpa Nair")]:
        print(f"  {a:14} vs {b:14} -> {name_equivalence(a, b)}")
