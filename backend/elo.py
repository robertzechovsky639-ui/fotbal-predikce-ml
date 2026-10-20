"""Elo s domácí výhodou, K podle rozdílu gólů a regresí k síle soutěže mezi sezónami."""
import datetime as dt

REGRESSION = 0.25
K_BASE = 20.0
HA_CLUB = 80.0
HA_NAT = 55.0

# Jižní polokoule a ligy s kalendářním ročníkem (J1, Čína, MLS…). Evropa a Saudská Arábie: 1. červenec.
JAN_COUNTRIES = {"bra", "arg", "chi", "col", "per", "uru", "par", "ecu", "ven", "bol", "jpn", "chn", "kor", "usa", "mex"}

REGION_BASE = {
    "europe_top": 1680,
    "europe_lower": 1500,
    "czech": 1500,
    "europe_cups": 1580,
    "asia": 1500,
    "south_america": 1560,
    "international": 1500,
    "other": 1480,
}

DIV_PRIOR = {
    "E0": 1720, "E1": 1580, "E2": 1490, "E3": 1420, "EC": 1360,
    "D1": 1700, "D2": 1540, "SP1": 1700, "SP2": 1540,
    "I1": 1680, "I2": 1520, "F1": 1640, "F2": 1500,
    "N1": 1600, "P1": 1600, "B1": 1540, "T1": 1540, "G1": 1520,
    "SC0": 1500, "SC1": 1400, "SC2": 1340, "SC3": 1280,
}

def season_kind(country, region):
    if region == "international":
        return "jul"
    if country in JAN_COUNTRIES or region == "south_america":
        return "jan"
    return "jul"

def season_id(date, kind):
    if kind == "jan":
        return date.year
    return date.year if date.month >= 7 else date.year - 1

def prior_for(league_id, region, league_name=""):
    div = str(league_id).split(":")[-1]
    if div in DIV_PRIOR:
        base = DIV_PRIOR[div]
    else:
        base = REGION_BASE.get(region, 1450)
    name = (league_name or "").lower()
    level = 1
    if any(token in name for token in ("second", " 2", " ii", "fnl", "serie b", "liga 2", "division 2", "druh", "championship", "league one")):
        level = 2
    if any(token in name for token in ("third", " iii", "serie c", "league two", "division 3", "treti")):
        level = 3
    if div in DIV_PRIOR:
        return base
    return base - (level - 1) * 80

def k_factor(goal_diff):
    gap = abs(int(goal_diff))
    if gap <= 1:
        return K_BASE
    if gap == 2:
        return 30.0
    return K_BASE * (1.75 + (gap - 3) / 8.0)

def expected(elo_home, elo_away, home_adv):
    return 1.0 / (1.0 + 10 ** ((elo_away - (elo_home + home_adv)) / 400.0))

def new_state():
    return {"teams": {}, "h2h": {}}

def ensure_team(state, tid, prior, name, league_id):
    team = state["teams"].get(tid)
    if team is None:
        team = {
            "elo": float(prior), "n": 0, "last": None, "season": None, "prior": float(prior),
            "gf": [], "ga": [], "xg": [], "xga": [], "sot": [], "sota": [],
            "hgf": [], "agf": [], "euro": None, "name": name or tid, "league": league_id,
            "_names": {},
        }
        state["teams"][tid] = team
    if name:
        counts = team["_names"]
        counts[name] = counts.get(name, 0) + 1
        if counts[name] >= counts.get(team["name"], 0):
            team["name"] = name
    return team

def _parse_date(value):
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.datetime):
        return value.date()
    return dt.date.fromisoformat(str(value)[:10])

def maybe_regress(team, date, kind, target):
    sid = season_id(date, kind)
    if team["season"] is None:
        team["season"] = sid
        return
    if sid > team["season"]:
        # regrese jen když je mezi sezónami opravdu pauza (ne zimní přestávka uvnitř ročníku)
        if team["last"] is not None:
            last = _parse_date(team["last"])
            if (date - last).days >= 30:
                team["elo"] = target + (team["elo"] - target) * (1.0 - REGRESSION)
        team["season"] = sid

def _avg(values, window):
    if not values:
        return None
    chunk = values[-window:]
    return sum(chunk) / len(chunk)

def _avg_known(values, window, minimum=3):
    chunk = [v for v in values[-window:] if v is not None]
    if len(chunk) < minimum:
        return None
    return sum(chunk) / len(chunk)

def snapshot(team, date):
    if team["last"] is None:
        rest = 14
    else:
        rest = min(21, max(0, (date - _parse_date(team["last"])).days))
    euro = 0
    if team["euro"]:
        gap = (date - _parse_date(team["euro"])).days
        euro = 1 if 0 < gap <= 4 else 0
    return {
        "elo": team["elo"], "n": team["n"], "prior": team["prior"], "rest": rest, "euro": euro,
        "f5_gf": _avg(team["gf"], 5), "f5_ga": _avg(team["ga"], 5),
        "f10_gf": _avg(team["gf"], 10), "f10_ga": _avg(team["ga"], 10),
        "f5_xg": _avg_known(team["xg"], 5), "f10_xg": _avg_known(team["xg"], 10),
        "f5_sot": _avg_known(team["sot"], 5), "f10_sot": _avg_known(team["sot"], 10),
        "venue_gf": _avg(team["hgf"], 5), "venue_ga_away": _avg(team["agf"], 5),
    }

def h2h_value(state, home_id, away_id):
    key = "|".join(sorted((home_id, away_id)))
    hist = state["h2h"].get(key) or []
    if len(hist) < 2:
        return 0.0
    points = []
    for _date, hid, hg, ag in hist[-5:]:
        if hid == home_id:
            points.append(1.0 if hg > ag else 0.5 if hg == ag else 0.0)
        else:
            points.append(1.0 if ag > hg else 0.5 if ag == hg else 0.0)
    return sum(points) / len(points) - 0.5

def _push(arr, value, cap=10):
    arr.append(value)
    if len(arr) > cap:
        del arr[0]

def apply_result(state, match, want_snap=False):
    """Započte výsledek. Vrací False u odložených, kontumací a neznámého skóre.

    want_snap vrátí příznaky PO sezónní regresi a PŘED samotným zápasem.
    """
    status = match.get("status") or "finished"
    if status in {"postponed", "abandoned", "cancelled", "canceled"}:
        return False
    if match.get("hg") is None or match.get("ag") is None:
        return False
    hg, ag = int(match["hg"]), int(match["ag"])
    if hg < 0 or ag < 0 or hg > 15 or ag > 15:
        return False
    hid, aid = match["home_id"], match["away_id"]
    if not hid or not aid or hid == aid:
        return False
    date = _parse_date(match["date"])
    kind = match.get("season_kind") or "jul"
    prior_h = float(match.get("prior") or REGION_BASE.get(match.get("region"), 1450))
    prior_a = float(match.get("prior_away") or prior_h)
    home = ensure_team(state, hid, prior_h, match.get("home_name"), match.get("league_id"))
    away = ensure_team(state, aid, prior_a, match.get("away_name"), match.get("league_id"))
    maybe_regress(home, date, kind, prior_h)
    maybe_regress(away, date, kind, prior_a)
    snap = None
    if want_snap:
        snap = (snapshot(home, date), snapshot(away, date), h2h_value(state, hid, aid))
    if match.get("neutral"):
        adv = 0.0
    elif str(hid).startswith("nat:"):
        adv = HA_NAT
    else:
        adv = HA_CLUB
    exp = expected(home["elo"], away["elo"], adv)
    act = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
    k = k_factor(hg - ag)
    home["elo"] += k * (act - exp)
    away["elo"] += k * ((1.0 - act) - (1.0 - exp))
    _push(home["gf"], hg); _push(home["ga"], ag)
    _push(away["gf"], ag); _push(away["ga"], hg)
    _push(home["hgf"], hg); _push(away["agf"], ag)
    xh, xa = match.get("xg_h"), match.get("xg_a")
    _push(home["xg"], None if xh is None else float(xh))
    _push(away["xg"], None if xa is None else float(xa))
    _push(home["xga"], None if xa is None else float(xa))
    _push(away["xga"], None if xh is None else float(xh))
    sh, sa = match.get("hst"), match.get("ast")
    _push(home["sot"], None if sh is None else float(sh))
    _push(away["sot"], None if sa is None else float(sa))
    _push(home["sota"], None if sa is None else float(sa))
    _push(away["sota"], None if sh is None else float(sh))
    home["n"] += 1; away["n"] += 1
    iso = date.isoformat()
    home["last"] = iso; away["last"] = iso
    if match.get("region") == "europe_cups":
        home["euro"] = iso; away["euro"] = iso
    key = "|".join(sorted((hid, aid)))
    bucket = state["h2h"].setdefault(key, [])
    bucket.append([iso, hid, hg, ag])
    if len(bucket) > 8:
        del bucket[:-8]
    return snap if want_snap else True

def shrunk_elo(team):
    n = team.get("n") or 0
    elo = float(team["elo"])
    prior = float(team.get("prior") or 1500)
    if n >= 8:
        return elo
    weight = n / 8.0
    return prior * (1 - weight) + elo * weight

def public_team(team, tid):
    return {
        "id": tid,
        "name": team.get("name") or tid,
        "league": team.get("league"),
        "elo": round(team["elo"]),
        "n": team["n"],
        "prior": round(team.get("prior") or 1500),
        "last": team.get("last"),
        "f5_gf": team["gf"][-5:],
        "f5_ga": team["ga"][-5:],
        "f10_gf": team["gf"][-10:],
        "f10_ga": team["ga"][-10:],
        "xg": [x for x in team["xg"][-10:]],
        "sot": [x for x in team["sot"][-10:]],
        "hgf": team["hgf"][-5:],
        "agf": team["agf"][-5:],
        "rest_last": team.get("last"),
        "euro": team.get("euro"),
    }

def dump_state(state, trained_through, recent_keys, elo_params):
    teams = {}
    for tid, team in state["teams"].items():
        item = public_team(team, tid)
        item["elo_raw"] = team["elo"]
        item["season"] = team.get("season")
        item["prior"] = team.get("prior")
        item["gf"] = team["gf"][-10:]
        item["ga"] = team["ga"][-10:]
        item["xg"] = team["xg"][-10:]
        item["xga"] = team["xga"][-10:]
        item["sot"] = team["sot"][-10:]
        item["sota"] = team["sota"][-10:]
        item["hgf"] = team["hgf"][-10:]
        item["agf"] = team["agf"][-10:]
        teams[tid] = item
    return {
        "trained_through": trained_through,
        "recent_keys": list(recent_keys),
        "elo_params": elo_params,
        "teams": teams,
        "h2h": state["h2h"],
    }

def load_runtime(blob):
    """Stav po tréninku převede zpět na strukturu, do které umí apply_result."""
    state = new_state()
    for tid, item in (blob.get("teams") or {}).items():
        state["teams"][tid] = {
            "elo": float(item.get("elo_raw", item.get("elo", 1500))),
            "n": int(item.get("n") or 0),
            "last": item.get("last"),
            "season": item.get("season"),
            "prior": float(item.get("prior") or 1500),
            "gf": list(item.get("gf") or []),
            "ga": list(item.get("ga") or []),
            "xg": list(item.get("xg") or []),
            "xga": list(item.get("xga") or []),
            "sot": list(item.get("sot") or []),
            "sota": list(item.get("sota") or []),
            "hgf": list(item.get("hgf") or []),
            "agf": list(item.get("agf") or []),
            "euro": item.get("euro"),
            "name": item.get("name") or tid,
            "league": item.get("league"),
            "_names": {item.get("name") or tid: 1},
        }
    state["h2h"] = {k: [list(x) for x in v] for k, v in (blob.get("h2h") or {}).items()}
    return state
