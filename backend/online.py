"""Průběžné Elo z dohraných zápasů. Každý export začíná od základního stavu a přehraje state.json jen jednou."""
import datetime as dt
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import elo

KEEP_DAYS = 21


def parse_date(value):
    return dt.date.fromisoformat(str(value)[:10])


def should_apply(match, trained_through, recent_keys):
    status = match.get("status") or ""
    if status != "finished":
        return False
    if match.get("hg") is None or match.get("ag") is None:
        return False
    if not trained_through:
        return True
    date = parse_date(match["date"])
    end = parse_date(trained_through)
    if date > end:
        return True
    if (end - date).days <= KEEP_DAYS and match.get("key") not in recent_keys:
        return True
    return False


def trim(matches, today=None):
    today = today or dt.date.today()
    kept = []
    seen_ids = set()
    seen_keys = set()
    for match in matches:
        mid = match.get("id")
        key = match.get("key")
        if mid and mid in seen_ids:
            continue
        if key and key in seen_keys:
            continue
        try:
            date = parse_date(match["date"])
        except (TypeError, ValueError):
            continue
        if (today - date).days > KEEP_DAYS:
            continue
        if mid:
            seen_ids.add(mid)
        if key:
            seen_keys.add(key)
        kept.append(match)
    return kept


def replay(base_blob, matches):
    state = elo.load_runtime(base_blob)
    trained = base_blob.get("trained_through")
    recent = set(base_blob.get("recent_keys") or [])
    applied = 0
    for match in matches:
        if not should_apply(match, trained, recent):
            continue
        if elo.apply_result(state, match, want_snap=False):
            applied += 1
    return state, applied


def stable_id(source, raw_id, date, home_id, away_id):
    if source == "espn" and raw_id:
        return f"espn:{raw_id}"
    if source == "sofa" and raw_id:
        return f"sofa:{raw_id}"
    if source == "s365" and raw_id:
        return f"s365:{raw_id}"
    return f"fx:{date}|{home_id}|{away_id}"
