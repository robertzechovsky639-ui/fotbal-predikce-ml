import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import competitions


def test_panama_reserves_are_not_european_cups():
    row = competitions.classify({
        "src": "s365", "competition_id": 8124, "country_name": "Panama",
        "home": "Herrera II", "away": "CD Universitario II",
    })
    assert row["region"] == "other"
    assert row["country"] == "pan"
    assert row["country_name"] == "Panama"
    assert row["segment"] == "reserve"
    assert row["cup"] is False
    assert "reserve" in row["tags"]
    stored = competitions.classify_stored({
        "league": "s365.8124", "region": "europe_cups", "country": "per",
        "country_raw": "Panama",
        "league_name": "Liga Prom - Apertura - Western Conference - North Zone",
        "teams": [{"name": "Herrera II"}, {"name": "CD Universitario II"}],
    })
    assert stored["region"] == "other"
    assert stored["country"] == "pan"
    assert stored["segment"] == "reserve"


def test_ncaa_conference_is_usa_college():
    row = competitions.classify({
        "src": "sofa", "tournament_id": 36031, "tournament_slug": "ncaa-division-iii",
        "country_name": "USA", "home": "Augsburg", "away": "Bethany Lutheran",
    })
    assert row["region"] == "other"
    assert row["country"] == "usa"
    assert row["segment"] == "college"
    assert row["cup"] is False


def test_only_listed_uefa_ids_are_european_cups():
    for spec in (
        {"src": "s365", "competition_id": 572, "country_name": "Belgium"},
        {"src": "s365", "competition_id": 573},
        {"src": "s365", "competition_id": 7685, "country_name": "Europe"},
        {"src": "s365", "competition_id": 332},
        {"src": "s365", "competition_id": 596},
        {"src": "s365", "competition_id": 472},
        {"src": "sofa", "tournament_id": 7, "country_name": "Europe"},
        {"src": "sofa", "tournament_id": 679},
        {"src": "sofa", "tournament_id": 17015},
        {"src": "sofa", "tournament_id": 465},
        {"src": "espn", "slug": "uefa.champions"},
        {"src": "espn", "slug": "uefa.champions_qual"},
        {"src": "espn", "slug": "uefa.europa"},
        {"src": "espn", "slug": "uefa.europa_qual"},
        {"src": "espn", "slug": "uefa.europa.conf"},
        {"src": "espn", "slug": "uefa.europa.conf_qual"},
        {"src": "espn", "slug": "uefa.super_cup"},
    ):
        row = competitions.classify(spec)
        assert row["region"] == "europe_cups", spec
        assert row["cup"] is True
        assert row["country"] is None
    assert competitions.classify({"src": "espn", "slug": "uefa.euro"})["region"] == "international"
    assert competitions.classify({"src": "espn", "slug": "uefa.nations"})["region"] == "international"
    assert competitions.classify({"src": "espn", "slug": "uefa.euroq"})["region"] == "international"
    assert competitions.classify({"src": "s365", "competition_id": 6297, "country_name": "Europe"})["segment"] == "youth"
    assert competitions.classify({"src": "s365", "competition_id": 6297, "country_name": "Europe"})["region"] != "europe_cups"
    women = competitions.classify({"src": "s365", "competition_id": 6225, "country_name": "Europe"})
    assert women["segment"] == "women"
    assert women["region"] != "europe_cups"


def test_category_suffix_keeps_english_lower_leagues():
    row = competitions.classify({
        "src": "sofa", "tournament_id": 19275, "country_name": "England Amateur",
        "label": "Isthmian League, Division One North",
        "home": "Bowers & Pitsea", "away": "Redbridge FC",
    })
    assert row["region"] == "europe_lower"
    assert row["country"] == "eng"
    assert row["segment"] == "main"
    youth = competitions.classify({
        "src": "sofa", "country_name": "Brazil Amateur", "home": "Sharjah Brasil U12", "away": "Salto FC U12",
        "label": "U12 Paulista Cup - Grupo 8",
    })
    assert youth["region"] == "south_america"
    assert youth["country"] == "bra"
    assert youth["segment"] == "youth"
    nwsl = competitions.classify({"src": "s365", "competition_id": 5566, "country_name": "USA", "label": "NWSL"})
    assert nwsl["region"] == "other" and nwsl["country"] == "usa" and nwsl["segment"] == "women"
    ncaa = competitions.classify({
        "src": "sofa", "country_name": "USA", "label": "NCAA III, Upper Midwest Athletic Conference",
        "home": "Crown Polars", "away": "Martin Luther Knights",
    })
    assert ncaa["region"] == "other" and ncaa["segment"] == "college"
    assert competitions.classify({"src": "s365", "competition_id": 5799, "country_name": "Hong Kong"})["region"] == "asia"
    assert competitions.classify({"src": "sofa", "country_name": "International", "label": "IFCPF Men's World Cup, Knockout"})["region"] == "international"
    crc = competitions.classify({"src": "espn", "slug": "crc.1"})
    assert crc["region"] == "other" and crc["country"] == "crc" and crc["tier"] == 1
    assert competitions.classify({"src": "espn", "slug": "eng.1"})["region"] == "europe_top"
    assert competitions.classify({"src": "espn", "slug": "eng.2"}) == {
        **competitions.classify({"src": "espn", "slug": "eng.2"}),
        "region": "europe_lower", "tier": 2, "country": "eng",
    }
    assert competitions.classify({"src": "espn", "slug": "cze.1"})["region"] == "czech"
    assert competitions.classify({"src": "espn", "slug": "bel.1"})["region"] == "europe_lower"
    assert competitions.classify({"src": "espn", "slug": "usa.usl.1"})["tier"] is None
    unknown = competitions.classify({"src": "s365", "competition_id": 999999})
    assert unknown["region"] == "other"
    assert unknown["region"] not in {"europe_cups", "europe_lower"}
    assert competitions.classify({"src": "s365", "competition_id": 11, "country_name": "Algeria"})["region"] == "other"
    assert competitions.classify({"src": "s365", "competition_id": 12, "country_name": "Egypt"})["country"] == "egy"
    asia = competitions.classify({"src": "s365", "competition_id": 8135, "country_name": "Asia"})
    assert asia["region"] == "asia" and asia["cup"] is True
    assert competitions.classify({"src": "espn", "slug": "caf.champions"})["region"] == "other"
    assert competitions.classify({"src": "espn", "slug": "conmebol.libertadores"})["region"] == "south_america"
