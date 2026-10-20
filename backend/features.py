"""Příznaky před zápasem. Chybějící xG/střely zůstávají NaN (LightGBM je umí)."""
import math

FEATURES = [
    "elo_diff", "elo_h", "elo_a", "elo_exp",
    "dc_lh", "dc_la", "dc_ph", "dc_pd", "dc_pa",
    "f5_gf", "f5_ga", "f10_gf", "f10_ga",
    "f5_xg", "f10_xg", "f5_sot", "f10_sot",
    "venue_gf", "rest_diff", "euro_h", "euro_a", "h2h",
    "imp_h", "imp_d", "imp_a", "odds_missing", "cup",
]

def _sub(a, b):
    if a is None or b is None:
        return math.nan
    return float(a) - float(b)

def row_from(snap_h, snap_a, h2h, dc_probs, elo_exp, implied, cup):
    imp = implied or [math.nan, math.nan, math.nan]
    dc = dc_probs or [math.nan, math.nan, math.nan, math.nan, math.nan]
    # dc = lh, la, ph, pd, pa
    values = {
        "elo_diff": snap_h["elo"] - snap_a["elo"],
        "elo_h": snap_h["elo"],
        "elo_a": snap_a["elo"],
        "elo_exp": elo_exp,
        "dc_lh": dc[0], "dc_la": dc[1], "dc_ph": dc[2], "dc_pd": dc[3], "dc_pa": dc[4],
        "f5_gf": _sub(snap_h["f5_gf"], snap_a["f5_gf"]),
        "f5_ga": _sub(snap_h["f5_ga"], snap_a["f5_ga"]),
        "f10_gf": _sub(snap_h["f10_gf"], snap_a["f10_gf"]),
        "f10_ga": _sub(snap_h["f10_ga"], snap_a["f10_ga"]),
        "f5_xg": _sub(snap_h["f5_xg"], snap_a["f5_xg"]),
        "f10_xg": _sub(snap_h["f10_xg"], snap_a["f10_xg"]),
        "f5_sot": _sub(snap_h["f5_sot"], snap_a["f5_sot"]),
        "f10_sot": _sub(snap_h["f10_sot"], snap_a["f10_sot"]),
        "venue_gf": _sub(snap_h["venue_gf"], snap_a["venue_ga_away"]),
        "rest_diff": float(snap_h["rest"] - snap_a["rest"]),
        "euro_h": float(snap_h["euro"]),
        "euro_a": float(snap_a["euro"]),
        "h2h": float(h2h or 0.0),
        "imp_h": imp[0], "imp_d": imp[1], "imp_a": imp[2],
        "odds_missing": 0.0 if implied else 1.0,
        "cup": 1.0 if cup else 0.0,
    }
    return [values[name] for name in FEATURES]
