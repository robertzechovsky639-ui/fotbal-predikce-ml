"""Seznam zápasů, predikce a state.json pro GitHub Pages. Release modelu se odsud nenahrává."""
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import elo
import names
import online
import predict

PRAGUE = ZoneInfo("Europe/Prague")
UA = {"User-Agent": "Mozilla/5.0 (compatible; fotbal-predikce/1.0)"}
MODEL = ROOT / "data" / "model"
DIST = ROOT / "dist"
WEB = ROOT / "web"
STATE_PATH = ROOT / "data" / "online" / "state.json"

SLUG_META = {
    "eng.1": ("eng", "europe_top", "eng:E0", False),
    "eng.2": ("eng", "europe_lower", "eng:E1", False),
    "eng.3": ("eng", "europe_lower", "eng:E2", False),
    "eng.4": ("eng", "europe_lower", "eng:E3", False),
    "eng.5": ("eng", "europe_lower", "eng:EC", False),
    "ger.1": ("ger", "europe_top", "ger:D1", False),
    "ger.2": ("ger", "europe_lower", "ger:D2", False),
    "esp.1": ("esp", "europe_top", "esp:SP1", False),
    "esp.2": ("esp", "europe_lower", "esp:SP2", False),
    "ita.1": ("ita", "europe_top", "ita:I1", False),
    "ita.2": ("ita", "europe_lower", "ita:I2", False),
    "fra.1": ("fra", "europe_top", "fra:F1", False),
    "fra.2": ("fra", "europe_lower", "fra:F2", False),
    "ned.1": ("ned", "europe_top", "ned:N1", False),
    "ned.2": ("ned", "europe_lower", "ned:N2", False),
    "por.1": ("por", "europe_top", "por:P1", False),
    "bel.1": ("bel", "europe_lower", "bel:B1", False),
    "tur.1": ("tur", "europe_lower", "tur:T1", False),
    "gre.1": ("gre", "europe_lower", "gre:G1", False),
    "sco.1": ("sco", "europe_lower", "sco:SC0", False),
    "cze.1": ("cze", "czech", "cze:1", False),
    "uefa.champions": (None, "europe_cups", "uefa:ucl", True),
    "uefa.europa": (None, "europe_cups", "uefa:uel", True),
    "uefa.europa.conf": (None, "europe_cups", "uefa:uecl", True),
    "conmebol.libertadores": (None, "south_america", "conmebol:libertadores", True),
    "conmebol.sudamericana": (None, "south_america", "conmebol:sudamericana", True),
}

FOCUS = {
    "eng.1", "esp.1", "ger.1", "ita.1", "fra.1", "ned.1", "por.1", "cze.1",
    "uefa.champions", "uefa.europa", "uefa.europa.conf",
}
WOMEN = ("(w)", " women", "woman", "femen", "feminin", "frauen", " ladies", "u17", "u18", "u19", "u20", "u21", "u23", "youth", "junior", "damen")
SKIP_STATUS = {"postponed", "cancelled", "canceled", "abandoned"}


def get_json(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def prague_day(ts):
    return dt.datetime.fromtimestamp(ts, PRAGUE).date()


def iso_ts(text):
    raw = str(text).replace("Z", "+00:00")
    return int(dt.datetime.fromisoformat(raw).timestamp())


def minute_of(clock):
    text = str(clock or "")
    found = re.search(r"(\d+)\s*'\s*\+\s*(\d+)", text)
    if found:
        return int(found.group(1)) + int(found.group(2))
    found = re.search(r"(\d+)", text)
    return int(found.group(1)) if found else None


def women(name):
    low = (name or "").lower()
    return any(token in low for token in WOMEN)


def region_of(slug, country):
    meta = SLUG_META.get(slug)
    if meta:
        return meta[1]
    if slug.startswith(("uefa.champions", "uefa.europa")):
        return "europe_cups"
    if slug.startswith("conmebol."):
        return "south_america"
    if country == "cze":
        return "czech"
    if country in elo.JAN_COUNTRIES and country in {"bra", "arg", "chi", "col", "per", "uru", "par", "ecu", "ven", "bol"}:
        return "south_america"
    if country in {"jpn", "chn", "kor", "ksa", "aus", "ind"}:
        return "asia"
    if country in {"usa", "mex"}:
        return "other"
    if country in {"eng", "esp", "ger", "ita", "fra", "ned", "por"} and slug.endswith(".1"):
        return "europe_top"
    if slug.startswith(("fifa.", "uefa.nations")):
        return "international"
    return "europe_lower"


def slug_country(slug):
    meta = SLUG_META.get(slug)
    if meta and meta[0]:
        return meta[0]
    prefix = slug.split(".")[0]
    mapped = {"ger": "ger", "eng": "eng", "esp": "esp", "ita": "ita", "fra": "fra", "ned": "ned", "por": "por",
              "bel": "bel", "tur": "tur", "gre": "gre", "sco": "sco", "cze": "cze", "arg": "arg", "bra": "bra",
              "chn": "chn", "jpn": "jpn", "ksa": "ksa", "usa": "usa", "mex": "mex", "den": "den", "nor": "nor",
              "swe": "swe", "sui": "sui", "aut": "aut", "rou": "rou", "rus": "rus", "irl": "irl", "chi": "chi",
              "col": "col", "per": "per", "uru": "uru", "par": "par", "ecu": "ecu", "aus": "aus", "ind": "ind"}
    return mapped.get(prefix)


def hinted_league(slug, league_name, country, region, cup):
    meta = SLUG_META.get(slug)
    if meta:
        return meta[2]
    return dataset_stable(slug, league_name, country, region, cup)


def dataset_stable(slug, league_name, country, region, cup):
    import dataset
    lid = f"{country or 'xx'}:{slug}"
    lid, _name = dataset.stable_league(lid, league_name, cup, region)
    return lid


def blank():
    return {
        "id": None, "src": None, "league": None, "league_name": None, "region": None, "country": None,
        "ts": None, "status": "upcoming", "minute": None, "period": 1, "hg": None, "ag": None,
        "reds": [0, 0], "winner": None, "neutral": False, "cup": False,
        "home_name": None, "away_name": None, "odds": None,
    }


def espn_events(slug, ymd):
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={ymd}"
    try:
        data = get_json(url)
    except Exception as exc:
        return slug, []
    out = []
    league_name = ((data.get("leagues") or [{}])[0].get("name")) or slug
    for ev in data.get("events") or []:
        comps = ev.get("competitions") or []
        if not comps:
            continue
        comp = comps[0]
        sides = {c.get("homeAway"): c for c in comp.get("competitors") or []}
        home, away = sides.get("home"), sides.get("away")
        if not home or not away:
            continue
        hn, an = home["team"].get("displayName"), away["team"].get("displayName")
        if women(hn) or women(an) or women(league_name):
            continue
        stype = (comp.get("status") or {}).get("type") or {}
        name = stype.get("name") or ""
        state = stype.get("state") or "pre"
        if name == "STATUS_POSTPONED":
            status = "postponed"
        elif name in {"STATUS_CANCELED", "STATUS_CANCELLED"}:
            status = "cancelled"
        elif name == "STATUS_ABANDONED":
            status = "abandoned"
        elif state == "in":
            status = "live"
        elif state == "post" or name == "STATUS_FULL_TIME":
            status = "finished"
        else:
            status = "upcoming"
        clock = (comp.get("status") or {}).get("displayClock")
        minute = minute_of(clock) if status == "live" else (minute_of(clock) if status == "finished" else None)
        period = 1
        if name.startswith("STATUS_EXTRA") or "PENALT" in name:
            period = 3
        elif minute and minute > 45:
            period = 2
        def goals(side):
            if status == "upcoming":
                return None
            raw = side.get("score")
            if raw is None or raw == "":
                return None
            try:
                return int(float(raw))
            except ValueError:
                return None
        reds = [0, 0]
        for det in comp.get("details") or []:
            if not det.get("redCard"):
                continue
            side = (det.get("team") or {}).get("id")
            if side and str(side) == str(home["team"].get("id")):
                reds[0] += 1
            elif side and str(side) == str(away["team"].get("id")):
                reds[1] += 1
        country = slug_country(slug)
        region = region_of(slug, country)
        cup = bool(SLUG_META.get(slug, (None, None, None, "cup" in slug))[3]) or "cup" in slug or "copa" in slug
        item = blank()
        item.update({
            "id": f"espn:{ev['id']}", "src": "espn", "league": slug, "league_name": league_name,
            "region": region, "country": country, "ts": iso_ts(ev["date"]), "status": status,
            "minute": minute, "period": period, "hg": goals(home), "ag": goals(away), "reds": reds,
            "neutral": region in {"europe_cups", "international"}, "cup": cup,
            "home_name": hn, "away_name": an,
            "league_id": hinted_league(slug, league_name, country, region, cup),
        })
        out.append(item)
    return slug, out


def fetch_espn(dates):
    slugs = json.loads((WEB / "espn_slugs.json").read_text(encoding="utf-8"))
    jobs = []
    for slug in slugs:
        use = dates if slug in FOCUS or slug.endswith(".1") else dates[1:4]
        for ymd in use:
            jobs.append((slug, ymd))
    found = []
    with ThreadPoolExecutor(16) as pool:
        futs = [pool.submit(espn_events, slug, ymd) for slug, ymd in jobs]
        for fut in as_completed(futs):
            _slug, rows = fut.result()
            found.extend(rows)
    print("ESPN zápasů", len(found))
    return found


def competitors_365(game):
    home, away = game.get("homeCompetitor") or {}, game.get("awayCompetitor") or {}
    if game.get("isHomeAwayInverted"):
        return away, home
    return home, away


def fetch_365(dates):
    start = dates[0]
    end = dates[-1]
    # dates are YYYYMMDD; 365 wants dd/mm/YYYY
    def conv(ymd):
        return f"{ymd[6:8]}/{ymd[4:6]}/{ymd[0:4]}"
    url = ("https://webws.365scores.com/web/games/allscores/?sports=1"
           f"&startDate={conv(start)}&endDate={conv(end)}&timezoneName=Europe/Prague&userCountryId=1")
    try:
        data = get_json(url, timeout=40)
    except Exception as exc:
        print("365 selhalo", exc)
        return []
    countries = {c["id"]: c.get("name") for c in data.get("countries") or []}
    out = []
    for game in data.get("games") or []:
        home, away = competitors_365(game)
        hn, an = home.get("name"), away.get("name")
        league_name = game.get("competitionDisplayName") or ""
        if not hn or not an or women(hn) or women(an) or women(league_name):
            continue
        text = (game.get("statusText") or "")
        low = text.lower()
        if "postpon" in low:
            status = "postponed"
        elif "cancel" in low:
            status = "cancelled"
        elif "abandon" in low:
            status = "abandoned"
        elif game.get("statusGroup") == 3 or low in {"1st half", "2nd half", "halftime"}:
            status = "live"
        elif game.get("statusGroup") == 4 or "ended" in low or "final" in low or "penalt" in low:
            status = "finished"
        else:
            status = "upcoming"
        def goals(side):
            raw = side.get("score")
            if status == "upcoming" or raw is None:
                return None
            try:
                val = int(float(raw))
            except (TypeError, ValueError):
                return None
            if val < 0:
                return None
            return val
        country = names.code_of(countries.get(home.get("countryId")))
        cup = any(w in league_name.lower() for w in ("cup", "copa", "pokal", "champions", "libertadores", "sudamericana"))
        region = "europe_cups" if any(w in league_name.lower() for w in ("champions league", "europa league", "conference")) else None
        if region is None and any(w in league_name.lower() for w in ("libertadores", "sudamericana")):
            region = "south_america"
        if region is None:
            region = region_of("", country)
        item = blank()
        minute = game.get("gameTime")
        try:
            minute = int(float(minute)) if status == "live" and minute is not None else None
        except (TypeError, ValueError):
            minute = None
        item.update({
            "id": f"s365:{game.get('id')}", "src": "s365", "league": f"s365.{game.get('competitionId')}",
            "league_name": league_name, "region": region, "country": country,
            "ts": iso_ts(game.get("startTime")), "status": status, "minute": minute,
            "period": 3 if "penalt" in low or "extra" in low else (2 if (minute or 0) > 45 else 1),
            "hg": goals(home), "ag": goals(away), "cup": cup,
            "neutral": region in {"europe_cups", "international"},
            "home_name": hn, "away_name": an,
            "league_id": dataset_stable("", league_name, country, region, cup),
        })
        out.append(item)
    print("365 zápasů", len(out))
    return out


def sofa_events(data):
    """Objekt {events: [...]} je živý feed. Ternární `or` by ho vyhodil jako prázdný."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        events = data.get("events")
        return events if isinstance(events, list) else []
    return []


def _score(raw):
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return None if value < 0 else value


def sofa_goals(block, status):
    """Skóre na kartu. current zahrnuje prodloužení; normaltime se do zobrazení nedává."""
    if not isinstance(block, dict) or status == "upcoming":
        return None
    return _score(block.get("current"))


def sofa_regulation(block, status):
    """90minutové skóre jen pro učení 1X2. Do zobrazení nepatří."""
    if status != "finished" or not isinstance(block, dict):
        return None
    return _score(block.get("normaltime"))


def sofa_clock(ev, status, now=None):
    st = ev.get("status") or {}
    desc = str(st.get("description") or "").lower()
    clock = ev.get("time") or {}
    if "halftime" in desc or desc == "ht":
        return 45, 1
    period = 1
    if "2nd" in desc:
        period = 2
    elif "pen" in desc:
        period = 5
    elif "extra" in desc or "aet" in desc:
        period = 3
    if status == "finished":
        return (120 if period >= 3 else 90), (period if period >= 3 else 2)
    if status != "live" or not clock.get("currentPeriodStartTimestamp"):
        return None, period
    now = dt.datetime.now(dt.timezone.utc).timestamp() if now is None else now
    elapsed = max(0, now - float(clock["currentPeriodStartTimestamp"]))
    sec = float(clock.get("initial") or 0) + elapsed
    cap = float(clock["max"] if clock.get("max") is not None else (2700 if period == 1 else 5400)) + float(clock.get("extra") or 0)
    if sec > cap:
        sec = cap
    return int(sec // 60), period


def fetch_sofa():
    url = "https://api.sofascore1.com/api/v1/sport/football/events/live"
    try:
        data = get_json(url)
    except Exception as exc:
        print("sofascore selhalo", exc)
        return []
    out = []
    for ev in sofa_events(data):
        home = (ev.get("homeTeam") or {}).get("name")
        away = (ev.get("awayTeam") or {}).get("name")
        tourn = ((ev.get("tournament") or {}).get("name")) or ""
        if not home or not away or women(home) or women(away) or women(tourn):
            continue
        kind = ((ev.get("status") or {}).get("type") or "")
        desc = str((ev.get("status") or {}).get("description") or "").lower()
        if kind in {"inprogress", "live"}:
            status = "live"
        elif kind == "finished":
            status = "finished"
        elif kind == "postponed" or "postpon" in desc:
            status = "postponed"
        elif "cancel" in desc:
            status = "cancelled"
        elif "abandon" in desc:
            status = "abandoned"
        else:
            status = "upcoming"
        country = names.code_of(((ev.get("tournament") or {}).get("category") or {}).get("name"))
        cup = any(w in tourn.lower() for w in ("cup", "copa", "champions", "libertadores", "sudamericana"))
        region = "europe_cups" if any(w in tourn.lower() for w in ("champions league", "europa league", "conference")) else region_of("", country)
        if "libertadores" in tourn.lower() or "sudamericana" in tourn.lower():
            region = "south_america"
        start = ev.get("startTimestamp")
        minute, period = sofa_clock(ev, status)
        item = blank()
        item.update({
            "id": f"sofa:{ev.get('id')}", "src": "sofa", "league": f"sofa.{(ev.get('tournament') or {}).get('id')}",
            "league_name": tourn, "region": region, "country": country,
            "ts": int(start) if start else None, "status": status, "minute": minute if status == "live" else None,
            "period": period, "hg": sofa_goals(ev.get("homeScore") or {}, status),
            "ag": sofa_goals(ev.get("awayScore") or {}, status),
            "hg90": sofa_regulation(ev.get("homeScore") or {}, status),
            "ag90": sofa_regulation(ev.get("awayScore") or {}, status),
            "cup": cup, "neutral": region in {"europe_cups", "international"},
            "home_name": home, "away_name": away,
            "league_id": dataset_stable("", tourn, country, region, cup),
        })
        if item["ts"]:
            out.append(item)
    print("sofascore živě", len(out))
    return out


def pair_key(item):
    day = prague_day(item["ts"]).isoformat()
    left, right = sorted((names.canon(item["home_name"]), names.canon(item["away_name"])))
    return day + "|" + left + "|" + right


def orient_to(item, home_canon):
    if names.canon(item["home_name"]) == home_canon:
        return item
    flipped = dict(item)
    flipped["home_name"], flipped["away_name"] = item["away_name"], item["home_name"]
    flipped["hg"], flipped["ag"] = item.get("ag"), item.get("hg")
    flipped["hg90"], flipped["ag90"] = item.get("ag90"), item.get("hg90")
    reds = list(item.get("reds") or [0, 0])
    flipped["reds"] = [reds[1], reds[0]] if len(reds) == 2 else reds
    odds = item.get("odds")
    if isinstance(odds, dict) and "h" in odds and "a" in odds:
        flipped["odds"] = {**odds, "h": odds["a"], "a": odds["h"]}
    return flipped


def better(a, b):
    rank = {"upcoming": 0, "postponed": 0, "cancelled": 0, "live": 1, "finished": 2, "abandoned": 2}
    if rank.get(b["status"], 0) > rank.get(a["status"], 0):
        return b
    if rank.get(a["status"], 0) > rank.get(b["status"], 0):
        return a
    # stejný stav: ESPN má stabilnější id
    if a["src"] == "espn":
        base = a
        extra = b
    elif b["src"] == "espn":
        base = b
        extra = a
    else:
        base, extra = a, b
    if base.get("hg") is None and extra.get("hg") is not None:
        base["hg"], base["ag"] = extra["hg"], extra["ag"]
    if base.get("minute") is None and extra.get("minute") is not None:
        base["minute"] = extra["minute"]
    if extra.get("odds"):
        base["odds"] = extra["odds"]
    return base


def merge(rows):
    bag = {}
    for item in rows:
        if not item.get("ts") or not item.get("home_name"):
            continue
        key = pair_key(item)
        if key not in bag:
            bag[key] = item
            continue
        base = bag[key]
        # ESPN home/away je autoritativní; otočený zdroj nesmí prohodit skóre.
        if item["src"] == "espn" and base["src"] != "espn":
            base = orient_to(base, names.canon(item["home_name"]))
            bag[key] = better(item, base)
        else:
            item = orient_to(item, names.canon(base["home_name"]))
            bag[key] = better(base, item)
    return list(bag.values())


def winner_of(item):
    if item["status"] != "finished" or item["hg"] is None or item["ag"] is None:
        return None
    if item["hg"] > item["ag"]:
        return 0
    if item["hg"] == item["ag"]:
        return 1
    return 2


def as_state_row(item, home_id, away_id):
    day = prague_day(item["ts"]).isoformat()
    return {
        "id": item["id"],
        "key": f"{day}|{home_id}|{away_id}",
        "date": day,
        "home_id": home_id, "away_id": away_id,
        "home_name": item["home_name"], "away_name": item["away_name"],
        "hg": item["hg"], "ag": item["ag"], "status": "finished",
        "league_id": item.get("league_id"), "region": item.get("region"),
        "prior": elo.prior_for(item.get("league_id"), item.get("region"), item.get("league_name") or ""),
        "neutral": bool(item.get("neutral")), "season_kind": elo.season_kind(item.get("country"), item.get("region")),
        "cup": bool(item.get("cup")),
    }


def h2h_list(state, home_id, away_id, home_name, away_name):
    key = "|".join(sorted((home_id, away_id)))
    rows = []
    for date, hid, hg, ag in (state["h2h"].get(key) or []):
        if hid == home_id:
            left, right, who = hg, ag, home_name if hg >= ag else away_name
        else:
            left, right = ag, hg
        rows.append({"date": date, "score": f"{left}-{right}", "home_id": hid, "hg": left, "ag": right})
    return rows[-8:]


def _public_line(block):
    return {"over": round(float(block["over"]), 4), "under": round(float(block["under"]), 4)}


def _public_side(side):
    if not side:
        return None
    ou = {name: _public_line(block) for name, block in (side.get("ou") or {}).items()}
    mode = side.get("mode") or [0, 0]
    return {
        "xg": round(float(side["xg"]), 4),
        "ou": ou,
        "mode": [int(mode[0]), round(float(mode[1]), 4)],
        "dist": [[int(k), round(float(p), 4)] for k, p in (side.get("dist") or [])],
    }


def _public_total(total):
    packed = _public_side(total)
    if not packed:
        return None
    lines = (total or {}).get("lines") or {}
    packed["lines"] = {name: _public_line(block) for name, block in lines.items()}
    return packed


def _public_ou(ou):
    lines = (ou or {}).get("lines") or {}
    packed = {}
    for name in ("1.5", "2.5", "3.5"):
        block = lines.get(name)
        if block:
            packed[name] = _public_line(block)
    if "2.5" not in packed:
        packed["2.5"] = {"over": round(float(ou["over"]), 4), "under": round(float(ou["under"]), 4)}
    return {"over": packed["2.5"]["over"], "under": packed["2.5"]["under"], "line": 2.5, "lines": packed}


def public_match(item, pred):
    return {
        "id": item["id"], "src": item["src"], "league": item["league"], "league_name": item["league_name"],
        "region": item["region"], "country": item["country"], "ts": item["ts"], "status": item["status"],
        "minute": item["minute"], "period": item["period"], "hg": item["hg"], "ag": item["ag"],
        "reds": item["reds"], "winner": winner_of(item), "neutral": bool(item.get("neutral")),
        "cup": bool(item.get("cup")),
        "teams": [
            {"name": item["home_name"], "id": pred["home_id"], "country": item.get("country")},
            {"name": item["away_name"], "id": pred["away_id"], "country": item.get("country")},
        ],
        "pred": {"h": round(pred["pred"][0], 4), "d": round(pred["pred"][1], 4), "a": round(pred["pred"][2], 4)},
        "lam": [round(pred["lam"][0], 4), round(pred["lam"][1], 4)],
        "xg": [
            round(float((pred.get("teams_goals") or {}).get("home", {}).get("xg", pred["lam"][0])), 4),
            round(float((pred.get("teams_goals") or {}).get("away", {}).get("xg", pred["lam"][1])), 4),
        ],
        "teams_goals": {
            "home": _public_side((pred.get("teams_goals") or {}).get("home")),
            "away": _public_side((pred.get("teams_goals") or {}).get("away")),
        } if pred.get("teams_goals") else None,
        "total_goals": _public_total(pred.get("total_goals")),
        "rho": round(pred["rho"], 4),
        "ou": _public_ou(pred["ou"]),
        "btts": round(pred["btts"], 4),
        "exact": [[s, round(p, 4)] for s, p in pred["exact"]],
        "pred_low": bool(pred["pred_low"]), "pred_note": pred["pred_note"],
        "odds": item.get("odds"),
        "elo": pred["elo"], "n": pred["n"],
        "hg90": item.get("hg90"), "ag90": item.get("ag90"),
    }


def safe_name(mid):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", mid)


def git_sha():
    env = os.environ.get("GITHUB_SHA") or ""
    if env:
        return env[:12]
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        return (out or "dev")[:12]
    except (OSError, subprocess.CalledProcessError):
        return "dev"


def copy_web():
    DIST.mkdir(parents=True, exist_ok=True)
    sha = git_sha()
    for path in WEB.iterdir():
        if path.suffix in {".html", ".css", ".js", ".svg", ".json"} or path.name == "manifest.json":
            target = DIST / path.name
            if path.name == "sw.js":
                target.write_text(path.read_text(encoding="utf-8").replace("__GIT_SHA__", sha), encoding="utf-8")
            else:
                target.write_bytes(path.read_bytes())
    (DIST / ".nojekyll").write_text("", encoding="utf-8")


def main():
    pack = predict.load_model(MODEL)
    today = dt.datetime.now(PRAGUE).date()
    dates = [(today + dt.timedelta(days=delta)).strftime("%Y%m%d") for delta in range(-2, 3)]
    rows = fetch_espn(dates) + fetch_365(dates) + fetch_sofa()
    rows = [r for r in rows if prague_day(r["ts"]) >= today - dt.timedelta(days=2) and prague_day(r["ts"]) <= today + dt.timedelta(days=2)]
    merged = merge(rows)
    print("po sloučení", len(merged))

    state_doc = {"matches": [], "ids": []}
    if STATE_PATH.exists():
        try:
            state_doc = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    finished_new = []
    for item in merged:
        if item["status"] != "finished" or item["hg"] is None:
            continue
        # id týmů až po resolve v predikci; tady předběžně podle země
        home_id = names.club_id(item["home_name"], item.get("country"))
        away_id = names.club_id(item["away_name"], item.get("country"))
        finished_new.append(as_state_row(item, home_id, away_id))
    combined = list(state_doc.get("matches") or []) + finished_new
    combined = online.trim(combined, today)
    runtime, applied = online.replay(pack["elo_blob"], combined)
    print("započteno z state", applied)

    out_matches = []
    details = {}
    for item in merged:
        if item["status"] in SKIP_STATUS and item["status"] != "postponed":
            pass
        fixture = {
            "home_name": item["home_name"], "away_name": item["away_name"], "country": item.get("country"),
            "league_id": item.get("league_id"), "region": item.get("region"), "league_name": item.get("league_name"),
            "date": prague_day(item["ts"]), "neutral": item.get("neutral"), "cup": item.get("cup"),
        }
        try:
            pred = predict.predict_fixture(
                runtime, pack["dc"], pack["booster"], pack["blend_w"], pack["elo_params"], pack["league_counts"], fixture,
                goals=pack.get("goals"),
            )
        except Exception as exc:
            print("predikce selhala", item["home_name"], exc)
            continue
        pub = public_match(item, pred)
        if pub["pred"]["h"] is None:
            continue
        out_matches.append(pub)
        home = runtime["teams"].get(pred["home_id"])
        away = runtime["teams"].get(pred["away_id"])
        detail = dict(pub)
        detail["h2h_list"] = h2h_list(runtime, pred["home_id"], pred["away_id"], item["home_name"], item["away_name"])
        detail["cards"] = [
            elo.public_team(home, pred["home_id"]) if home else {"id": pred["home_id"], "name": item["home_name"], "elo": pred["elo"][0], "n": 0},
            elo.public_team(away, pred["away_id"]) if away else {"id": pred["away_id"], "name": item["away_name"], "elo": pred["elo"][1], "n": 0},
        ]
        details[pub["id"]] = detail

    # state ukládá id z predikce (země z ligy), ať se trefí do Elo
    state_matches = []
    for pub in out_matches:
        if pub["status"] != "finished" or pub["hg"] is None:
            continue
        item = {
            "id": pub["id"], "ts": pub["ts"], "status": "finished",
            "hg": pub["hg90"] if pub.get("hg90") is not None else pub["hg"],
            "ag": pub["ag90"] if pub.get("ag90") is not None else pub["ag"],
            "home_name": pub["teams"][0]["name"], "away_name": pub["teams"][1]["name"],
            "league_id": None, "region": pub["region"], "country": pub["country"], "neutral": pub["neutral"],
            "cup": pub.get("cup"), "league_name": pub["league_name"],
        }
        state_matches.append(as_state_row(item, pub["teams"][0]["id"], pub["teams"][1]["id"]))
    # staré řádky, které dnes v rozpisu nejsou, necháme (ještě v okně 21 dní)
    seen = {m["id"] for m in state_matches}
    for old in combined:
        if old.get("id") not in seen:
            state_matches.append(old)
    state_matches = online.trim(state_matches, today)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state_out = {"matches": state_matches, "ids": [m["id"] for m in state_matches if m.get("id")]}
    STATE_PATH.write_text(json.dumps(state_out, ensure_ascii=False), encoding="utf-8")

    copy_web()
    data = DIST / "data"
    (data / "m").mkdir(parents=True, exist_ok=True)
    payload = {
        "generated": int(dt.datetime.now(dt.timezone.utc).timestamp()),
        "status": {"sources": ["espn", "s365", "sofascore"], "n": len(out_matches)},
        "matches": out_matches,
    }
    (data / "matches.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for mid, detail in details.items():
        (data / "m" / f"{safe_name(mid)}.json").write_text(json.dumps(detail, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    metrics = pack["metrics"]
    (data / "model.json").write_text(json.dumps({
        "test": metrics.get("test"), "by_region": metrics.get("by_region"),
        "international": metrics.get("international"), "coverage": metrics.get("coverage"),
        "gate": metrics.get("gate"), "history": metrics.get("history"),
        "importance": metrics.get("importance"), "notes": metrics.get("notes"),
        "split": metrics.get("split"), "trained_at": metrics.get("trained_at"),
        "data_from": metrics.get("data_from"), "data_to": metrics.get("data_to"),
        "n_matches": metrics.get("n_matches"), "train_rows": metrics.get("train_rows"),
        "test_rows": metrics.get("test_rows"), "blend_w": metrics.get("blend_w"),
        "elo_params": pack["elo_params"], "features": metrics.get("features"),
        "goals": metrics.get("goals"),
    }, ensure_ascii=False), encoding="utf-8")
    teams = []
    for tid, team in runtime["teams"].items():
        if not str(tid).startswith("club:"):
            continue
        last = team.get("last")
        if last and last < "2022-01-01":
            continue
        teams.append({"id": tid, "name": team.get("name"), "elo": round(elo.shrunk_elo(team)), "n": team.get("n"), "league": team.get("league"), "last": last})
    teams.sort(key=lambda t: -(t["elo"] or 0))
    (data / "teams.json").write_text(json.dumps(teams, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (data / "state.json").write_text(json.dumps(state_out, ensure_ascii=False), encoding="utf-8")
    cache = ROOT / "data" / "online-cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "state.json").write_text(json.dumps(state_out, ensure_ascii=False), encoding="utf-8")
    missing = [m for m in out_matches if not m.get("pred")]
    print("zápasů s predikcí", len(out_matches), "bez", len(missing))
    if missing:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
