"""Sjednocení názvů týmů. Stejná pravidla jsou v web/live.js (testy drží obě strany u sebe)."""
import json, pathlib, re, unicodedata

ROOT = pathlib.Path(__file__).resolve().parents[1]
RULES = json.loads((ROOT / "web" / "names_rules.json").read_text(encoding="utf-8"))
STOP = set(RULES["stop"])
CITY = RULES["city"]
ALIASES = RULES["aliases"]
NAT_ALIASES = RULES["nat_aliases"]
COUNTRIES = RULES["countries"]

def strip_accents(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower().replace("'", "").replace("’", "")

def _tokens(value, drop_stop):
    text = strip_accents(value)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    out = []
    for token in text.split():
        if token.isdigit():
            continue
        if re.fullmatch(r"(18|19|20)\d\d", token):
            continue
        if drop_stop and token in STOP:
            continue
        out.append(CITY.get(token, token))
    return out

def canon(name):
    key = " ".join(_tokens(name, True))
    return ALIASES.get(key, key)

def nat_key(name):
    key = " ".join(_tokens(name, False))
    return NAT_ALIASES.get(key, key)

def code_of(value):
    if value is None:
        return None
    text = strip_accents(value)
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    if not text:
        return None
    if text in COUNTRIES:
        return COUNTRIES[text]
    compact = text.replace(" ", "")
    if compact in COUNTRIES:
        return COUNTRIES[compact]
    return None

def club_id(name, country):
    code = code_of(country) or "xx"
    key = canon(name)
    if not key:
        key = "unknown"
    return f"club:{code}:{key}"

def nat_id(name):
    key = nat_key(name) or "unknown"
    return f"nat:{key}"

def resolve_club(teams, name, country=None):
    """Najde id. Země z ligy má přednost; jinak jednoznačný klíč, jinak tým s nejvíc zápasy."""
    key = canon(name)
    if not key:
        return "club:xx:unknown"
    code = code_of(country) if country else None
    if code:
        return f"club:{code}:{key}"
    hits = [tid for tid in teams if tid.startswith("club:") and tid.endswith(":" + key)]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        hits.sort(key=lambda tid: teams[tid].get("n", 0), reverse=True)
        return hits[0]
    return f"club:xx:{key}"
