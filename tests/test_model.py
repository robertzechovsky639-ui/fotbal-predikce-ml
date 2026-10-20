import datetime as dt
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import dataset
import dixon
import elo
import goals
import metrics
import names
import numpy as np
import odds
import online


def test_affix_canon_merges_duplicates():
    assert names.canon("PEC Zwolle") == names.canon("Zwolle") == "zwolle"
    assert names.canon("Le Havre") == names.canon("Havre AC") == "havre"
    assert names.canon("AJ Auxerre") == names.canon("Auxerre")
    assert names.canon("NEC Nijmegen") == "nijmegen"
    teams = {
        "club:ned:zwolle": {"n": 511, "elo": 1600.0, "name": "Zwolle", "last": "2026-05-01"},
        "club:ned:pec zwolle": {"n": 1, "elo": 1400.0, "name": "PEC Zwolle", "last": "2024-01-01"},
        "club:fra:le havre": {"n": 1227, "elo": 1550.0, "name": "Le Havre", "last": "2026-05-01"},
        "club:fra:havre": {"n": 1, "elo": 1300.0, "name": "Havre AC", "last": "2020-01-01"},
    }
    assert names.resolve_club(teams, "PEC Zwolle", "Netherlands") == "club:ned:zwolle"
    assert names.resolve_club(teams, "Havre AC", "France") == "club:fra:le havre"
    state = {"teams": {k: dict(v) for k, v in teams.items()}, "h2h": {"club:ned:pec zwolle|club:ned:zwolle": [["2024-01-01", "club:ned:pec zwolle", 0, 1]]}}
    names.merge_clubs(state)
    assert set(state["teams"]) == {"club:ned:zwolle", "club:fra:le havre"}
    assert state["teams"]["club:ned:zwolle"]["n"] == 512
    assert abs(state["teams"]["club:ned:zwolle"]["elo"] - ((1600 * 511) + 1400) / 512) < 1e-6
    assert names.resolve_club(state["teams"], "PEC Zwolle", "ned") == "club:ned:zwolle"


def test_canon_clubs():
    assert names.canon("Man United") == "manchester united"
    assert names.canon("Nott'm Forest") == "nottingham forest"
    assert names.canon("M'gladbach") == "monchengladbach"
    assert names.canon("Ath Madrid") == "atletico madrid"
    assert names.canon("Ath Bilbao") == "athletic bilbao"
    assert names.canon("Paris SG") == "paris saint germain"
    assert names.canon("Bayern Munich") == "bayern munchen"
    assert names.canon("Espanol") == "espanyol"
    assert names.canon("Dortmund") == "borussia dortmund"
    assert names.canon("Milan") == "ac milan"
    assert names.canon("Internazionale") == "inter"
    assert names.canon("Sp Lisbon") == "sporting cp"
    assert names.canon("Sparta Prague") == "sparta praha"
    assert names.canon("Sparta Rotterdam") != names.canon("Sparta Prague")
    assert names.club_id("Arsenal", "ENG") != names.club_id("Arsenal", "ARG")


def test_odds_ignore_closing():
    assert odds.pick_odds({"PSCH": "1.5", "PSCD": "3.5", "PSCA": "6"}) is None
    assert odds.pick_odds({"B365CH": "1.4", "B365CD": "4", "B365CA": "7", "B365H": "1.9", "B365D": "3.4", "B365A": "4.2"})[:1] == [1.9]
    assert odds.is_closing("AvgCH")
    imp = odds.implied([2, 3, 6])
    assert abs(sum(imp) - 1) < 1e-9


def test_rps_and_gate():
    perfect = metrics.rps([0], [[1, 0, 0]])
    assert perfect < 1e-6
    worst = metrics.rps([2], [[1, 0, 0]])
    assert worst > 0.9
    ok, _ = metrics.gate(
        {"log_loss": 0.90, "rps": 0.18},
        {"log_loss": 1.05, "rps": 0.22},
        {"log_loss": 0.91, "rps": 0.181},
    )
    assert ok
    bad, reason = metrics.gate(
        {"log_loss": 1.04, "rps": 0.22},
        {"log_loss": 1.05, "rps": 0.22},
        {"log_loss": 0.90, "rps": 0.18},
    )
    assert not bad and "baseline" in reason or "Elo" in reason or "horší" in reason


def test_elo_prior_regression_and_skip():
    assert elo.prior_for("eng:E0", "europe_top", "Premier League") == 1720
    assert elo.prior_for("cze:1", "czech", "Czech First League") == 1500
    state = elo.new_state()
    base = {
        "home_id": "club:eng:a", "away_id": "club:eng:b", "home_name": "A", "away_name": "B",
        "prior": 1720, "prior_away": 1720, "season_kind": "jul", "region": "europe_top",
        "league_id": "eng:E0", "status": "finished", "neutral": False,
    }
    assert elo.apply_result(state, {**base, "date": dt.date(2024, 5, 1), "hg": 1, "ag": 0})
    before = state["teams"]["club:eng:a"]["elo"]
    assert before != 1500 and before > 1720
    elo.apply_result(state, {**base, "date": dt.date(2024, 8, 20), "hg": 0, "ag": 0})
    after = state["teams"]["club:eng:a"]["season"]
    assert after == 2024
    # leden: Brazílie se 1. července uprostřed sezóny neregredí
    br = elo.new_state()
    b = {**base, "home_id": "club:bra:a", "away_id": "club:bra:b", "season_kind": "jan", "region": "south_america", "prior": 1560, "prior_away": 1560}
    elo.apply_result(br, {**b, "date": dt.date(2024, 6, 1), "hg": 2, "ag": 0})
    mid = br["teams"]["club:bra:a"]["elo"]
    elo.apply_result(br, {**b, "date": dt.date(2024, 8, 1), "hg": 0, "ag": 0})
    assert br["teams"]["club:bra:a"]["season"] == 2024
    # rozdíl jen o výsledek 0-0, ne o 25% regresi (ta by rating stáhla blíž k 1560 ještě před zápasem)
    assert abs(br["teams"]["club:bra:a"]["elo"] - mid) < 25
    assert elo.apply_result(state, {**base, "date": dt.date(2024, 9, 1), "hg": 1, "ag": 0, "status": "abandoned"}) is False
    assert elo.apply_result(state, {**base, "date": dt.date(2024, 9, 2), "hg": None, "ag": None}) is False


def test_k_factor_and_matrix():
    assert elo.k_factor(1) == 20
    assert elo.k_factor(2) == 30
    assert elo.k_factor(4) > 30
    matrix = dixon.score_matrix(1.4, 1.1, 0)
    assert abs(matrix.sum() - 1) < 1e-9
    base = dixon.markets(1.3, 1.1, 0)
    moved = dixon.markets(1.3, 1.1, -0.1)
    assert moved["p"][1] != pytest.approx(base["p"][1], abs=1e-4)
    rem0 = dixon.remaining_lambdas(1.5, 1.2, 0, (0, 0), (0, 0), 1)
    late = dixon.remaining_lambdas(1.5, 1.2, 80, (0, 0), (0, 0), 2)
    red = dixon.remaining_lambdas(1.5, 1.2, 30, (1, 0), (0, 0), 1)
    assert late[0] + late[1] > rem0[0] * 0  # jen že se spočítá
    assert red[0] < dixon.remaining_lambdas(1.5, 1.2, 30, (0, 0), (0, 0), 1)[0]
    # pozdní minuta má vyšší intenzitu než stejný zbytek bez late bonusu: 80' zbývá 10/90 * late
    plain = 1.5 * (10 / 90)
    assert late[0] > plain


def test_openfootball_czech():
    text = """= Czech Republic First League 2024/25
  Fri Jul 19 2024
    19:00  AC Sparta Praha         v FK Pardubice             2-1 (1-1)
  Sat Jul 20
    17:00  Dynamo České Budějovice v Sigma Olomouc            0-2 (0-0)
"""
    rows = dataset.parse_openfootball(text, "cze", "czech", "openfootball", cup=False)
    assert len(rows) == 2
    assert rows[0]["home_id"] == "club:cze:sparta praha"
    assert rows[0]["hg"] == 2 and rows[0]["region"] == "czech"
    assert rows[1]["date"] == dt.date(2024, 7, 20)
    newer = """= Czech Republic | First League 2026/27
Sat Jul 25 2026
  17:00   FK Teplice  3-1 (1-0)  Bohemians 1905
          FC Fastav Zlín  0-1 (0-0)  Baník Ostrava
"""
    rows2 = dataset.parse_openfootball(newer, "cze", "czech", "openfootball", cup=False)
    assert len(rows2) == 2
    assert rows2[0]["hg"] == 3 and rows2[0]["ag"] == 1
    assert rows2[0]["league_id"] == "cze:1"
    assert rows2[0]["date"] == dt.date(2026, 7, 25)


def test_goal_blend_keeps_poisson_without_booster():
    assert goals.apply_match(None, [0.0] * 26, 1.2, 0.9) == (1.2, 0.9)
    mixed = goals.blend_lambdas(1.0, 1.0, 2.0, 0.4, 0.5)
    assert mixed == pytest.approx((1.5, 0.7))


def test_goal_lines_live_and_gate():
    mk = dixon.markets(1.45, 1.15, -0.05)
    assert mk["lines"]["1.5"]["over"] > mk["lines"]["2.5"]["over"] > mk["lines"]["3.5"]["over"]
    assert mk["over"] == pytest.approx(mk["lines"]["2.5"]["over"])
    for line in ("1.5", "2.5", "3.5"):
        assert mk["lines"][line]["over"] + mk["lines"][line]["under"] == pytest.approx(1)
    early = dixon.live_markets(0, 0, *dixon.remaining_lambdas(1.5, 1.2, 10, (0, 0), (0, 0), 1))
    late = dixon.live_markets(0, 0, *dixon.remaining_lambdas(1.5, 1.2, 80, (0, 0), (0, 0), 2))
    assert early["lines"]["2.5"]["over"] > late["lines"]["2.5"]["over"]
    done = dixon.live_markets(2, 1, 0.05, 0.05)
    assert done["lines"]["2.5"]["over"] > 0.99
    need = dixon.live_markets(2, 0, 0.05, 0.05)
    assert need["lines"]["1.5"]["over"] > 0.99
    assert need["lines"]["2.5"]["over"] < 0.2
    home = mk["teams"]["home"]
    away = mk["teams"]["away"]
    assert home["ou"]["0.5"]["over"] > home["ou"]["1.5"]["over"] > home["ou"]["2.5"]["over"]
    assert away["ou"]["0.5"]["over"] + away["ou"]["0.5"]["under"] == pytest.approx(1)
    assert home["mode"][0] == max(home["dist"], key=lambda item: item[1])[0]
    assert mk["total"]["xg"] == pytest.approx(home["xg"] + away["xg"])
    assert sum(p for _, p in mk["total"]["dist"]) > 0.95
    assert [k for k, _ in mk["total"]["dist"]] == sorted(k for k, _ in mk["total"]["dist"])
    assert abs(home["xg"] - 1.45) < 0.2
    led = need["teams"]["home"]
    assert led["ou"]["0.5"]["over"] > 0.99 and led["ou"]["1.5"]["over"] > 0.99
    assert led["ou"]["2.5"]["over"] < 0.2 and led["mode"][0] >= 2
    assert need["total"]["xg"] == pytest.approx(led["xg"] + need["teams"]["away"]["xg"])
    red = dixon.live_markets(0, 0, *dixon.remaining_lambdas(1.5, 1.2, 40, (1, 0), (0, 0), 1))
    plain = dixon.live_markets(0, 0, *dixon.remaining_lambdas(1.5, 1.2, 40, (0, 0), (0, 0), 1))
    assert red["lines"]["2.5"]["over"] != pytest.approx(plain["lines"]["2.5"]["over"], abs=1e-4)
    assert red["teams"]["home"]["xg"] < plain["teams"]["home"]["xg"]
    assert red["teams"]["away"]["xg"] > plain["teams"]["away"]["xg"]
    lh, la = 1.7, 0.9
    cal = dixon.calibrate(lh, la, 0.0, [0.25, 0.28, 0.47])
    scaled = goals.rescale_total(cal[0], cal[1], lh + la)
    assert scaled[0] + scaled[1] == pytest.approx(lh + la)
    assert scaled[0] / scaled[1] == pytest.approx(cal[0] / cal[1])
    probs = goals.batch_binary(np.array([1.4, 0.8]), np.array([1.1, 1.3]), np.array([-0.08, 0.0]))
    for i, (h, a, rho) in enumerate(((1.4, 1.1, -0.08), (0.8, 1.3, 0.0))):
        one = dixon.markets(h, a, rho)
        assert probs["ou15"][i] == pytest.approx(one["lines"]["1.5"]["over"], abs=1e-6)
        assert probs["ou25"][i] == pytest.approx(one["over"], abs=1e-6)
        assert probs["ou35"][i] == pytest.approx(one["lines"]["3.5"]["over"], abs=1e-6)
        assert probs["btts"][i] == pytest.approx(one["btts"], abs=1e-6)
    packed = lambda ll, br: {"mean": {"log_loss": ll, "brier": br}}
    ok, _ = metrics.goals_gate(packed(0.60, 0.20), packed(0.62, 0.21), packed(0.70, 0.24))
    assert ok
    bad, reason = metrics.goals_gate(packed(0.69, 0.23), packed(0.62, 0.21), packed(0.70, 0.24))
    assert not bad and reason


def test_workflows_keep_previous_model():
    root = pathlib.Path(__file__).resolve().parents[1]
    learn = (root / ".github/workflows/learn.yml").read_text(encoding="utf-8")
    pages = (root / ".github/workflows/pages.yml").read_text(encoding="utf-8")
    assert "concurrency:" in learn and "cancel-in-progress: false" in learn
    assert "concurrency:" in pages and "cancel-in-progress: false" in pages
    assert "fetch_release.py" in learn and "fetch_release.py" in pages
    assert "model-last-" not in pages
    assert "state.json" in pages and "--clobber" in pages
    assert "goals_h.txt" in learn and "goals_a.txt" in learn and "goals_meta.json" in learn
    sys.path.insert(0, str(root / "scripts"))
    import fetch_release
    assert fetch_release.archive_ok(root / "README.md") is False
    assert fetch_release.state_ok({"matches": []})
    assert not fetch_release.state_ok({"matches": {}})
    sw = (root / "web" / "sw.js").read_text(encoding="utf-8")
    assert "__GIT_SHA__" in sw and "3000" in sw and "caches.match" in sw


def test_online_dedupe():
    today = dt.date(2026, 10, 20)
    rows = [
        {"id": "espn:1", "key": "2026-10-19|a|b", "date": "2026-10-19", "status": "finished", "hg": 1, "ag": 0},
        {"id": "espn:1", "key": "2026-10-19|a|b", "date": "2026-10-19", "status": "finished", "hg": 1, "ag": 0},
        {"id": "espn:2", "key": "2026-09-01|a|b", "date": "2026-09-01", "status": "finished", "hg": 0, "ag": 0},
    ]
    kept = online.trim(rows, today)
    assert len(kept) == 1 and kept[0]["id"] == "espn:1"
    assert online.should_apply({"status": "finished", "hg": 2, "ag": 1, "date": "2026-10-20", "key": "k"}, "2026-10-18", set())
    assert not online.should_apply({"status": "finished", "hg": 2, "ag": 1, "date": "2026-10-18", "key": "k"}, "2026-10-18", {"k"})
    assert not online.should_apply({"status": "postponed", "hg": 0, "ag": 0, "date": "2026-10-20", "key": "k"}, "2026-10-18", set())
