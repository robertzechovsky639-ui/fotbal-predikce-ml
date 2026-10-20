"""Každý zápas v exportu má 1X2. Nízká jistota je povolená, chybějící predikce ne."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "dist" / "data" / "matches.json")
data = json.loads(path.read_text(encoding="utf-8"))
missing = []
bad = []
for match in data["matches"]:
    pred = match.get("pred") or {}
    if any(pred.get(k) is None for k in ("h", "d", "a")):
        missing.append(match.get("id"))
        continue
    total = pred["h"] + pred["d"] + pred["a"]
    if abs(total - 1) > 0.02:
        bad.append(match.get("id"))
print("zápasů", len(data["matches"]), "bez predikce", len(missing), "součet mimo 1", len(bad))
if missing or bad:
    print(missing[:10], bad[:10])
    sys.exit(1)
