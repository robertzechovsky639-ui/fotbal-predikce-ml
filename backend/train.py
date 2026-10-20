"""Chronologický trénink: Elo, Dixon-Coles, LightGBM. Metriky jsou z holdoutu před finálním refitem."""
import datetime as dt
import json
import math
import pathlib
import sys

import lightgbm as lgb
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import dataset
import dixon
import elo
import features
import goals
import metrics

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL = ROOT / "data" / "model"
HOLDOUT = dt.date(2025, 7, 1)
DC_ASOF = dt.date(2023, 7, 1)
VAL_DAYS = 120

NOTES = [
    "ClubElo API (clubelo.com) vrací 502 / timeout a stránka s datem je jen aktuální žebříček, ne historie. Vlastní Elo je jediný rating, ať neunikne budoucnost.",
    "Soubory football-data.co.uk/new mají jen closing kurzy (PSCH, B365CH). Ty se do modelu neberou; zápasy z nich mají odds_missing.",
    "Kódy KOR, KSA, CHI a COL na football-data.co.uk přesměrovávají na jinou zemi. Stahování je zahodí. Korea proto začíná jen s priorou ligy a výsledky ze živých zdrojů.",
    "Česká historie v openfootball je jen několik sezón (ne od 1993). Nižší jistota, dokud se nenasbírají výsledky ze živých zdrojů.",
    "Saudská Arábie v openfootball je hlavně 2024/25. J1, Čína, Brazílie a Argentina jedou z football-data extra CSV.",
    "xG jen z Understatu (Premier League, La Liga, Bundesliga, Serie A, Ligue 1). Jinde je příznak prázdný.",
    "1X2 je po 90 minutách. Prodloužení a penalty se nepočítají jako gól navíc.",
    "Publikované metriky jsou kandidát natrénovaný jen do 2025-07-01. Když brána projde, ostrý model se dofituje na všech datech.",
]


def _y(match):
    if match["hg"] > match["ag"]:
        return 0
    if match["hg"] == match["ag"]:
        return 1
    return 2


def elo_lambdas(elo_h, elo_a, neutral, params):
    ha = 0.0 if neutral else float(params["ha"])
    coef = float(params["coef"])
    base_h = 1.30 if neutral else float(params.get("base_h", 1.48))
    base_a = 1.30 if neutral else float(params.get("base_a", 1.18))
    diff = (elo_h + ha - elo_a) / 400.0
    lh = math.exp(math.log(base_h) + coef * diff)
    la = math.exp(math.log(base_a) - coef * diff)
    return min(4.8, max(0.15, lh)), min(4.8, max(0.15, la))


def elo_probs_from(elo_h, elo_a, neutral, params):
    lh, la = elo_lambdas(elo_h, elo_a, neutral, params)
    return dixon.markets(lh, la, 0.0)["p"], lh, la


def _dc_vec(models, league_id, home_id, away_id, neutral):
    model = models.get(league_id) if models else None
    got = dixon.lambdas_from_model(model, home_id, away_id, neutral)
    if not got:
        return None
    lh, la = got
    probs = dixon.markets(lh, la, model["rho"])["p"]
    return [lh, la, probs[0], probs[1], probs[2]]


def _build_matrix(rows, models_for):
    x = np.empty((len(rows), len(features.FEATURES)), dtype=np.float64)
    for i, row in enumerate(rows):
        dc = models_for(row)
        values = features.row_from(row["sh"], row["sa"], row["h2h"], dc, row["elo_exp"], row["imp"], row["cup"])
        x[i] = values
    return x


def _weights(dates, end):
    out = np.empty(len(dates), dtype=np.float64)
    for i, date in enumerate(dates):
        out[i] = 0.5 ** ((end - date).days / 365.25 / 4.0)
    return out


def _tune_elo(rows):
    pool = [r for r in rows if r["date"] >= HOLDOUT - dt.timedelta(days=900)]
    rng = np.random.default_rng(7)
    if len(pool) > 15000:
        pick = rng.choice(len(pool), 15000, replace=False)
        pool = [pool[i] for i in pick]
    y = [_y_of(r) for r in pool]
    best = None
    best_ll = 1e9
    for ha in (50, 70, 90):
        for coef in (0.35, 0.55, 0.75):
            params = {"ha": ha, "coef": coef, "base_h": 1.48, "base_a": 1.18}
            probs = []
            for row in pool:
                p, _, _ = elo_probs_from(row["sh"]["elo"], row["sa"]["elo"], row["neutral"], params)
                probs.append(p)
            ll = metrics.log_loss(y, probs)
            print(f"  elo λ ha={ha} coef={coef} logloss={ll:.4f} n={len(pool)}")
            if ll < best_ll:
                best_ll = ll
                best = params
    return best


def _y_of(row):
    return row["y"]


def _blend_w(y, lgb_p, elo_p):
    best_w, best_ll = 0.0, 1e9
    for step in range(0, 11):
        w = step / 10.0
        mixed = [[w * a[i] + (1 - w) * b[i] for i in range(3)] for a, b in zip(lgb_p, elo_p)]
        ll = metrics.log_loss(y, mixed)
        if ll < best_ll:
            best_ll, best_w = ll, w
    return best_w


def _mix(lgb_p, elo_p, w):
    return [[w * a[i] + (1 - w) * b[i] for i in range(3)] for a, b in zip(lgb_p, elo_p)]


def _lgb_params():
    return {
        "objective": "multiclass",
        "num_class": 3,
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_data_in_leaf": 40,
        "feature_fraction": 0.9,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "lambda_l2": 2.0,
        "seed": 7,
        "num_threads": 4,
        "deterministic": True,
        "force_row_wise": True,
        "verbosity": -1,
    }


def _fit_lgb(x, y, w):
    data = lgb.Dataset(x, label=np.array(y), weight=w, feature_name=features.FEATURES, free_raw_data=False)
    return lgb.train(_lgb_params(), data, num_boost_round=160)


def _region_pack(rows, probs, regions):
    out = {}
    for region in regions:
        idx = [i for i, row in enumerate(rows) if row["region"] == region]
        if not idx:
            continue
        y = [rows[i]["y"] for i in idx]
        p = [probs[i] for i in idx]
        out[region] = metrics.pack(y, p)
    return out


def main():
    MODEL.mkdir(parents=True, exist_ok=True)
    prev_path = MODEL / "metrics.json"
    previous = None
    if prev_path.exists():
        try:
            previous = json.loads(prev_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = None
    prev_test = (previous or {}).get("test", {}).get("blend")
    gbm_backup = (MODEL / "gbm.txt").read_bytes() if (MODEL / "gbm.txt").exists() else None
    dc_backup = (MODEL / "dc.json").read_bytes() if (MODEL / "dc.json").exists() else None

    matches = dataset.load_all()
    if not matches:
        print("žádná data")
        return 1
    cov = dataset.coverage(matches)
    state = elo.new_state()
    rows = []
    league_counts = {}
    for match in matches:
        snap = elo.apply_result(state, match, want_snap=True)
        if snap is False:
            continue
        league_counts[match["league_id"]] = league_counts.get(match["league_id"], 0) + 1
        if match["pool"] != "club":
            continue
        sh, sa, h2h = snap
        nat = str(match["home_id"]).startswith("nat:")
        exp = elo.expected(sh["elo"], sa["elo"], 0.0 if match.get("neutral") else (elo.HA_NAT if nat else elo.HA_CLUB))
        rows.append({
            "date": match["date"], "region": match["region"], "league_id": match["league_id"],
            "home_id": match["home_id"], "away_id": match["away_id"], "neutral": bool(match.get("neutral")),
            "cup": bool(match.get("cup")), "imp": match.get("imp"), "y": _y(match),
            "hg": match["hg"], "ag": match["ag"],
            "sh": sh, "sa": sa, "h2h": h2h, "elo_exp": exp,
        })
    print("klubových řádků", len(rows))
    max_date = max(m["date"] for m in matches)
    recent_from = max_date - dt.timedelta(days=21)
    recent_keys = [m["key"] for m in matches if m["date"] >= recent_from]

    print("Dixon-Coles k 2023-07-01")
    dc_2023 = dixon.fit_leagues(matches, DC_ASOF)
    print("Dixon-Coles k 2025-07-01")
    dc_hold = dixon.fit_leagues(matches, HOLDOUT)
    print("Dixon-Coles ostrý (všechna data)")
    dc_full = dixon.fit_leagues(matches, max_date + dt.timedelta(days=1))

    def honest(row):
        if row["date"] < DC_ASOF:
            return None
        if row["date"] < HOLDOUT:
            return _dc_vec(dc_2023, row["league_id"], row["home_id"], row["away_id"], row["neutral"])
        return _dc_vec(dc_hold, row["league_id"], row["home_id"], row["away_id"], row["neutral"])

    print("ladím Elo → Poisson na tréninku")
    train_rows = [r for r in rows if r["date"] < HOLDOUT]
    elo_params = _tune_elo(train_rows)
    print("zvolené Elo λ", elo_params)

    x_all = _build_matrix(rows, honest)
    y_all = [r["y"] for r in rows]
    train_idx = [i for i, r in enumerate(rows) if r["date"] < HOLDOUT]
    val_from = HOLDOUT - dt.timedelta(days=VAL_DAYS)
    val_idx = [i for i in train_idx if rows[i]["date"] >= val_from]
    fit_idx = [i for i in train_idx if rows[i]["date"] < val_from]
    test_idx = [i for i, r in enumerate(rows) if r["date"] >= HOLDOUT]
    print(f"fit {len(fit_idx)} val {len(val_idx)} test {len(test_idx)}")

    def take(idx):
        return x_all[idx], [y_all[i] for i in idx], [rows[i]["date"] for i in idx]

    x_fit, y_fit, d_fit = take(fit_idx)
    booster = _fit_lgb(x_fit, y_fit, _weights(d_fit, val_from))
    x_val, y_val, _ = take(val_idx)
    lgb_val = booster.predict(x_val).tolist()
    elo_val = [elo_probs_from(rows[i]["sh"]["elo"], rows[i]["sa"]["elo"], rows[i]["neutral"], elo_params)[0] for i in val_idx]
    blend_w = _blend_w(y_val, lgb_val, elo_val)
    print("váha LightGBM", blend_w, "val logloss", metrics.log_loss(y_val, _mix(lgb_val, elo_val, blend_w)))

    # kandidát na celém tréninku (val je uvnitř), váha už je vybraná
    x_tr, y_tr, d_tr = take(train_idx)
    candidate = _fit_lgb(x_tr, y_tr, _weights(d_tr, HOLDOUT))
    x_te, y_te, _ = take(test_idx)
    lgb_te = candidate.predict(x_te).tolist()
    elo_te = [elo_probs_from(rows[i]["sh"]["elo"], rows[i]["sa"]["elo"], rows[i]["neutral"], elo_params)[0] for i in test_idx]
    blend_te = _mix(lgb_te, elo_te, blend_w)
    freq = [0.0, 0.0, 0.0]
    for value in y_tr:
        freq[value] += 1
    freq = [v / max(1, len(y_tr)) for v in freq]
    base_te = [freq for _ in y_te]
    test_rows = [rows[i] for i in test_idx]
    regions = ["europe_top", "europe_lower", "czech", "europe_cups", "asia", "south_america", "other"]
    by_region = {}
    for region in regions:
        idx = [j for j, row in enumerate(test_rows) if row["region"] == region]
        if not idx:
            by_region[region] = None
            continue
        yy = [y_te[j] for j in idx]
        by_region[region] = {
            "blend": metrics.pack(yy, [blend_te[j] for j in idx]),
            "lightgbm": metrics.pack(yy, [lgb_te[j] for j in idx]),
            "elo": metrics.pack(yy, [elo_te[j] for j in idx]),
            "baseline": metrics.pack(yy, [base_te[j] for j in idx]),
        }
    dc_idx = [j for j, i in enumerate(test_idx) if honest(rows[i])]
    dix = None
    if dc_idx:
        dix_y = [y_te[j] for j in dc_idx]
        dix_p = []
        for j in dc_idx:
            vec = honest(rows[test_idx[j]])
            dix_p.append(vec[2:5])
        dix = metrics.pack(dix_y, dix_p)

    # reprezentace: jen Elo proti frekvenci, ze stejného období
    nat_y, nat_p = [], []
    # znovu neprocházíme; mezinárodní zápasy nejsou v rows. Dopočítáme z matches podruhé by bylo drahé.
    # Elo očekávání jsme neukládali. Projdeme matches se stavem, který už je po všech zápasech – to by unikalo.
    # Proto mezinárodní metriky počítáme jen tam, kde je uložený snap... nejsou. Dopočet níže přes druhý průchod
    # s want_snap je rychlý (už máme data v paměti).
    nat_state = elo.new_state()
    nat_train_y = []
    for match in matches:
        if match["region"] != "international":
            elo.apply_result(nat_state, match, want_snap=False)
            continue
        snap = elo.apply_result(nat_state, match, want_snap=True)
        if snap is False:
            continue
        sh, sa, _h2h = snap
        if match["date"] < HOLDOUT:
            nat_train_y.append(_y(match))
            continue
        probs, _, _ = elo_probs_from(sh["elo"], sa["elo"], bool(match.get("neutral")), elo_params)
        nat_y.append(_y(match))
        nat_p.append(probs)
    if nat_train_y:
        nf = [0.0, 0.0, 0.0]
        for value in nat_train_y:
            nf[value] += 1
        nf = [v / len(nat_train_y) for v in nf]
    else:
        nf = freq
    international = {
        "elo": metrics.pack(nat_y, nat_p) if nat_y else None,
        "baseline": metrics.pack(nat_y, [nf for _ in nat_y]) if nat_y else None,
    }

    report = {
        "blend": metrics.pack(y_te, blend_te),
        "lightgbm": metrics.pack(y_te, lgb_te),
        "elo": metrics.pack(y_te, elo_te),
        "baseline": metrics.pack(y_te, base_te),
        "dixon": dix,
    }
    for name, pack in report.items():
        if not pack:
            continue
        print(f"TEST {name}: n={pack['n']} acc={pack['accuracy']:.4f} ll={pack['log_loss']:.4f} rps={pack['rps']:.4f}")
    ok, reason = metrics.gate(report["blend"], report["baseline"], report["elo"], prev_test)
    print("brána", ok, reason)

    print("gólový model (Dixon-Coles/Poisson + LightGBM)")
    goals_report = goals.run(rows, dc_2023, dc_hold, elo_params, MODEL, (previous or {}).get("goals"))

    gain = candidate.feature_importance(importance_type="gain")
    total = float(gain.sum()) or 1.0
    importance = {features.FEATURES[i]: round(float(gain[i]) / total, 4) for i in range(len(features.FEATURES))}
    blob = {
        "split": "trénink < 2025-07-01, test ≥ 2025-07-01 (kandidát; ostrý refit není v těchto číslech)",
        "test": report,
        "by_region": by_region,
        "international": international,
        "coverage": cov,
        "gate": {"ok": bool(ok), "reason": reason},
        "history": list((previous or {}).get("history") or []),
        "elo_params": elo_params,
        "blend_w": blend_w,
        "features": features.FEATURES,
        "importance": importance,
        "notes": NOTES,
        "trained_at": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "data_from": min(m["date"] for m in matches).isoformat(),
        "data_to": max_date.isoformat(),
        "n_matches": len(matches),
        "n_club": len(rows),
        "train_rows": len(train_idx),
        "test_rows": len(test_idx),
        "gbm_rounds": 160,
        "published_model": bool(ok),
        "goals": goals_report,
    }
    blob["history"].append({
        "at": blob["trained_at"],
        "holdout_n": len(test_idx),
        "candidate": {"log_loss": report["blend"]["log_loss"], "rps": report["blend"]["rps"]},
        "published": bool(ok),
        "reason": reason,
    })
    prev_path.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")

    elo_blob = elo.dump_state(state, max_date.isoformat(), recent_keys, elo_params)
    elo_blob["league_counts"] = league_counts
    elo_blob["blend_w"] = blend_w
    (MODEL / "elo_state.json").write_text(json.dumps(elo_blob, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    if ok:
        print("ostrý LightGBM na všech klubových řádcích")
        prod = _fit_lgb(x_all, y_all, _weights([r["date"] for r in rows], max_date))
        prod.save_model(str(MODEL / "gbm.txt"))
        (MODEL / "dc.json").write_text(json.dumps(dc_full, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        return 0
    if gbm_backup and dc_backup:
        (MODEL / "gbm.txt").write_bytes(gbm_backup)
        (MODEL / "dc.json").write_bytes(dc_backup)
        print("brána neprošla, ponechán předchozí model, Elo se aktualizovalo")
        return 0
    print("brána neprošla a není co ponechat")
    return 1


if __name__ == "__main__":
    sys.exit(main())
