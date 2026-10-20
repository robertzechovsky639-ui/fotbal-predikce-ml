"""Soutěž podle id zdroje. Název zápasu region neurčuje."""
import json
import pathlib
import re

import names

ROOT = pathlib.Path(__file__).resolve().parents[1]
RULES = json.loads((ROOT / "web" / "comp_rules.json").read_text(encoding="utf-8"))

_TAG_PRIORITY = ("women", "college", "youth", "reserve")
_YOUTH = re.compile(r"\b(u1[0-9]|u2[0-3]|youth|junior)\b")
_WOMEN = re.compile(r"\b(women|woman|femen|feminin|frauen|ladies|damen|nwsl)\b|\(w\)")
_RESERVE = re.compile(r"\b(ii|iii|iv|reserves|reserve|rezerva|rezervy)\b")
_COLLEGE_SLUG = re.compile(r"(^|[-.])ncaa([-.]\d|$)|college")
_NCAA_LABEL = re.compile(r"\bncaa\b")
_QUAL = {"amateur", "women", "woman", "youth", "reserve", "reserves", "university", "college"}


def _set(name):
    return set(RULES.get(name) or [])


def _ids(name):
    return {int(x) for x in (RULES.get(name) or [])}


def _has(rules_key, value):
    if value is None:
        return False
    try:
        return int(value) in _ids(rules_key)
    except (TypeError, ValueError):
        return False


def _tokens(*parts):
    text = names.strip_accents(" ".join(str(p) for p in parts if p))
    return re.sub(r"[^a-z0-9]+", " ", text)


def tags_of(home, away, slug, tournament_slug, tournament_id, competition_id, label=""):
    tags = []
    blob = _tokens(home, away, slug, tournament_slug)
    if _WOMEN.search(blob) or _has("women_s365", competition_id) or _has("women_sofa", tournament_id):
        tags.append("women")
    if (_has("college_sofa", tournament_id) or (tournament_slug and _COLLEGE_SLUG.search(str(tournament_slug)))
            or (slug and "ncaa" in str(slug)) or _NCAA_LABEL.search(_tokens(label))):
        tags.append("college")
    if _YOUTH.search(blob) or _has("youth_s365", competition_id) or _has("youth_sofa", tournament_id):
        tags.append("youth")
    if _RESERVE.search(blob):
        tags.append("reserve")
    return tags


def _country_from_raw(raw):
    """Země z názvu kategorie. 'England Amateur' je Anglie, ne neznámá soutěž."""
    if not raw or _continent(raw):
        return None
    code = names.code_of(raw)
    if code:
        return code
    tokens = re.sub(r"[^a-z0-9]+", " ", names.strip_accents(raw)).split()
    trimmed = [tok for tok in tokens if tok not in _QUAL]
    if trimmed and len(trimmed) < len(tokens):
        return names.code_of(" ".join(trimmed))
    return None


def segment_of(tags):
    for name in _TAG_PRIORITY:
        if name in tags:
            return name
    return "main"


def country_name(code, raw=None):
    labels = RULES.get("labels") or {}
    if code and code in labels:
        return labels[code]
    if raw and raw.strip() and raw.strip().lower() not in (RULES.get("continent") or {}):
        return raw.strip()
    return None


def _region_from_code(code, tier, cup):
    if not code:
        return "other"
    if code == "cze" and not cup:
        return "czech"
    if code in _set("europe_top") and tier == 1 and not cup:
        return "europe_top"
    if code in _set("europe"):
        return "europe_lower"
    if code in _set("south_america"):
        return "south_america"
    if code in _set("asia"):
        return "asia"
    return "other"


def _espn_tier(slug):
    parts = str(slug or "").split(".")
    if len(parts) == 2 and parts[1].isdigit():
        return int(parts[1])
    return None


def _espn_country(slug):
    prefix = str(slug or "").split(".")[0]
    if prefix in _set("europe") or prefix in _set("south_america") or prefix in _set("asia"):
        return prefix
    if names.code_of(prefix) == prefix:
        return prefix
    return None


def _intl_espn(slug):
    slug = str(slug or "")
    if slug in set(RULES.get("international_espn_exact") or []):
        return True
    return any(slug.startswith(prefix) for prefix in (RULES.get("international_espn") or []))


def _continent(name):
    if not name:
        return None
    return (RULES.get("continent") or {}).get(str(name).strip().lower())


def classify(spec):
    """Vrátí region, zemi, stupeň a štítky. Klíč je id soutěže, ne text názvu."""
    spec = spec or {}
    src = spec.get("src") or ""
    slug = spec.get("slug") or ""
    competition_id = spec.get("competition_id")
    tournament_id = spec.get("tournament_id")
    tournament_slug = spec.get("tournament_slug") or ""
    country_code = spec.get("country_code") or None
    raw_country = spec.get("country_name") or ""
    if not country_code and raw_country:
        country_code = _country_from_raw(raw_country)
    home, away = spec.get("home"), spec.get("away")
    tags = tags_of(home, away, slug, tournament_slug, tournament_id, competition_id, spec.get("label") or "")
    tier = None
    cup = False
    region = None

    if src == "espn" or (slug and not competition_id and not tournament_id):
        tier = _espn_tier(slug)
        if slug in set(RULES.get("cups_espn") or []):
            region, cup, country_code = "europe_cups", True, None
        elif _intl_espn(slug):
            region, country_code = "international", None
        elif slug in (RULES.get("continental_espn") or {}):
            region, cup = RULES["continental_espn"][slug], True
            country_code = None
        else:
            country_code = _espn_country(slug) or country_code
            region = _region_from_code(country_code, tier, False)
    else:
        if _has("cups_s365", competition_id) or _has("cups_sofa", tournament_id):
            region, cup, country_code = "europe_cups", True, None
        elif str(competition_id) in (RULES.get("continental_s365") or {}):
            region, cup, country_code = RULES["continental_s365"][str(competition_id)], True, None
        elif _has("international_s365", competition_id):
            region, country_code = "international", None
        else:
            continent = _continent(raw_country)
            if continent:
                region, country_code = continent, None
                cup = continent != "other" or str(raw_country).strip().lower() in {"africa", "north america"}
                if str(raw_country).strip().lower() in {"europe", "international", "world"}:
                    cup = False
            else:
                region = _region_from_code(country_code, tier, False)

    if region is None:
        region = "other"
    segment = segment_of(tags)
    return {
        "region": region,
        "country": country_code,
        "tier": tier,
        "tags": tags,
        "segment": segment,
        "cup": cup,
        "neutral": region in {"europe_cups", "international"},
        "country_name": country_name(country_code, raw_country if not cup else None),
    }


def classify_stored(match):
    """Přepočte uložený zápas z id soutěže. Text názvu se nečte."""
    league = str((match or {}).get("league") or "")
    teams = (match or {}).get("teams") or []
    home = (match or {}).get("home_name") or (teams[0].get("name") if teams else None)
    away = (match or {}).get("away_name") or (teams[1].get("name") if len(teams) > 1 else None)
    spec = {
        "home": home,
        "away": away,
        "tournament_id": (match or {}).get("ut"),
        "tournament_slug": (match or {}).get("ut_slug"),
        "country_code": (match or {}).get("country"),
        "country_name": (match or {}).get("country_raw"),
        "label": (match or {}).get("league_name"),
    }
    if league.startswith("s365."):
        spec["src"] = "s365"
        tail = league.split(".", 1)[1]
        spec["competition_id"] = int(tail) if tail.isdigit() else None
    elif league.startswith("sofa."):
        spec["src"] = "sofa"
    else:
        spec["src"] = "espn"
        spec["slug"] = league
    if spec.get("country_name"):
        spec["country_code"] = None
    return classify(spec)
