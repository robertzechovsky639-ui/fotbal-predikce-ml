"""Predikce jednoho zápasu. Vždy vrátí 1X2; málo historie = Elo a nižší jistota."""
import datetime as dt
import pathlib
import sys

import lightgbm as lgb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import dixon
import elo
import features
import names
import train

LOW_LEAGUE = "Málo historie v soutěži – odhad z Elo a síly ligy, nižší spolehlivost."
LOW_TEAM = "Tým není v historii – odhad podle síly soutěže, nižší spolehlivost."


def _blank_snap(prior):
    return {
        "elo": float(prior), "n": 0, "prior": float(prior), "rest": 14, "euro": 0,
        "f5_gf": None, "f5_ga": None, "f10_gf": None, "f10_ga": None,
        "f5_xg": None, "f10_xg": None, "f5_sot": None, "f10_sot": None,
        "venue_gf": None, "venue_ga_away": None,
    }


def _snap(state, tid, prior, date):
    team = (state.get("teams") or {}).get(tid)
    if not team:
        return _blank_snap(prior)
    shot = elo.snapshot(team, date)
    shot["elo"] = elo.shrunk_elo(team)
    return shot


def linked_league(dc_models, hinted, home_id, away_id):
    """Když oba týmy sedí v některém ligovém modelu, použij to id (ESPN slug ≠ football-data kód)."""
    if not dc_models:
        return hinted
    hinted_model = dc_models.get(hinted)
    if hinted_model and home_id in hinted_model["teams"] and away_id in hinted_model["teams"]:
        return hinted
    best, best_n = None, -1
    for lid, model in dc_models.items():
        teams = model.get("teams") or {}
        if home_id in teams and away_id in teams and int(model.get("n") or 0) > best_n:
            best, best_n = lid, int(model.get("n") or 0)
    return best or hinted


def predict_fixture(state, dc_models, booster, blend_w, elo_params, league_counts, fixture):
    """fixture: home_name, away_name, country, league_id, region, league_name, date, neutral, cup."""
    country = fixture.get("country")
    home_id = names.resolve_club(state.get("teams") or {}, fixture["home_name"], country)
    away_id = names.resolve_club(state.get("teams") or {}, fixture["away_name"], country)
    league_id = linked_league(dc_models, fixture.get("league_id"), home_id, away_id)
    prior = float(fixture.get("prior") or elo.prior_for(league_id, fixture.get("region"), fixture.get("league_name") or ""))
    date = fixture["date"]
    if isinstance(date, str):
        date = dt.date.fromisoformat(date[:10])
    sh = _snap(state, home_id, prior, date)
    sa = _snap(state, away_id, prior, date)
    neutral = bool(fixture.get("neutral"))
    exp = elo.expected(sh["elo"], sa["elo"], 0.0 if neutral else elo.HA_CLUB)
    h2h = elo.h2h_value(state, home_id, away_id)
    n_league = int((league_counts or {}).get(league_id) or 0)
    known = sh["n"] >= 8 and sa["n"] >= 8 and n_league >= 200 and booster is not None
    dc_model = (dc_models or {}).get(league_id)
    dc_l = dixon.lambdas_from_model(dc_model, home_id, away_id, neutral) if known or dc_model else None
    rho = float(dc_model["rho"]) if dc_model and dc_l else 0.0
    elo_p, elo_lh, elo_la = train.elo_probs_from(sh["elo"], sa["elo"], neutral, elo_params)
    note = None
    low = False
    if known:
        dc_vec = None
        if dc_l:
            mk = dixon.markets(dc_l[0], dc_l[1], rho)["p"]
            dc_vec = [dc_l[0], dc_l[1], mk[0], mk[1], mk[2]]
        row = features.row_from(sh, sa, h2h, dc_vec, exp, fixture.get("imp"), fixture.get("cup"))
        import numpy as np
        lgb_p = booster.predict(np.array([row], dtype=float))[0]
        w = float(blend_w or 0.0)
        probs = [w * float(lgb_p[i]) + (1 - w) * elo_p[i] for i in range(3)]
        total = sum(probs) or 1.0
        probs = [p / total for p in probs]
        if dc_l:
            lh, la = dc_l
        else:
            lh, la = elo_lh, elo_la
            rho = 0.0
    else:
        probs = elo_p
        lh, la = elo_lh, elo_la
        rho = 0.0
        low = True
        if sh["n"] == 0 or sa["n"] == 0:
            note = LOW_TEAM
        else:
            note = LOW_LEAGUE
    lh, la = dixon.calibrate(lh, la, rho, probs)
    mk = dixon.markets(lh, la, rho)
    # kalibrace má 1X2 srovnat s publikovanou pravděpodobností; trhy bereme z matice,
    # ale 1X2 publikujeme přesně to, co vyšlo z modelu (matice je jen pro góly).
    return {
        "home_id": home_id, "away_id": away_id,
        "pred": probs, "lam": [lh, la], "rho": rho,
        "ou": {"over": mk["over"], "under": mk["under"], "line": 2.5},
        "btts": mk["btts"], "exact": mk["exact"],
        "pred_low": low, "pred_note": note,
        "elo": [round(sh["elo"]), round(sa["elo"])],
        "n": [sh["n"], sa["n"]],
        "h2h": h2h,
        "prior": prior,
    }


def load_model(folder):
    folder = pathlib.Path(folder)
    import json
    elo_blob = json.loads((folder / "elo_state.json").read_text(encoding="utf-8"))
    dc_models = {}
    dc_path = folder / "dc.json"
    if dc_path.exists():
        dc_models = json.loads(dc_path.read_text(encoding="utf-8"))
    booster = None
    gbm = folder / "gbm.txt"
    if gbm.exists():
        booster = lgb.Booster(model_file=str(gbm))
    metrics_blob = {}
    mp = folder / "metrics.json"
    if mp.exists():
        metrics_blob = json.loads(mp.read_text(encoding="utf-8"))
    params = elo_blob.get("elo_params") or metrics_blob.get("elo_params") or {"ha": 70, "coef": 0.55, "base_h": 1.48, "base_a": 1.18}
    blend_w = elo_blob.get("blend_w", metrics_blob.get("blend_w", 0.5))
    state = elo.load_runtime(elo_blob)
    return {
        "state": state, "elo_blob": elo_blob, "dc": dc_models, "booster": booster,
        "blend_w": blend_w, "elo_params": params,
        "league_counts": elo_blob.get("league_counts") or {},
        "metrics": metrics_blob,
        "trained_through": elo_blob.get("trained_through"),
        "recent_keys": set(elo_blob.get("recent_keys") or []),
    }
