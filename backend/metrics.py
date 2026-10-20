"""Přesnost, log loss a RPS (ranked probability score) pro 1X2. Pořadí tříd: domácí, remíza, hosté."""
import math

def _clip(probs):
    out = []
    for row in probs:
        vals = [min(1 - 1e-12, max(1e-12, float(p))) for p in row]
        total = sum(vals)
        out.append([v / total for v in vals])
    return out

def accuracy(y, probs):
    if not y:
        return None
    hit = 0
    for truth, row in zip(y, probs):
        pred = max(range(3), key=lambda i: row[i])
        hit += int(pred == int(truth))
    return hit / len(y)

def log_loss(y, probs):
    if not y:
        return None
    rows = _clip(probs)
    total = 0.0
    for truth, row in zip(y, rows):
        total -= math.log(row[int(truth)])
    return total / len(y)

def rps(y, probs):
    """RPS = průměr z (1/2) * sum_{k=1..2} (CDF_pred - CDF_obs)^2. Nižší je lepší."""
    if not y:
        return None
    rows = _clip(probs)
    total = 0.0
    for truth, row in zip(y, rows):
        obs = [0.0, 0.0, 0.0]
        obs[int(truth)] = 1.0
        cdf_p = cdf_o = 0.0
        acc = 0.0
        for k in range(2):
            cdf_p += row[k]
            cdf_o += obs[k]
            acc += (cdf_p - cdf_o) ** 2
        total += acc / 2.0
    return total / len(y)

def pack(y, probs):
    return {"n": len(y), "accuracy": accuracy(y, probs), "log_loss": log_loss(y, probs), "rps": rps(y, probs)}

def _bin(prob):
    return min(1 - 1e-12, max(1e-12, float(prob)))

def binary_log_loss(y, probs):
    if not y:
        return None
    total = 0.0
    for truth, prob in zip(y, probs):
        p = _bin(prob)
        t = 1.0 if truth else 0.0
        total -= t * math.log(p) + (1.0 - t) * math.log(1.0 - p)
    return total / len(y)

def brier(y, probs):
    if not y:
        return None
    total = 0.0
    for truth, prob in zip(y, probs):
        t = 1.0 if truth else 0.0
        total += (float(prob) - t) ** 2
    return total / len(y)

def binary_pack(y, probs):
    return {"n": len(y), "log_loss": binary_log_loss(y, probs), "brier": brier(y, probs)}

def _mean_metric(blob, key):
    vals = [blob[name][key] for name in ("ou15", "ou25", "ou35", "btts") if blob.get(name) and blob[name].get(key) is not None]
    if not vals:
        block = blob.get("mean") or {}
        return block.get(key)
    return sum(vals) / len(vals)

def goals_gate(after, before, baseline, previous=None):
    """Směs gólů musí porazit frekvenci na log loss i Brier a nesmí být horší než Dixon-Coles/Poisson."""
    reasons = []
    ok = True
    a_ll, b_ll, f_ll = _mean_metric(after, "log_loss"), _mean_metric(before, "log_loss"), _mean_metric(baseline, "log_loss")
    a_br, b_br, f_br = _mean_metric(after, "brier"), _mean_metric(before, "brier"), _mean_metric(baseline, "brier")
    if None in (a_ll, b_ll, f_ll, a_br, b_br, f_br):
        return False, "chybí metriky gólových trhů"
    if a_ll > f_ll - 0.005:
        ok = False
        reasons.append("log loss gólových trhů není aspoň o 0,005 lepší než frekvence")
    if a_br > f_br - 0.002:
        ok = False
        reasons.append("Brier gólových trhů není aspoň o 0,002 lepší než frekvence")
    if a_ll > b_ll + 0.001:
        ok = False
        reasons.append("log loss je horší než Dixon-Coles/Poisson")
    if a_br > b_br + 0.001:
        ok = False
        reasons.append("Brier je horší než Dixon-Coles/Poisson")
    prev = (previous or {}).get("test", {}).get("after") if isinstance(previous, dict) else None
    if prev:
        p_ll, p_br = _mean_metric(prev, "log_loss"), _mean_metric(prev, "brier")
        if p_ll is not None and a_ll > p_ll + 0.01:
            ok = False
            reasons.append("log loss gólů je o víc než 0,01 horší než minule")
        if p_br is not None and a_br > p_br + 0.005:
            ok = False
            reasons.append("Brier gólů je o víc než 0,005 horší než minule")
    return ok, ("; ".join(reasons) if reasons else "brána gólů prošla")

def gate(model, baseline, elo, previous=None):
    """Model musí porazit frekvenční baseline na log loss i RPS a nesmí být horší než Elo."""
    reasons = []
    ok = True
    if model["log_loss"] > baseline["log_loss"] - 0.01:
        ok = False
        reasons.append("log loss není aspoň o 0,01 lepší než frekvenční baseline")
    if model["rps"] > baseline["rps"] - 0.003:
        ok = False
        reasons.append("RPS není aspoň o 0,003 lepší než baseline")
    if model["log_loss"] > elo["log_loss"] + 0.001:
        ok = False
        reasons.append("log loss je horší než Elo")
    if model["rps"] > elo["rps"] + 0.001:
        ok = False
        reasons.append("RPS je horší než Elo")
    if previous:
        if model["log_loss"] > previous["log_loss"] + 0.01:
            ok = False
            reasons.append("log loss je o víc než 0,01 horší než minule publikovaný model")
        if model["rps"] > previous["rps"] + 0.005:
            ok = False
            reasons.append("RPS je o víc než 0,005 horší než minule")
    return ok, ("; ".join(reasons) if reasons else "brána prošla")
