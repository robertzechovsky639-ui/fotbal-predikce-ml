"""Dixon-Coles: bivariátní Poisson, časový úpadek vah a korekce rho. Skóre matice -> 1X2, over/under, BTTS."""
import math
import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

XI = 0.0025
MAXG = 8

def score_matrix(lh, la, rho=0.0, maxg=MAXG):
    lh = float(np.clip(lh, 0.05, 6.5))
    la = float(np.clip(la, 0.05, 6.5))
    ks = np.arange(0, maxg + 1)
    hs = poisson.pmf(ks, lh)
    aw = poisson.pmf(ks, la)
    hs[-1] = max(0.0, 1.0 - float(hs[:-1].sum()))
    aw[-1] = max(0.0, 1.0 - float(aw[:-1].sum()))
    matrix = np.outer(hs, aw)
    rho = float(rho)
    if rho:
        def tau(i, j):
            if i == 0 and j == 0:
                return 1 - lh * la * rho
            if i == 0 and j == 1:
                return 1 + lh * rho
            if i == 1 and j == 0:
                return 1 + la * rho
            if i == 1 and j == 1:
                return 1 - rho
            return 1.0
        for i in range(min(2, maxg + 1)):
            for j in range(min(2, maxg + 1)):
                matrix[i, j] *= max(1e-8, tau(i, j))
    matrix = np.clip(matrix, 0, None)
    total = float(matrix.sum())
    if total <= 0:
        matrix[:] = 0
        matrix[0, 0] = 1
    else:
        matrix /= total
    return matrix

def _count_market(mass, ou_lines):
    """Marginální počty gólů: očekávání, over/under, modus a rozdělení."""
    keys = sorted(mass)
    if not keys:
        empty = {f"{line:.1f}": {"over": 0.0, "under": 1.0} for line in ou_lines}
        return {"xg": 0.0, "ou": empty, "mode": [0, 1.0], "dist": [(0, 1.0)]}
    total_p = sum(mass.values()) or 1.0
    xg = sum(k * mass[k] for k in keys) / total_p

    def over_at(need):
        return sum(mass[k] for k in keys if k >= need) / total_p

    ou = {}
    for line in ou_lines:
        over = over_at(int(line + 0.5))
        ou[f"{line:.1f}"] = {"over": over, "under": 1.0 - over}
    mode = max(keys, key=lambda k: (mass[k], -k))
    dist = [(k, mass[k] / total_p) for k in keys if mass[k] / total_p >= 0.004]
    return {"xg": xg, "ou": ou, "mode": [mode, mass[mode] / total_p], "dist": dist}


def markets_from_matrix(matrix, base_h=0, base_a=0):
    """1X2, góly každého týmu, součet zápasu, BTTS a nejpravděpodobnější skóre. base_* přičte už vstřelené góly."""
    n = matrix.shape[0]
    home = draw = away = btts = 0.0
    overs = {1.5: 0.0, 2.5: 0.0, 3.5: 0.0}
    home_c, away_c, tot_c = {}, {}, {}
    exact = []
    bh, ba = int(base_h or 0), int(base_a or 0)
    for i in range(n):
        for j in range(n):
            p = float(matrix[i, j])
            H, A = bh + i, ba + j
            if H > A:
                home += p
            elif H == A:
                draw += p
            else:
                away += p
            total_goals = H + A
            if total_goals >= 2:
                overs[1.5] += p
            if total_goals >= 3:
                overs[2.5] += p
            if total_goals >= 4:
                overs[3.5] += p
            if H >= 1 and A >= 1:
                btts += p
            home_c[H] = home_c.get(H, 0.0) + p
            away_c[A] = away_c.get(A, 0.0) + p
            tot_c[total_goals] = tot_c.get(total_goals, 0.0) + p
            exact.append((f"{H}-{A}", p))
    total = home + draw + away
    if total <= 0:
        home = draw = away = 1 / 3
    else:
        home, draw, away = home / total, draw / total, away / total
    exact.sort(key=lambda item: -item[1])
    lines = {f"{line:.1f}": {"over": overs[line], "under": 1.0 - overs[line]} for line in (1.5, 2.5, 3.5)}
    home_side = _count_market(home_c, (0.5, 1.5, 2.5))
    away_side = _count_market(away_c, (0.5, 1.5, 2.5))
    match_total = _count_market(tot_c, (1.5, 2.5, 3.5))
    match_total["lines"] = lines
    return {
        "p": [home, draw, away],
        "over": overs[2.5],
        "under": 1.0 - overs[2.5],
        "lines": lines,
        "btts": btts,
        "exact": exact[:5],
        "teams": {"home": home_side, "away": away_side},
        "total": match_total,
    }

def markets(lh, la, rho=0.0, maxg=MAXG):
    return markets_from_matrix(score_matrix(lh, la, rho, maxg))

def live_markets(hg, ag, lh_rem, la_rem, maxg=6):
    """Zbývající Poisson (bez rho) složený s aktuálním skóre. Over/under se počítá z konečného součtu."""
    matrix = score_matrix(max(lh_rem, 1e-4), max(la_rem, 1e-4), 0.0, maxg)
    return markets_from_matrix(matrix, hg, ag)

def remaining_lambdas(lh, la, minute, reds=(0, 0), score=(0, 0), period=1):
    """lambda * zbývající/90, ke konci zápasu roste; červené karty a stav skóre. Po 90 min bez prodloužení."""
    minute = 0 if minute is None else float(minute)
    try:
        period = int(period or 1)
    except (TypeError, ValueError):
        period = 1
    if period > 2 or minute >= 120:
        frac = 0.0
        late = 1.0
    else:
        m = min(max(minute, 0.0), 99.0)
        regular = max(0.0, 90.0 - min(m, 90.0))
        extra = max(0.0, 96.0 - m) if m > 90 else 0.0
        frac = (regular + extra) / 90.0
        late = 1.0 + (0.35 * max(0.0, min(m, 90.0) - 75.0) / 15.0 if m > 75 else 0.0)
        frac *= late
    lh2 = float(lh) * frac
    la2 = float(la) * frac
    rh, ra = int(reds[0] or 0), int(reds[1] or 0)
    if rh > ra:
        lh2 *= 0.68 ** (rh - ra)
        la2 *= 1.18 ** (rh - ra)
    elif ra > rh:
        la2 *= 0.68 ** (ra - rh)
        lh2 *= 1.18 ** (ra - rh)
    if 60 <= minute <= 100 and period <= 2:
        diff = int(score[0] or 0) - int(score[1] or 0)
        if diff <= -1:
            lh2 *= 1.10
            la2 *= 0.94
        elif diff >= 1:
            la2 *= 1.10
            lh2 *= 0.94
    return max(lh2, 1e-4), max(la2, 1e-4)

def calibrate(lh, la, rho, target):
    """Posune rozdíl lambd, aby 1X2 matice sedělo na publikovanou pravděpodobnost (živě v minutě 0)."""
    best = None
    best_loss = 1e9
    for step in range(-16, 17):
        delta = step * 0.05
        got = markets(lh * math.exp(delta), la * math.exp(-delta), rho)["p"]
        loss = sum((got[i] - target[i]) ** 2 for i in range(3))
        if loss < best_loss:
            best_loss = loss
            best = (lh * math.exp(delta), la * math.exp(-delta))
    return best

def _fit_one(home_idx, away_idx, gh, ga, weights, neutral, n_teams):
    k = n_teams - 1
    if k < 1:
        return None
    x0 = np.zeros(2 * k + 2)
    x0[-2] = 0.22
    x0[-1] = -0.05
    bounds = [(-2.2, 2.2)] * (2 * k) + [(-0.15, 0.7), (-0.18, 0.08)]

    def nll(p):
        att = np.zeros(n_teams)
        deff = np.zeros(n_teams)
        att[:k] = p[:k]
        att[k] = -att[:k].sum()
        deff[:k] = p[k:2 * k]
        deff[k] = -deff[:k].sum()
        home, rho = p[-2], p[-1]
        adv = home * (1.0 - neutral)
        lh = np.exp(np.clip(att[home_idx] - deff[away_idx] + adv, -2.6, 1.8))
        la = np.exp(np.clip(att[away_idx] - deff[home_idx], -2.6, 1.8))
        tau = np.ones_like(lh)
        tau[(gh == 0) & (ga == 0)] = 1 - lh[(gh == 0) & (ga == 0)] * la[(gh == 0) & (ga == 0)] * rho
        tau[(gh == 0) & (ga == 1)] = 1 + lh[(gh == 0) & (ga == 1)] * rho
        tau[(gh == 1) & (ga == 0)] = 1 + la[(gh == 1) & (ga == 0)] * rho
        tau[(gh == 1) & (ga == 1)] = 1 - rho
        tau = np.clip(tau, 1e-6, None)
        ll = np.log(tau) + gh * np.log(lh) - lh + ga * np.log(la) - la
        pen = 0.03 * (float(np.dot(att, att)) + float(np.dot(deff, deff)))
        return -float(np.dot(weights, ll)) + pen

    res = minimize(nll, x0, method="L-BFGS-B", bounds=bounds, options={"maxiter": 40, "ftol": 1e-5})
    p = res.x
    att = np.zeros(n_teams)
    deff = np.zeros(n_teams)
    att[:k] = p[:k]
    att[k] = -att[:k].sum()
    deff[:k] = p[k:2 * k]
    deff[k] = -deff[:k].sum()
    return att, deff, float(p[-2]), float(p[-1])

def fit_leagues(matches, asof, years=5, min_matches=400, min_teams=8):
    """Fit jen z zápasů přísně před asof (bez úniku). Vrací {league_id: {home, rho, teams}}."""
    import datetime as dt
    start = asof - dt.timedelta(days=int(365.25 * years))
    groups = {}
    for match in matches:
        if match.get("cup") or match.get("pool") != "club":
            continue
        if match["date"] >= asof or match["date"] < start:
            continue
        groups.setdefault(match["league_id"], []).append(match)
    models = {}
    for league_id, rows in groups.items():
        if len(rows) < min_matches:
            continue
        ids = sorted({m["home_id"] for m in rows} | {m["away_id"] for m in rows})
        if len(ids) < min_teams or len(ids) > 80:
            # příliš široká „liga“ (špatně slitá data) radši vynechat
            if len(ids) < min_teams:
                continue
            counts = {tid: 0 for tid in ids}
            for m in rows:
                counts[m["home_id"]] += 1
                counts[m["away_id"]] += 1
            ids = [tid for tid, n in counts.items() if n >= 12]
            if len(ids) < min_teams or len(ids) > 60:
                continue
            idset = set(ids)
            rows = [m for m in rows if m["home_id"] in idset and m["away_id"] in idset]
            if len(rows) < min_matches:
                continue
        index = {tid: i for i, tid in enumerate(ids)}
        home_idx = np.array([index[m["home_id"]] for m in rows])
        away_idx = np.array([index[m["away_id"]] for m in rows])
        gh = np.array([m["hg"] for m in rows], dtype=float)
        ga = np.array([m["ag"] for m in rows], dtype=float)
        neutral = np.array([1.0 if m.get("neutral") else 0.0 for m in rows])
        days = np.array([(asof - m["date"]).days for m in rows], dtype=float)
        weights = np.exp(-XI * days)
        weights = weights / max(weights.mean(), 1e-9)
        try:
            fitted = _fit_one(home_idx, away_idx, gh, ga, weights, neutral, len(ids))
        except Exception as exc:
            print("DC selhalo", league_id, exc)
            continue
        if not fitted:
            continue
        att, deff, home, rho = fitted
        teams = {tid: {"att": round(float(att[i]), 5), "def": round(float(deff[i]), 5)} for i, tid in enumerate(ids)}
        models[league_id] = {"home": round(home, 5), "rho": round(rho, 5), "teams": teams, "n": len(rows)}
        print(f"  DC {league_id}: n={len(rows)} týmů={len(ids)} home={home:.3f} rho={rho:.3f}")
    return models

def lambdas_from_model(model, home_id, away_id, neutral=False):
    if not model:
        return None
    teams = model["teams"]
    if home_id not in teams or away_id not in teams:
        return None
    home = 0.0 if neutral else model["home"]
    lh = math.exp(np.clip(teams[home_id]["att"] - teams[away_id]["def"] + home, -2.6, 1.8))
    la = math.exp(np.clip(teams[away_id]["att"] - teams[home_id]["def"], -2.6, 1.8))
    return float(lh), float(la)
