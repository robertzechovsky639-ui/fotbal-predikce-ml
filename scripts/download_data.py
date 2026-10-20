"""Stáhne football-data.co.uk, openfootball, reprezentace a Understat xG. Surová data se necommitují."""
import gzip, json, pathlib, shutil, subprocess, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
UA = {"User-Agent": "Mozilla/5.0 (compatible; fotbal-predikce/1.0; research)"}

DIVS = ["E0", "E1", "E2", "E3", "EC", "SC0", "SC1", "SC2", "SC3", "D1", "D2", "I1", "I2",
        "SP1", "SP2", "F1", "F2", "N1", "B1", "P1", "T1", "G1"]
EXTRAS = ["ARG", "AUT", "BRA", "CHN", "DNK", "FIN", "IRL", "JPN", "MEX", "NOR", "POL", "ROU", "RUS", "SWE", "SWZ", "USA"]
UNDER = ["EPL", "La_liga", "Bundesliga", "Serie_A", "Ligue_1"]
REPOS = {
    "europe": "https://github.com/openfootball/europe.git",
    "champions-league": "https://github.com/openfootball/champions-league.git",
    "south-america": "https://github.com/openfootball/south-america.git",
    "world": "https://github.com/openfootball/world.git",
}


def seasons():
    out = []
    for year in range(1993, 2027):
        out.append(f"{year % 100:02d}{(year + 1) % 100:02d}")
    return out


def fetch(url, dest, timeout=40):
    dest = pathlib.Path(dest)
    if dest.exists() and dest.stat().st_size > 80:
        return "cached"
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final = resp.geturl()
            data = resp.read()
    except Exception as exc:
        return f"err {exc}"
    # football-data občas přesměruje špatný kód země na jiný CSV (KOR → NOR).
    # Sezónní soubor ukládáme jako 9394_E0.csv, ale URL končí na /E0.csv – hlídá se vzdálené jméno.
    remote = url.rstrip("/").split("/")[-1]
    if remote.endswith(".csv") and "football-data.co.uk" in url:
        if not final.split("?")[0].rstrip("/").endswith("/" + remote):
            return f"redirect {final}"
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    if dest.suffix == ".csv" and b"," not in data[:400]:
        return "not csv"
    dest.write_bytes(data)
    return "ok"


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    jobs = []
    fd = RAW / "fd"
    for season in seasons():
        for div in DIVS:
            url = f"https://www.football-data.co.uk/mmz4281/{season}/{div}.csv"
            jobs.append((url, fd / f"{season}_{div}.csv"))
    extra = RAW / "fdnew"
    for code in EXTRAS:
        jobs.append((f"https://www.football-data.co.uk/new/{code}.csv", extra / f"{code}.csv"))
    jobs.append(("https://raw.githubusercontent.com/martj42/international_results/master/results.csv", RAW / "internationals.csv"))
    ust = RAW / "understat"
    for league in UNDER:
        for year in range(2014, 2027):
            url = f"https://understat.com/getLeagueData/{league}/{year}"
            jobs.append((url, ust / f"{league}-{year}.json"))

    def one(job):
        url, dest = job
        headers = UA
        if "understat" in url:
            req_headers = dict(UA)
            req_headers["X-Requested-With"] = "XMLHttpRequest"
            req_headers["Referer"] = "https://understat.com/"
            dest = pathlib.Path(dest)
            if dest.exists() and dest.stat().st_size > 80:
                return dest.name, "cached"
            dest.parent.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(url, headers=req_headers)
            try:
                with urllib.request.urlopen(req, timeout=40) as resp:
                    data = resp.read()
            except Exception as exc:
                return dest.name, f"err {exc}"
            if data[:2] == b"\x1f\x8b":
                data = gzip.decompress(data)
            dest.write_bytes(data)
            return dest.name, "ok"
        return pathlib.Path(dest).name, fetch(url, dest)

    ok = err = 0
    with ThreadPoolExecutor(8) as pool:
        for fut in as_completed([pool.submit(one, job) for job in jobs]):
            name, status = fut.result()
            if status in {"ok", "cached"}:
                ok += 1
            else:
                err += 1
                if not str(status).startswith("err HTTP Error 404") and "404" not in str(status):
                    print(name, status)
    print(f"soubory ok/cache {ok}, chyby {err}")

    of = RAW / "of"
    of.mkdir(parents=True, exist_ok=True)
    for name, url in REPOS.items():
        dest = of / name
        if dest.exists():
            print("repo", name, "už je")
            continue
        subprocess.run(["git", "clone", "--depth", "1", url, str(dest)], check=False)

    status = {"clubelo": "api clubelo.com vrací 502 / timeout, historický dump není; vlastní Elo"}
    (RAW / "source_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print("hotovo", RAW)


if __name__ == "__main__":
    main()
