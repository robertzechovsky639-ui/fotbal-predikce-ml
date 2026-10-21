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
        "teams_goals": {
            "home": {"xg": 1.41, "ou": {"0.5": {"over": 0.76, "under": 0.24}, "1.5": {"over": 0.42, "under": 0.58}, "2.5": {"over": 0.18, "under": 0.82}}, "mode": [1, 0.35], "dist": [[0, 0.24], [1, 0.35], [2, 0.24]]},
            "away": {"xg": 1.07, "ou": {"0.5": {"over": 0.66, "under": 0.34}, "1.5": {"over": 0.31, "under": 0.69}, "2.5": {"over": 0.11, "under": 0.89}}, "mode": [1, 0.36], "dist": [[0, 0.34], [1, 0.36]]},
        },
        "total_goals": {"xg": 2.48, "mode": [2, 0.23], "dist": [[1, 0.18], [2, 0.23], [3, 0.2]], "lines": {"1.5": {"over": 0.71, "under": 0.29}, "2.5": {"over": 0.49, "under": 0.51}, "3.5": {"over": 0.24, "under": 0.76}}},
        "pred_low": False, "pred_note": None, "elo": [1600, 1590], "n": [40, 40],
    }
    pub = ex.public_match(item, pred)
    assert pub["xg"] == [1.41, 1.07]
    assert pub["ou"]["line"] == 2.5
    assert pub["ou"]["over"] == 0.49
    assert pub["ou"]["lines"]["1.5"]["over"] == 0.71
    assert pub["ou"]["lines"]["3.5"]["under"] == 0.76
    assert pub["exact"][0] == ["1-1", 0.12]
    assert pub["teams_goals"]["home"]["ou"]["0.5"]["over"] == 0.76
    assert pub["teams_goals"]["away"]["mode"] == [1, 0.36]
    assert pub["total_goals"]["dist"][1] == [2, 0.23]
    assert pub["total_goals"]["lines"]["2.5"]["over"] == 0.49


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
    et_min, et_period = ex.sofa_clock({
        "status": {"description": "Extra time"},
        "time": {"initial": 5400, "currentPeriodStartTimestamp": now - 180},
    }, "live", now=now)
    assert (et_min, et_period) == (93, 3)
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
    assert row["minute"] == 55
    assert row["odds"]["h"] == 2.1 and row["odds"]["a"] == 3.2
    assert row["src"] == "espn"


def _row(src, home, away, **extra):
    ts = int(dt.datetime(2026, 10, 20, 18, 0, tzinfo=dt.timezone.utc).timestamp())
    item = {
        "ts": ts, "home_name": home, "away_name": away, "src": src, "id": src + ":" + home,
        "status": "live", "hg": 0, "ag": 0, "minute": 10, "segment": "main", "odds": None, "reds": [0, 0],
    }
    item.update(extra)
    return item


def test_cross_source_aliases_keep_the_further_score():
    espn = _row("espn", "Guadalajara", "Necaxa", hg=0, ag=0, minute=11)
    other = _row("s365", "Chivas", "Necaxa", hg=1, ag=0, minute=30)
    merged = ex.merge([espn, other])
    assert len(merged) == 1
    assert merged[0]["src"] == "espn"
    assert merged[0]["home_name"] == "Guadalajara"
    assert merged[0]["hg"] == 1 and merged[0]["ag"] == 0 and merged[0]["minute"] == 30
    assert ex.merge([
        espn,
        _row("s365", "Deportivo Guadalajara", "Necaxa", hg=3, ag=0, minute=80),
    ]).__len__() == 2
    women = _row("s365", "Guadalajara Chivas (W)", "Necaxa (W)", segment="women", ts=espn["ts"] + 10740, status="upcoming")
    assert len(ex.merge([espn, women])) == 2
    assert len(ex.merge([espn, _row("s365", "Guadalajara Chivas (W)", "Necaxa (W)", ts=espn["ts"] + 10740)])) == 2


def test_loose_names_merge_and_stale_full_time_does_not_hide_a_goal():
    assert len(ex.merge([
        _row("espn", "Blackpool", "Milton Keynes Dons", status="finished", minute=98, hg=2, ag=0),
        _row("s365", "Blackpool", "MK Dons", status="finished", minute=None, hg=2, ag=0),
    ])) == 1
    assert len(ex.merge([
        _row("espn", "Montevideo City Torque", "Atlético-MG"),
        _row("s365", "Montevideo City Torque", "Atlético Mineiro"),
    ])) == 1
    assert len(ex.merge([
        _row("espn", "Sanfrecce Hiroshima", "Kyoto Sanga"),
        _row("s365", "Hiroshima Sanfrecce", "Kyoto"),
    ])) == 1
    assert len(ex.merge([
        _row("espn", "Avispa Fukuoka", "Fagiano Okayama"),
        _row("s365", "Fukuoka", "Okayama"),
    ])) == 1
    live = _row("sofa", "Criciúma U20", "Flamengo U20", segment="youth", status="live", minute=91, hg=0, ag=2)
    bare = _row("s365", "Criciúma/Sc Youth", "Flamengo/RJ Youth", segment="youth", status="finished", minute=None, hg=0, ag=2)
    folded = ex.merge([bare, live])
    assert len(folded) == 1
    assert folded[0]["status"] == "live" and folded[0]["minute"] == 91
    assert folded[0]["hg"] == 0 and folded[0]["ag"] == 2
    ahead = _row("s365", "Criciúma/Sc Youth", "Flamengo/RJ Youth", segment="youth", status="finished", minute=None, hg=0, ag=3)
    taken = ex.merge([live, ahead])
    assert taken[0]["status"] == "finished" and taken[0]["ag"] == 3
    hidden = ex.merge([
        _row("espn", "Blackpool", "MK Dons", status="finished", minute=None, hg=0, ag=0),
        _row("s365", "Blackpool", "Milton Keynes Dons", status="live", minute=50, hg=1, ag=0),
    ])
    assert hidden[0]["hg"] == 1 and hidden[0]["status"] == "live"
    clock = ex.merge([
        _row("espn", "Avispa Fukuoka", "Okayama", minute=70, hg=1, ag=0),
        _row("s365", "Fukuoka", "Okayama", minute=40, hg=2, ag=0),
    ])
    assert clock[0]["hg"] == 2 and clock[0]["minute"] == 70
    split = ex.merge([
        _row("espn", "Manchester United", "Chelsea"),
        _row("s365", "Manchester City", "Chelsea"),
    ])
    assert len(split) == 2
    hapoel = ex.merge([
        _row("espn", "Hapoel Ra'anana", "Maccabi Haifa"),
        _row("s365", "Hapoel Afula", "Maccabi Haifa"),
    ])
    assert len(hapoel) == 2
    later = _row("s365", "Arsenal", "Chelsea", ts=_row("espn", "Arsenal", "Chelsea")["ts"] + 3 * 3600, hg=1, ag=0)
    assert len(ex.merge([_row("espn", "Arsenal", "Chelsea", hg=0, ag=0), later])) == 2
    swapped = ex.merge([
        _row("espn", "Arsenal", "Chelsea", minute=40, hg=1, ag=0),
        _row("s365", "Arsenal", "Chelsea", minute=70, hg=0, ag=1),
    ])
    assert swapped[0]["hg"] == 0 and swapped[0]["ag"] == 1 and swapped[0]["minute"] == 70
    postponed = ex.merge([
        _row("espn", "Universidad de Chile", "Antofagasta", status="upcoming", hg=None, ag=None, minute=None),
        _row("s365", "Universidad de Chile", "Deportes Antofagasta", status="postponed", hg=None, ag=None, minute=None),
    ])
    assert len(postponed) == 1 and postponed[0]["status"] == "postponed"
    still_live = ex.merge([
        _row("espn", "Arsenal", "Chelsea", status="live", minute=20, hg=1, ag=0),
        _row("s365", "Arsenal", "Chelsea", status="postponed", hg=None, ag=None, minute=None),
    ])
    assert still_live[0]["status"] == "live" and still_live[0]["hg"] == 1
