import datetime as dt
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import export_static as ex


def test_public_goal_lines():
    item = {
        "id": "espn:1", "src": "espn", "league": "cze.1", "league_name": "Chance Liga",
        "region": "czech", "country": "cze", "ts": 1, "status": "upcoming",
        "minute": None, "period": None, "hg": None, "ag": None, "reds": [0, 0],
        "neutral": False, "cup": False, "home_name": "Sparta", "away_name": "Slavia", "odds": None,
    }
    pred = {
        "home_id": "club:cze:sparta", "away_id": "club:cze:slavia",
        "pred": [0.46, 0.27, 0.27], "lam": [1.42, 1.08], "rho": -0.03,
        "ou": {"over": 0.49, "under": 0.51, "lines": {
            "1.5": {"over": 0.71, "under": 0.29},
            "2.5": {"over": 0.49, "under": 0.51},
            "3.5": {"over": 0.24, "under": 0.76},
        }},
        "btts": 0.53, "exact": [("1-1", 0.12), ("1-0", 0.11)],
        "pred_low": False, "pred_note": None, "elo": [1600, 1590], "n": [40, 40],
    }
    pub = ex.public_match(item, pred)
    assert pub["xg"] == [1.42, 1.08]
    assert pub["ou"]["line"] == 2.5
    assert pub["ou"]["over"] == 0.49
    assert pub["ou"]["lines"]["1.5"]["over"] == 0.71
    assert pub["ou"]["lines"]["3.5"]["under"] == 0.76
    assert pub["exact"][0] == ["1-1", 0.12]


def test_sofa_payload_is_not_dropped():
    assert ex.sofa_events({"events": [{"id": 7}]}) == [{"id": 7}]
    assert ex.sofa_events({"events": None}) == []
    assert ex.sofa_events([{"id": 1}]) == [{"id": 1}]
    now = 1_000_000
    minute, period = ex.sofa_clock({
        "status": {"description": "2nd half"},
        "time": {"initial": 2700, "currentPeriodStartTimestamp": now - 120, "max": 5400, "extra": 540},
    }, "live", now=now)
    assert (minute, period) == (47, 2)
    assert ex.sofa_goals({"current": 1, "normaltime": 0}, "live") == 1
    assert ex.sofa_goals({"current": 2, "normaltime": 1}, "finished") == 2
    assert ex.sofa_regulation({"current": 2, "normaltime": 1}, "finished") == 1
    text = (ROOT / "web" / "sw.js").read_text(encoding="utf-8")
    assert ex.git_sha()
    assert "fotbal-abc123def456" in text.replace("__GIT_SHA__", "abc123def456")


def test_365_inverted_home_is_swapped():
    game = {
        "isHomeAwayInverted": True,
        "homeCompetitor": {"name": "Away Side", "score": 0},
        "awayCompetitor": {"name": "Home Side", "score": 2},
    }
    home, away = ex.competitors_365(game)
    assert home["name"] == "Home Side" and away["name"] == "Away Side"
    assert home["score"] == 2 and away["score"] == 0
    plain = {"homeCompetitor": {"name": "A"}, "awayCompetitor": {"name": "B"}}
    assert ex.competitors_365(plain)[0]["name"] == "A"


def test_flipped_sources_merge_without_swapping_score():
    ts = int(dt.datetime(2026, 10, 20, 18, 0, tzinfo=dt.timezone.utc).timestamp())
    espn = {
        "ts": ts, "home_name": "Arsenal", "away_name": "Chelsea", "src": "espn",
        "status": "live", "hg": 1, "ag": 0, "reds": [0, 1], "minute": 50, "odds": None,
    }
    sofa = {
        "ts": ts, "home_name": "Chelsea", "away_name": "Arsenal", "src": "sofa",
        "status": "live", "hg": 0, "ag": 1, "reds": [1, 0], "minute": 55,
        "odds": {"h": 3.2, "d": 3.4, "a": 2.1},
    }
    merged = ex.merge([sofa, espn])
    assert len(merged) == 1
    row = merged[0]
    assert row["home_name"] == "Arsenal" and row["away_name"] == "Chelsea"
    assert row["hg"] == 1 and row["ag"] == 0
    assert row["reds"] == [0, 1]
