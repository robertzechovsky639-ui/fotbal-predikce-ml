"""Historické zápasy: football-data.co.uk (hlavní + new), openfootball, reprezentační CSV, Understat xG."""
import csv, datetime as dt, pathlib, re
import names
import odds as odds_mod
import elo as elo_mod

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

DIV_META = {
    "E0": ("eng", "europe_top", "Premier League"),
    "E1": ("eng", "europe_lower", "Championship"),
    "E2": ("eng", "europe_lower", "League One"),
    "E3": ("eng", "europe_lower", "League Two"),
    "EC": ("eng", "europe_lower", "National League"),
    "D1": ("ger", "europe_top", "Bundesliga"),
    "D2": ("ger", "europe_lower", "2. Bundesliga"),
    "SP1": ("esp", "europe_top", "La Liga"),
    "SP2": ("esp", "europe_lower", "La Liga 2"),
    "I1": ("ita", "europe_top", "Serie A"),
    "I2": ("ita", "europe_lower", "Serie B"),
    "F1": ("fra", "europe_top", "Ligue 1"),
    "F2": ("fra", "europe_lower", "Ligue 2"),
    "N1": ("ned", "europe_top", "Eredivisie"),
    "P1": ("por", "europe_top", "Primeira Liga"),
    "B1": ("bel", "europe_lower", "Pro League"),
    "T1": ("tur", "europe_lower", "Super Lig"),
    "G1": ("gre", "europe_lower", "Super League"),
    "SC0": ("sco", "europe_lower", "Premiership"),
    "SC1": ("sco", "europe_lower", "Championship"),
    "SC2": ("sco", "europe_lower", "League One"),
    "SC3": ("sco", "europe_lower", "League Two"),
}

EXTRA_COUNTRY = {
    "ARG": "arg", "AUT": "aut", "BRA": "bra", "CHN": "chn", "DNK": "den", "FIN": "fin",
    "IRL": "irl", "JPN": "jpn", "MEX": "mex", "NOR": "nor", "POL": "pol", "ROU": "rou",
    "RUS": "rus", "SWE": "swe", "SWZ": "sui", "USA": "usa",
}

SA = {"arg", "bra", "chi", "col", "per", "uru", "par", "ecu", "ven", "bol"}
ASIA = {"jpn", "chn", "kor", "ksa", "aus", "ind", "qat", "uae", "irn", "irq", "kaz"}
OTHER = {"usa", "mex", "can", "crc", "hon", "gua", "slv", "rsa"}

UNDERSTAT = {"EPL": "eng", "La_liga": "esp", "Bundesliga": "ger", "Serie_A": "ita", "Ligue_1": "fra"}

MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
DATE_LINE = re.compile(r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Z][a-z]{2})\s+(\d{1,2})(?:\s*,)?(?:\s+(\d{4}))?\s*$")
SCORE_LINE = re.compile(r"(\d{1,2})\s*-\s*(\d{1,2})")
COUNTRY_SUFFIX = re.compile(r"\(([A-Za-z]{3})\)\s*$")
CUP_WORDS = ("champions league", "europa league", "conference", "libertadores", "sudamericana", "copa del rey", "fa cup", "pokal", "coppa", "coupe", "cup", "pohár", "super cup")


def parse_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def region_for(country, league_name, cup=False):
    if cup and any(w in (league_name or "").lower() for w in ("libertadores", "sudamericana")):
        return "south_america"
    if cup and any(w in (league_name or "").lower() for w in ("champions", "europa", "conference", "uefa")):
        return "europe_cups"
    if country == "cze":
        return "czech"
    if country in SA:
        return "south_america"
    if country in ASIA:
        return "asia"
    if country in OTHER:
        return "other"
    return "europe_lower"


def _num(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        number = float(value)
    except ValueError:
        return None
    if number != number:
        return None
    return number


def stable_league(league_id, league_name, cup, region):
    """Poháry drží jedno id napříč sezónami, ať se nesypou na desítky krátkých názvů."""
    name = (league_name or "").lower()
    plain = names.strip_accents(name)
    if "czech" in plain and any(w in plain for w in ("first league", "chance liga", "fortuna")):
        return "cze:1", "Chance Liga"
    if "czech" in plain and "national" in plain:
        return "cze:2", "Česká národní liga"
    if "champions league" in name or "liga mistru" in plain:
        return "uefa:ucl", "Liga mistrů"
    if "europa league" in name or "uefa cup" in name:
        return "uefa:uel", "Evropská liga"
    if "conference league" in name or "europa conference" in name:
        return "uefa:uecl", "Konferenční liga"
    if "libertadores" in name:
        return "conmebol:libertadores", "Copa Libertadores"
    if "sudamericana" in name:
        return "conmebol:sudamericana", "Copa Sudamericana"
    if cup and region == "europe_cups":
        return league_id, league_name
    return league_id, league_name


def _match(date, league_id, league_name, country, region, home_name, away_name, hg, ag, source, cup=False, neutral=False, row=None):
    league_id, league_name = stable_league(league_id, league_name, cup, region)
    if date is None or hg is None or ag is None:
        return None
    try:
        hg, ag = int(hg), int(ag)
    except (TypeError, ValueError):
        return None
    if hg < 0 or ag < 0 or hg > 15 or ag > 15:
        return None
    pool = "nat" if region == "international" else "club"
    if pool == "nat":
        home_id, away_id = names.nat_id(home_name), names.nat_id(away_name)
    else:
        home_id, away_id = names.club_id(home_name, country), names.club_id(away_name, country)
    if home_id == away_id:
        return None
    picked = odds_mod.pick_odds(row) if row else None
    imp = odds_mod.implied(picked)
    prior = elo_mod.prior_for(league_id, region, league_name)
    kind = "jul" if region == "international" else elo_mod.season_kind(country, region)
    item = {
        "date": date, "league_id": league_id, "league_name": league_name, "country": country,
        "region": region, "home_id": home_id, "away_id": away_id,
        "home_name": str(home_name).strip(), "away_name": str(away_name).strip(),
        "hg": hg, "ag": ag, "cup": bool(cup), "neutral": bool(neutral), "pool": pool,
        "source": source, "prior": prior, "prior_away": prior, "season_kind": kind,
        "status": "finished", "hs": None, "as": None, "hst": None, "ast": None,
        "xg_h": None, "xg_a": None, "imp": imp,
        "key": f"{date.isoformat()}|{home_id}|{away_id}",
    }
    if row:
        item["hs"] = _num(row.get("HS"))
        item["as"] = _num(row.get("AS"))
        item["hst"] = _num(row.get("HST"))
        item["ast"] = _num(row.get("AST"))
    return item


class Bag:
    def __init__(self):
        self.rows = []
        self.keys = set()
        self.near = {}

    def _near(self, home, away, date, window):
        bucket = self.near.get((home, away))
        if not bucket:
            return False
        if window == 0:
            return date in bucket
        return (date in bucket) or ((date - dt.timedelta(days=1)) in bucket) or ((date + dt.timedelta(days=1)) in bucket)

    def add(self, match, window=0):
        if not match:
            return False
        if match["key"] in self.keys or self._near(match["home_id"], match["away_id"], match["date"], window):
            return False
        self.keys.add(match["key"])
        self.near.setdefault((match["home_id"], match["away_id"]), set()).add(match["date"])
        self.rows.append(match)
        return True


def _read_csv(path):
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "latin1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("latin1", "replace")
    return list(csv.DictReader(text.splitlines()))


def load_main(bag):
    folder = RAW / "fd"
    if not folder.exists():
        return 0
    n = 0
    for path in sorted(folder.glob("*.csv")):
        div = path.name.split("_")[-1].replace(".csv", "")
        meta = DIV_META.get(div)
        if not meta:
            continue
        country, region, label = meta
        for row in _read_csv(path):
            date = parse_date(row.get("Date"))
            match = _match(date, f"{country}:{div}", label, country, region, row.get("HomeTeam"), row.get("AwayTeam"),
                           row.get("FTHG", row.get("HG")), row.get("FTAG", row.get("AG")), "football-data", row=row)
            if bag.add(match):
                n += 1
    return n


def load_extra(bag):
    folder = RAW / "fdnew"
    if not folder.exists():
        return 0
    n = 0
    for path in sorted(folder.glob("*.csv")):
        code = path.stem.upper()
        country = EXTRA_COUNTRY.get(code)
        if not country:
            continue
        for row in _read_csv(path):
            league_name = (row.get("League") or "").strip() or code
            region = region_for(country, league_name, cup=any(w in league_name.lower() for w in CUP_WORDS))
            if code in {"MEX", "USA"}:
                region = "other"
            date = parse_date(row.get("Date"))
            league_id = f"{country}:{names.canon(league_name) or code.lower()}"
            # Kurzy v těchto souborech jsou jen closing (PSCH, B365CH) – pick_odds je nevezme.
            match = _match(date, league_id, league_name, country, region, row.get("Home"), row.get("Away"),
                           row.get("HG"), row.get("AG"), "football-data-new", cup=("cup" in league_name.lower() or "copa" in league_name.lower()), row=row)
            if bag.add(match):
                n += 1
    return n


def load_internationals(bag):
    path = RAW / "internationals.csv"
    if not path.exists():
        return 0
    n = 0
    for row in _read_csv(path):
        date = parse_date(row.get("date"))
        if date is None or date < dt.date(1993, 1, 1):
            continue
        neutral = str(row.get("neutral") or "").strip().lower() in {"true", "1", "yes"}
        tournament = row.get("tournament") or "International"
        match = _match(date, "nat:international", tournament, None, "international",
                       row.get("home_team"), row.get("away_team"), row.get("home_score"), row.get("away_score"),
                       "martj42", cup=("cup" in tournament.lower() or "nations league" in tournament.lower()), neutral=neutral)
        if match:
            match["prior"] = 1500
            match["prior_away"] = 1500
            match["season_kind"] = "jul"
        if bag.add(match):
            n += 1
    return n


def _split_teams(left):
    if " v " not in left:
        return None
    home, away = left.split(" v ", 1)
    suffix_h = COUNTRY_SUFFIX.search(home.strip())
    suffix_a = COUNTRY_SUFFIX.search(away.strip())
    country_h = names.code_of(suffix_h.group(1)) if suffix_h else None
    country_a = names.code_of(suffix_a.group(1)) if suffix_a else None
    if suffix_h:
        home = home[:suffix_h.start()]
    if suffix_a:
        away = away[:suffix_a.start()]
    return home.strip(), away.strip(), country_h, country_a


def parse_openfootball(text, default_country, default_region, source, cup=None):
    """Vrátí seznam zápasů z textu openfootball. cup=None odhadne z názvu."""
    found = []
    title = "League"
    year = None
    current = None
    last_month = None
    forced_cup = cup
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("▪") or line.startswith("##"):
            continue
        if line.startswith("="):
            title = line.lstrip("= ").strip()
            years = re.findall(r"(19|20)\d{2}", title)
            if years:
                year = int(years[0])
            last_month = None
            continue
        dated = DATE_LINE.match(line)
        if dated:
            month = MONTHS[dated.group(1)]
            day = int(dated.group(2))
            if dated.group(3):
                year = int(dated.group(3))
            elif year is None:
                continue
            elif last_month is not None and month < last_month - 6:
                year += 1
            last_month = month
            try:
                current = dt.date(year, month, day)
            except ValueError:
                current = None
            continue
        if current is None:
            continue
        low = line.lower()
        if any(word in low for word in ("postpon", "canc", "awarded", "walkover", "w/o", "abd")):
            if not SCORE_LINE.search(line):
                continue
        body = re.sub(r"^\d{1,2}:\d{2}\s+", "", line)
        inline = re.match(r"^(?P<home>.+?)\s+(\d{1,2})\s*-\s*(\d{1,2})(?:\s*\(\d{1,2}\s*-\s*\d{1,2}\))?\s+(?P<away>.+?)\s*$", body)
        if inline and " v " not in body:
            home, away = inline.group("home").strip(), inline.group("away").strip()
            hg, ag = int(inline.group(2)), int(inline.group(3))
            ch = ca = None
        else:
            if " v " not in body:
                continue
            scored = SCORE_LINE.search(body)
            if not scored:
                continue
            hg, ag = int(scored.group(1)), int(scored.group(2))
            teams = _split_teams(body[:scored.start()])
            if not teams:
                continue
            home, away, ch, ca = teams
        is_cup = forced_cup if forced_cup is not None else any(w in title.lower() for w in CUP_WORDS)
        country = ch or ca or default_country
        # hostia z jiné země: id se skládá zvlášť níž
        region = default_region
        if is_cup and default_region == "europe_cups":
            region = "europe_cups"
        elif is_cup and "libertadores" in title.lower() or (is_cup and "sudamericana" in title.lower()):
            region = "south_america"
        league_id = f"{country or 'xx'}:{names.canon(title) or 'league'}"
        if len(league_id) > 80:
            league_id = league_id[:80]
        match = _match(current, league_id, title, country, region, home, away, hg, ag, source, cup=is_cup)
        if not match:
            continue
        # přepiš id, když mají týmy vlastní zemi (poháry)
        if ch or ca:
            home_c = ch or country
            away_c = ca or country
            match["home_id"] = names.club_id(home, home_c)
            match["away_id"] = names.club_id(away, away_c)
            if match["home_id"] == match["away_id"]:
                continue
            match["key"] = f"{current.isoformat()}|{match['home_id']}|{match['away_id']}"
            match["country"] = home_c
            match["prior"] = elo_mod.prior_for(match["league_id"], region, title)
            match["prior_away"] = elo_mod.prior_for(match["league_id"], region, title)
            match["season_kind"] = elo_mod.season_kind(home_c, region)
        found.append(match)
    return found


def load_openfootball(bag):
    base = RAW / "of"
    if not base.exists():
        return 0
    n = 0
    specs = [
        (base / "europe", "europe", False),
        (base / "champions-league", "europe_cups", True),
        (base / "south-america", "south_america", None),
        (base / "world", "asia", None),
    ]
    for root, kind, cup_flag in specs:
        if not root.exists():
            continue
        for path in root.rglob("*.txt"):
            parts = set(path.parts)
            if "rsssf" in parts or "node_modules" in parts:
                continue
            rel = path.relative_to(root)
            top = rel.parts[0] if len(rel.parts) > 1 else ""
            country_from_path = None
            for part in rel.parts[:-1]:
                code = names.code_of(part.replace("-", " "))
                if code:
                    country_from_path = code
            text = path.read_text(encoding="utf-8", errors="replace")
            name = path.name.lower()
            if kind == "europe_cups" or any(name.startswith(p) for p in ("cl", "el", "conf")):
                region, cup = "europe_cups", True
                country = None
            elif "copa" in name or "libertadores" in name or "sudamericana" in str(path).lower():
                region, cup = "south_america", True
                country = country_from_path or (names.code_of(top.replace("-", " ")) if top else None)
            elif kind == "asia" or kind == "south_america":
                country = country_from_path or (names.code_of(top.replace("-", " ")) if top else None)
                region = region_for(country, path.stem, cup=False)
                cup = bool(cup_flag) if cup_flag is not None else ("cup" in name)
            else:
                country = country_from_path or (names.code_of(top.replace("-", " ")) if top else None)
                region = "czech" if country == "cze" else region_for(country or "xx", path.stem, cup=False)
                cup = "cup" in name or name.endswith("cup.txt")
            # země, které už má football-data v plné kvalitě, bereme jen když jde o nižší soutěž / pohár
            fd_countries = {"eng", "ger", "esp", "ita", "fra", "ned", "por", "bel", "tur", "gre", "sco",
                            "aut", "den", "fin", "irl", "nor", "pol", "rou", "rus", "swe", "sui", "arg", "bra", "jpn", "chn", "mex", "usa"}
            lower = bool(re.search(r"(^|_)(2|3|ii|b)(_|\.|$)|second|fnl|liga2", name))
            if country in fd_countries and not cup and not lower and kind == "europe":
                continue
            for match in parse_openfootball(text, country, region, "openfootball", cup=cup if cup else None):
                if bag.add(match, window=1):
                    n += 1
    return n


def load_understat(rows):
    folder = RAW / "understat"
    if not folder.exists():
        return 0
    index = {(m["date"], m["home_id"], m["away_id"]): m for m in rows}
    hit = 0
    total = 0
    for path in folder.glob("*.json"):
        league = path.stem.rsplit("-", 1)[0]
        country = UNDERSTAT.get(league)
        if not country:
            continue
        import json
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for item in payload.get("dates") or []:
            total += 1
            try:
                date = dt.date.fromisoformat(str(item.get("datetime"))[:10])
                hg_name = item["h"]["title"]
                ag_name = item["a"]["title"]
                xh = float(item["xG"]["h"])
                xa = float(item["xG"]["a"])
            except (KeyError, TypeError, ValueError):
                continue
            home_id = names.club_id(hg_name, country)
            away_id = names.club_id(ag_name, country)
            match = index.get((date, home_id, away_id))
            if match is None:
                match = index.get((date + dt.timedelta(days=1), home_id, away_id)) or index.get((date - dt.timedelta(days=1), home_id, away_id))
            if match is None:
                continue
            match["xg_h"] = xh
            match["xg_a"] = xa
            hit += 1
    print(f"understat xG spojeno {hit}/{total}")
    return hit


def load_all():
    bag = Bag()
    print("football-data hlavní", load_main(bag))
    print("football-data extra", load_extra(bag))
    print("openfootball", load_openfootball(bag))
    print("reprezentace", load_internationals(bag))
    bag.rows.sort(key=lambda m: (m["date"], m["league_id"], m["home_id"]))
    load_understat(bag.rows)
    print("zápasů celkem", len(bag.rows))
    return bag.rows


def coverage(rows):
    out = {}
    for match in rows:
        region = match["region"]
        slot = out.setdefault(region, {"matches": 0, "leagues": set(), "sources": set(), "from": None, "to": None})
        slot["matches"] += 1
        slot["leagues"].add(match["league_name"])
        slot["sources"].add(match["source"])
        if slot["from"] is None or match["date"] < slot["from"]:
            slot["from"] = match["date"]
        if slot["to"] is None or match["date"] > slot["to"]:
            slot["to"] = match["date"]
    public = {}
    for region, slot in sorted(out.items()):
        public[region] = {
            "matches": slot["matches"],
            "n_leagues": len(slot["leagues"]),
            "leagues": sorted(slot["leagues"])[:40],
            "sources": sorted(slot["sources"]),
            "from": slot["from"].isoformat() if slot["from"] else None,
            "to": slot["to"].isoformat() if slot["to"] else None,
        }
    return public
