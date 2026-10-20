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

def _club_parts(tid):
    parts = str(tid).split(":", 2)
    if len(parts) != 3 or parts[0] != "club":
        return None, None
    return parts[1], canon(parts[2])


def _matching_ids(teams, key, code):
    hits = []
    for tid in teams:
        country, canon_key = _club_parts(tid)
        if canon_key != key:
            continue
        if code and country != code:
            continue
        hits.append(tid)
    hits.sort(key=lambda tid: ((teams[tid] or {}).get("n") or 0, tid), reverse=True)
    return hits


def resolve_club(teams, name, country=None):
    """Najde id. Stejný canon v jedné zemi se sejde na tým s nejvíc zápasy."""
    key = canon(name)
    if not key:
        return "club:xx:unknown"
    code = code_of(country) if country else None
    hits = _matching_ids(teams, key, code)
    if hits:
        return hits[0]
    if code:
        hits = _matching_ids(teams, key, None)
        if hits:
            return hits[0]
    return f"club:{code or 'xx'}:{key}"


def merge_clubs(state):
    """Spojí záznamy, které po novém canonu znamenají stejný klub. Nechá id s nejvyšším n."""
    teams = state.get("teams") or {}
    groups = {}
    for tid in list(teams):
        code, key = _club_parts(tid)
        if not code:
            continue
        groups.setdefault((code, key), []).append(tid)
    alias = {}
    for ids in groups.values():
        if len(ids) < 2:
            continue
        ids.sort(key=lambda tid: ((teams[tid].get("n") or 0), tid), reverse=True)
        keep, *rest = ids
        dest = teams[keep]
        for other in rest:
            src = teams.pop(other)
            alias[other] = keep
            n1 = dest.get("n") or 0
            n2 = src.get("n") or 0
            total = n1 + n2
            if total:
                dest["elo"] = (float(dest.get("elo") or 1500) * n1 + float(src.get("elo") or 1500) * n2) / total
            dest["n"] = total
            if (src.get("last") or "") > (dest.get("last") or ""):
                dest["last"] = src.get("last")
                dest["name"] = src.get("name") or dest.get("name")
                for field in ("gf", "ga", "xg", "xga", "sot", "sota", "hgf", "agf", "euro"):
                    if src.get(field):
                        dest[field] = src[field]
    if alias and state.get("h2h"):
        folded = {}
        for key, rows in state["h2h"].items():
            sides = [alias.get(part, part) for part in str(key).split("|")]
            new_key = "|".join(sorted(sides))
            bucket = folded.setdefault(new_key, [])
            for row in rows:
                row = list(row)
                if len(row) > 1:
                    row[1] = alias.get(row[1], row[1])
                bucket.append(row)
            if len(bucket) > 8:
                del bucket[:-8]
        state["h2h"] = folded
    state["id_alias"] = alias
    return state
