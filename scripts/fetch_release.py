"""Stáhne release `model`. Když chybí nebo je useknutý, nechá zálohu v data/model. State.json bere z Pages, do release nic nenahrává."""
import json
import os
import pathlib
import shutil
import subprocess
import tarfile
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL = ROOT / "data" / "model"
INCOMING = ROOT / "data" / "online-cache" / "incoming"
PUBLISHED = ROOT / "data" / "online" / "state.published.json"
REPO = os.environ.get("GITHUB_REPOSITORY", "robertzechovsky639-ui/fotbal-predikce-ml")
# Gólové stromy (goals_h.txt, goals_a.txt, goals_meta.json) jsou volitelné.
# Starší release bez nich pořád platí; když v archivu jsou, extractall je doplní.
NEED = {"gbm.txt", "dc.json", "elo_state.json", "metrics.json"}


def archive_ok(path):
    path = pathlib.Path(path)
    if not path.is_file() or path.stat().st_size < 1000:
        return False
    try:
        with tarfile.open(path, "r:gz") as tar:
            names = {pathlib.PurePosixPath(m.name).name for m in tar.getmembers() if m.isfile()}
    except (tarfile.TarError, OSError, EOFError):
        return False
    return NEED <= names


def download_asset(name, dest):
    dest = pathlib.Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    proc = subprocess.run(["gh", "release", "download", "model", "-p", name, "-D", str(dest.parent), "-R", REPO], capture_output=True, text=True)
    got = dest.parent / name
    if proc.returncode == 0 and got.is_file() and got.stat().st_size > 0:
        if got != dest:
            shutil.move(str(got), dest)
        return True
    print("stažení", name, "selhalo:", (proc.stderr or proc.stdout or "").strip())
    return False


def state_ok(payload):
    if isinstance(payload, (bytes, str)):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False
    return isinstance(payload, dict) and isinstance(payload.get("matches"), list)


def _write_state(obj):
    target = ROOT / "data" / "online" / "state.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    print("state.json", len(obj["matches"]))


def pull_state():
    """Nejdřív asset release `model` (state.json --clobber). Pages je záloha, když release ještě není."""
    dest = INCOMING / "state.json"
    if download_asset("state.json", dest) and dest.is_file():
        try:
            obj = json.loads(dest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            obj = None
        if state_ok(obj):
            _write_state(obj)
            return
        print("state.json v release není použitelný")
    url = f"https://{REPO.split('/')[0]}.github.io/{REPO.split('/')[1]}/data/state.json"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = resp.read()
        obj = json.loads(data.decode("utf-8"))
    except Exception as exc:
        print("state.json z Pages není:", exc)
        return
    if state_ok(obj):
        _write_state(obj)


def main():
    INCOMING.mkdir(parents=True, exist_ok=True)
    dest = INCOMING / "model.tar.gz"
    ok = False
    for attempt in range(1, 4):
        if download_asset("model.tar.gz", dest) and archive_ok(dest):
            ok = True
            break
        print("pokus", attempt, "archiv není celý")
        time.sleep(5)
    if ok:
        MODEL.mkdir(parents=True, exist_ok=True)
        with tarfile.open(dest, "r:gz") as tar:
            tar.extractall(MODEL)
        print("model z release")
    else:
        have = all((MODEL / name).exists() for name in NEED)
        print("release chybí, použitý model v repu" if have else "model chybí")
        if not have:
            return 1
    pull_state()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
