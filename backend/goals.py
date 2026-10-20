"""Očekávané góly: Dixon-Coles/Elo Poisson, upřesněné dvěma poissonovskými LightGBM.

Brána porovnává log loss a Brier trhů Over/Under 1.5, 2.5, 3.5 a BTTS
proti frekvenci z tréninku a proti lambdám před modelem. Když neprojde,
stromy se nepublikují a predikce zůstane u Poissonu.
"""
import datetime as dt
import json
import pathlib
import sys

import lightgbm as lgb
import numpy as np
from scipy.stats import poisson

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import dataset
import dixon
import elo
import features
import metrics
import train

GOAL_FEATURES = features.FEATURES + ["base_lh", "base_la"]
MARKETS = ("ou15", "ou25", "ou35", "btts")
MODEL = pathlib.Path(__file__).resolve().parents[1] / "data" / "model"
NOTE = (
    "Góly: základ je Dixon-Coles, kde oba týmy v ligovém modelu jsou, jinak Elo Poisson. "
    "LightGBM (poisson) upřesní lambdy; váha je z posledních 120 dní tréninku. "
    "1X2 se nemění. Součet očekávaných gólů zůstává ze směsi, kalibrace jen rozdělí domácí a hosty. "
    "Desetiminutový export přehraje dohrané zápasy ze state.json do Elo před výpočtem. "
    "Stromy se mění až denním učením."
)


def rescale_total(lh, la, total):
    """Stejný poměr jako po kalibraci 1X2, součet vrátí na gólový model."""
    total = max(float(total), 0.1)
    acc = float(lh) + float(la)
    if acc <= 1e-9:
        return total / 2.0, total / 2.0
    scale = total / acc
    return float(lh) * scale, float(la) * scale


def _clip_lam(value):
    return float(min(6.5, max(0.05, value)))


def blend_lambdas(base_h, base_a, pred_h, pred_a, weight):
    w = float(weight or 0.0)
    return (
        _clip_lam(w * float(pred_h) + (1.0 - w) * float(base_h)),
        _clip_lam(w * float(pred_a) + (1.0 - w) * float(base_a)),
    )


def dc_base(row, dc_2023, dc_hold):
    """Poctivé lambdy: před 2023-07-01 nic, do holdoutu model k 2023, potom model k 2025-07-01."""
    if row["date"] < train.DC_ASOF:
        return None
    models = dc_2023 if row["date"] < train.HOLDOUT else dc_hold
    model = (models or {}).get(row["league_id"])
    got = dixon.lambdas_from_model(model, row["home_id"], row["away_id"], row["neutral"])
    if not got:
        return None
    return float(got[0]), float(got[1]), float(model["rho"])


def base_lambda(row, dc_2023, dc_hold, elo_params):
    got = dc_base(row, dc_2023, dc_hold)
    if got:
        return got
    lh, la = train.elo_lambdas(row["sh"]["elo"], row["sa"]["elo"], row["neutral"], elo_params)
    return lh, la, 0.0


def feature_row(row, dc_vec, base_h, base_a, elo_params):
    exp = row.get("elo_exp")
    if exp is None:
        exp = elo.expected(row["sh"]["elo"], row["sa"]["elo"], 0.0 if row["neutral"] else elo.HA_CLUB)
    values = features.row_from(row["sh"], row["sa"], row["h2h"], dc_vec, exp, row.get("imp"), row.get("cup"))
    return values + [float(base_h), float(base_a)]


def dc_vec_of(row, dc_2023, dc_hold):
    got = dc_base(row, dc_2023, dc_hold)
    if not got:
        return None
    lh, la, rho = got
    probs = dixon.markets(lh, la, rho)["p"]
    return [lh, la, probs[0], probs[1], probs[2]]


def build_frame(rows, dc_2023, dc_hold, elo_params):
    x = np.empty((len(rows), len(GOAL_FEATURES)), dtype=np.float64)
    base = np.empty((len(rows), 2), dtype=np.float64)
    rho = np.empty(len(rows), dtype=np.float64)
    for i, row in enumerate(rows):
        lh, la, rr = base_lambda(row, dc_2023, dc_hold, elo_params)
        vec = dc_vec_of(row, dc_2023, dc_hold)
        x[i] = feature_row(row, vec, lh, la, elo_params)
        base[i, 0] = lh
        base[i, 1] = la
        rho[i] = rr
    return x, base, rho


def _pmf(lam, maxg=dixon.MAXG):
    ks = np.arange(0, maxg + 1)
    raw = poisson.pmf(ks, np.clip(lam, 0.05, 6.5)[:, None])
    out = np.array(raw, copy=True)
    out[:, -1] = np.maximum(0.0, 1.0 - out[:, :-1].sum(axis=1))
    return out


def batch_binary(lh, la, rho, maxg=dixon.MAXG):
    """Stejná matice jako dixon.score_matrix, po řádcích. Vrací P(over) a P(BTTS)."""
    lh = np.asarray(lh, dtype=np.float64)
    la = np.asarray(la, dtype=np.float64)
    rho = np.asarray(rho, dtype=np.float64)
    hs = _pmf(lh, maxg)
    aw = _pmf(la, maxg)
    mat = hs[:, :, None] * aw[:, None, :]
    nz = np.nonzero(rho)[0]
    if len(nz):
        r = rho[nz]
        hh = np.clip(lh[nz], 0.05, 6.5)
        aa = np.clip(la[nz], 0.05, 6.5)
        mat[nz, 0, 0] *= np.maximum(1e-8, 1.0 - hh * aa * r)
        mat[nz, 0, 1] *= np.maximum(1e-8, 1.0 + hh * r)
        mat[nz, 1, 0] *= np.maximum(1e-8, 1.0 + aa * r)
        mat[nz, 1, 1] *= np.maximum(1e-8, 1.0 - r)
    mat = np.clip(mat, 0, None)
    total = mat.sum(axis=(1, 2), keepdims=True)
    mat = np.divide(mat, np.where(total <= 0, 1.0, total))
    ii = np.arange(maxg + 1)[:, None]
    jj = np.arange(maxg + 1)[None, :]
    goals = ii + jj
    return {
        "ou15": (mat * (goals >= 2)).sum(axis=(1, 2)),
        "ou25": (mat * (goals >= 3)).sum(axis=(1, 2)),
        "ou35": (mat * (goals >= 4)).sum(axis=(1, 2)),
        "btts": mat[:, 1:, 1:].sum(axis=(1, 2)),
    }


def truth_of(rows):
    hg = np.array([int(r["hg"]) for r in rows], dtype=np.int16)
    ag = np.array([int(r["ag"]) for r in rows], dtype=np.int16)
    return {
        "ou15": (hg + ag >= 2).astype(np.float64),
        "ou25": (hg + ag >= 3).astype(np.float64),
        "ou35": (hg + ag >= 4).astype(np.float64),
        "btts": ((hg >= 1) & (ag >= 1)).astype(np.float64),
        "hg": hg.astype(np.float64),
        "ag": ag.astype(np.float64),
    }


def pack_probs(truth, probs):
    out = {}
    for name in MARKETS:
        out[name] = metrics.binary_pack(truth[name].tolist(), np.asarray(probs[name]).tolist())
    lls = [out[name]["log_loss"] for name in MARKETS]
    brs = [out[name]["brier"] for name in MARKETS]
    out["mean"] = {"n": int(len(truth["ou15"])), "log_loss": float(sum(lls) / len(lls)), "brier": float(sum(brs) / len(brs))}
    return out


def _mae(lh, la, truth):
    if len(truth["hg"]) == 0:
        return None
    return {
        "home": float(np.mean(np.abs(lh - truth["hg"]))),
        "away": float(np.mean(np.abs(la - truth["ag"]))),
        "total": float(np.mean(np.abs((lh + la) - (truth["hg"] + truth["ag"])))),
    }


def _lgb_params():
    return {
        "objective": "poisson",
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_data_in_leaf": 50,
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


def _fit_pair(x, yh, ya, w):
    params = _lgb_params()
    home = lgb.Dataset(x, label=yh, weight=w, feature_name=GOAL_FEATURES, free_raw_data=False)
    away = lgb.Dataset(x, label=ya, weight=w, feature_name=GOAL_FEATURES, free_raw_data=False)
    bh = lgb.train(params, home, num_boost_round=140)
    ba = lgb.train(params, away, num_boost_round=140)
    return bh, ba


def _predict_pair(bh, ba, x):
    return np.clip(bh.predict(x), 0.05, 6.5), np.clip(ba.predict(x), 0.05, 6.5)


def choose_weight(truth, base, pred_h, pred_a, rho):
    best_w, best_ll = 0.0, 1e9
    for step in range(0, 11):
        w = step / 10.0
        lh = w * pred_h + (1.0 - w) * base[:, 0]
        la = w * pred_a + (1.0 - w) * base[:, 1]
        probs = batch_binary(lh, la, rho)
        packed = pack_probs(truth, probs)
        ll = packed["mean"]["log_loss"]
        print(f"  góly váha {w:.1f} val logloss {ll:.4f} brier {packed['mean']['brier']:.4f}")
        if ll < best_ll - 1e-12:
            best_ll, best_w = ll, w
    return best_w


def _region_mean(rows, truth, probs):
    out = {}
    regions = ["europe_top", "europe_lower", "czech", "europe_cups", "asia", "south_america", "other"]
    for region in regions:
        idx = [i for i, row in enumerate(rows) if row["region"] == region]
        if len(idx) < 20:
            continue
        sub_t = {name: truth[name][idx] for name in list(MARKETS) + ["hg", "ag"]}
        sub_p = {name: np.asarray(probs[name])[idx] for name in MARKETS}
        packed = pack_probs(sub_t, sub_p)
        out[region] = {"n": len(idx), "log_loss": packed["mean"]["log_loss"], "brier": packed["mean"]["brier"]}
    return out


def _backup(path):
    path = pathlib.Path(path)
    return path.read_bytes() if path.exists() else None


def _restore(path, blob):
    path = pathlib.Path(path)
    if blob is None:
        if path.exists():
            path.unlink()
        return
    path.write_bytes(blob)


def run(rows, dc_2023, dc_hold, elo_params, model_dir, previous=None, patch_metrics=False):
    model_dir = pathlib.Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    paths = {name: model_dir / name for name in ("goals_h.txt", "goals_a.txt", "goals_meta.json")}
    backups = {name: _backup(path) for name, path in paths.items()}

    print("gólové příznaky", len(rows))
    x, base, rho = build_frame(rows, dc_2023, dc_hold, elo_params)
    truth_all = truth_of(rows)
    train_idx = np.array([i for i, r in enumerate(rows) if r["date"] < train.HOLDOUT])
    val_from = train.HOLDOUT - dt.timedelta(days=train.VAL_DAYS)
    fit_idx = np.array([i for i in train_idx if rows[i]["date"] < val_from])
    val_idx = np.array([i for i in train_idx if rows[i]["date"] >= val_from])
    test_idx = np.array([i for i, r in enumerate(rows) if r["date"] >= train.HOLDOUT])
    print(f"góly fit {len(fit_idx)} val {len(val_idx)} test {len(test_idx)}")
    if len(fit_idx) < 1000 or len(val_idx) < 100 or len(test_idx) < 100:
        report = {"published": False, "gate": {"ok": False, "reason": "málo řádků na gólový model"}, "note": NOTE}
        if patch_metrics:
            _patch(model_dir / "metrics.json", report)
        return report

    dates = [rows[i]["date"] for i in fit_idx]
    w_fit = train._weights(dates, val_from)
    y_h = truth_all["hg"]
    y_a = truth_all["ag"]
    booster_h, booster_a = _fit_pair(x[fit_idx], y_h[fit_idx], y_a[fit_idx], w_fit)
    pred_h, pred_a = _predict_pair(booster_h, booster_a, x[val_idx])
    val_truth = {name: truth_all[name][val_idx] for name in list(MARKETS) + ["hg", "ag"]}
    blend_w = choose_weight(val_truth, base[val_idx], pred_h, pred_a, rho[val_idx])
    print("zvolená váha gólů", blend_w)

    w_tr = train._weights([rows[i]["date"] for i in train_idx], train.HOLDOUT)
    cand_h, cand_a = _fit_pair(x[train_idx], y_h[train_idx], y_a[train_idx], w_tr)
    te_h, te_a = _predict_pair(cand_h, cand_a, x[test_idx])
    te_base = base[test_idx]
    te_rho = rho[test_idx]
    after_h = blend_w * te_h + (1.0 - blend_w) * te_base[:, 0]
    after_a = blend_w * te_a + (1.0 - blend_w) * te_base[:, 1]
    te_truth = {name: truth_all[name][test_idx] for name in list(MARKETS) + ["hg", "ag"]}
    before_p = batch_binary(te_base[:, 0], te_base[:, 1], te_rho)
    after_p = batch_binary(after_h, after_a, te_rho)
    freq = {name: float(truth_all[name][train_idx].mean()) for name in MARKETS}
    base_p = {name: np.full(len(test_idx), freq[name]) for name in MARKETS}
    before = pack_probs(te_truth, before_p)
    after = pack_probs(te_truth, after_p)
    baseline = pack_probs(te_truth, base_p)
    for label, pack in (("před", before), ("po", after), ("frekvence", baseline)):
        print(f"GÓLY {label}: ll={pack['mean']['log_loss']:.4f} brier={pack['mean']['brier']:.4f} n={pack['mean']['n']}")
        for name in MARKETS:
            print(f"  {name}: ll={pack[name]['log_loss']:.4f} brier={pack[name]['brier']:.4f}")

    ok, reason = metrics.goals_gate(after, before, baseline, previous)
    if blend_w <= 0:
        ok = False
        reason = "LightGBM na validaci nepřidal nic k Poissonu"
    print("brána gólů", ok, reason)
    test_rows = [rows[i] for i in test_idx]
    by_region = {
        "after": _region_mean(test_rows, te_truth, after_p),
        "before": _region_mean(test_rows, te_truth, before_p),
        "baseline": _region_mean(test_rows, te_truth, base_p),
    }
    report = {
        "split": "trénink < 2025-07-01, test ≥ 2025-07-01; váha z posledních 120 dní tréninku",
        "blend_w": blend_w,
        "published": bool(ok),
        "gate": {"ok": bool(ok), "reason": reason},
        "test": {"before": before, "after": after, "baseline": baseline},
        "by_region": by_region,
        "mae": {"before": _mae(te_base[:, 0], te_base[:, 1], te_truth), "after": _mae(after_h, after_a, te_truth)},
        "train_rate": freq,
        "features": GOAL_FEATURES,
        "objective": "poisson",
        "rounds": 140,
        "note": NOTE,
    }
    if ok:
        print("ostré gólové stromy na všech klubových řádcích")
        end = max(r["date"] for r in rows)
        prod_h, prod_a = _fit_pair(x, y_h, y_a, train._weights([r["date"] for r in rows], end))
        prod_h.save_model(str(paths["goals_h.txt"]))
        prod_a.save_model(str(paths["goals_a.txt"]))
        meta = {"published": True, "blend_w": blend_w, "features": GOAL_FEATURES, "objective": "poisson"}
        paths["goals_meta.json"].write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        for name, path in paths.items():
            _restore(path, backups[name])
        print("gólová brána neprošla, stromy se nepublikují")
    if patch_metrics:
        _patch(model_dir / "metrics.json", report)
    return report


def _patch(path, report):
    path = pathlib.Path(path)
    blob = {}
    if path.exists():
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            blob = {}
    blob["goals"] = report
    path.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")


def predict_lambdas(booster_h, booster_a, values):
    row = np.array([values], dtype=np.float64)
    pred_h = float(booster_h.predict(row)[0])
    pred_a = float(booster_a.predict(row)[0])
    return pred_h, pred_a


def load_boosters(folder):
    folder = pathlib.Path(folder)
    meta_path = folder / "goals_meta.json"
    home = folder / "goals_h.txt"
    away = folder / "goals_a.txt"
    if not (meta_path.exists() and home.exists() and away.exists()):
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not meta.get("published"):
        return None
    if meta.get("features") != GOAL_FEATURES:
        print("gólový model má jiné příznaky, přeskakuji")
        return None
    return {
        "home": lgb.Booster(model_file=str(home)),
        "away": lgb.Booster(model_file=str(away)),
        "blend_w": float(meta.get("blend_w") or 0.0),
        "meta": meta,
    }


def apply_match(goals, row_values, base_h, base_a):
    """Vrátí smíchané lambdy. Bez publikovaného modelu vrátí základ."""
    if not goals or not goals.get("home"):
        return float(base_h), float(base_a)
    values = list(row_values) + [float(base_h), float(base_a)]
    if len(values) != len(GOAL_FEATURES):
        return float(base_h), float(base_a)
    pred_h, pred_a = predict_lambdas(goals["home"], goals["away"], values)
    return blend_lambdas(base_h, base_a, pred_h, pred_a, goals.get("blend_w"))


def main():
    """Natřen jen gólový model. 1X2 soubory (gbm, dc, elo) se nesahejí."""
    metrics_path = MODEL / "metrics.json"
    previous = None
    elo_params = {"ha": 70, "coef": 0.55, "base_h": 1.48, "base_a": 1.18}
    if metrics_path.exists():
        blob = json.loads(metrics_path.read_text(encoding="utf-8"))
        previous = blob.get("goals")
        elo_params = blob.get("elo_params") or elo_params
    matches = dataset.load_all()
    if not matches:
        print("žádná data")
        return 1
    state = elo.new_state()
    rows = []
    for match in matches:
        snap = elo.apply_result(state, match, want_snap=True)
        if snap is False or match["pool"] != "club":
            continue
        sh, sa, h2h = snap
        nat = str(match["home_id"]).startswith("nat:")
        exp = elo.expected(sh["elo"], sa["elo"], 0.0 if match.get("neutral") else (elo.HA_NAT if nat else elo.HA_CLUB))
        rows.append({
            "date": match["date"], "region": match["region"], "league_id": match["league_id"],
            "home_id": match["home_id"], "away_id": match["away_id"], "neutral": bool(match.get("neutral")),
            "cup": bool(match.get("cup")), "imp": match.get("imp"),
            "hg": match["hg"], "ag": match["ag"],
            "sh": sh, "sa": sa, "h2h": h2h, "elo_exp": exp,
        })
    print("klubových řádků", len(rows))
    print("Dixon-Coles k 2023-07-01")
    dc_2023 = dixon.fit_leagues(matches, train.DC_ASOF)
    print("Dixon-Coles k 2025-07-01")
    dc_hold = dixon.fit_leagues(matches, train.HOLDOUT)
    run(rows, dc_2023, dc_hold, elo_params, MODEL, previous, patch_metrics=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
