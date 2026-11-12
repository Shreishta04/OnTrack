"""Copy OnTrack's logs from the server into a `logs` folder, to read in VS Code.

Run from the top OnTrack folder (or backend), with the venv active:

    python backend\\pull_logs.py            new lines since last time
    python backend\\pull_logs.py --all      start again from the oldest (60 days)

It writes one file per area into OnTrack\\logs\\ (never committed to git):

    items.log  stores.log  refresh.log  alerts.log  accounts.log
    budget.log  speed.log  app.log  errors.log      and all.log (everything)

Setup, once: in OnTrack (owner account), Settings → Shortcuts and extension →
make a key called "Laptop logs", then add it to backend\\.env:

    ONTRACK_LOGS_KEY=the-key
    ONTRACK_LOGS_SERVER=https://ontrack-production-8f1d.up.railway.app   (optional: this is the default)

Only Python's own modules are used (no psycopg), so Smart App Control has
nothing to block. Times are shown in India time.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
LOGS = HERE.parent / "logs"
LAST = LOGS / ".last_id"
DEFAULT_SERVER = "https://ontrack-production-8f1d.up.railway.app"
ZONE = ZoneInfo("Asia/Kolkata")
PAGE = 2000


def settings() -> tuple[str, str]:
    """The server and key: from the environment, else backend\\.env."""
    values = dict(os.environ)
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                name, _, value = line.partition("=")
                values.setdefault(name.strip(), value.strip().strip('"').strip("'"))
    key = values.get("ONTRACK_LOGS_KEY", "")
    if not key:
        sys.exit("No key yet. In OnTrack: Settings → Shortcuts and extension → make a key called "
                 "\"Laptop logs\", then add ONTRACK_LOGS_KEY=<the key> to backend\\.env")
    return values.get("ONTRACK_LOGS_SERVER", DEFAULT_SERVER).rstrip("/"), key


def fetch(server: str, key: str, after_id: int) -> list[dict]:
    url = f"{server}/logs?" + urllib.parse.urlencode({"after_id": after_id, "limit": PAGE})
    request = urllib.request.Request(url, headers={"X-API-Key": key, "User-Agent": "OnTrack pull_logs"})
    try:
        with urllib.request.urlopen(request, timeout=90) as answer:      # long enough for the server to wake
            return json.load(answer)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            sys.exit("The server doesn't recognise ONTRACK_LOGS_KEY. Make a new key in Settings and update backend\\.env")
        if e.code == 403:
            sys.exit("That key isn't the owner's. Only the owner account can read the logs.")
        sys.exit(f"The server answered {e.code}. Try again in a minute.")
    except urllib.error.URLError as e:
        sys.exit(f"Couldn't reach {server} ({e.reason}). Check the internet connection.")


def line(e: dict) -> str:
    """One readable line, plus an indented traceback for errors."""
    at = datetime.fromisoformat(e["at"]).astimezone(ZONE).strftime("%Y-%m-%d %H:%M:%S")
    who = (e.get("user_name") or ("server" if not e.get("user_id") else f"user {e['user_id']}"))[:12]
    detail = json.loads(e["detail"]) if e.get("detail") else {}
    trace = detail.pop("traceback", None)
    extras = "  ".join(f"{k}={json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v}"
                       for k, v in detail.items())
    took = f"  took {e['took_ms'] / 1000:.2f} s" if e.get("took_ms") is not None else ""
    ref = f"  ref {e['ref']}" if e.get("ref") else ""
    text = f"{at}  {e['level'].upper():<5}  {who:<12}  {e['event']}" + (f"  {extras}" if extras else "") + took + ref
    if trace:
        text += "\n" + "\n".join("        " + t for t in trace.rstrip().splitlines())
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy OnTrack's logs into the logs folder.")
    parser.add_argument("--all", action="store_true", help="start again from the oldest")
    args = parser.parse_args()

    server, key = settings()
    LOGS.mkdir(exist_ok=True)
    after = 0 if args.all or not LAST.exists() else int(LAST.read_text() or 0)
    if after == 0:
        for old in LOGS.glob("*.log"):              # starting over: no doubled lines
            old.unlink()

    total, by_area = 0, {}
    while True:
        batch = fetch(server, key, after)
        if not batch:
            break
        files: dict[str, list[str]] = {}
        for e in batch:
            text = line(e)
            files.setdefault(e["area"], []).append(text)
            files.setdefault("all", []).append(f"[{e['area']}] {text}")
            by_area[e["area"]] = by_area.get(e["area"], 0) + 1
        for area, lines in files.items():
            with open(LOGS / f"{area}.log", "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        after = batch[-1]["id"]
        LAST.write_text(str(after))
        total += len(batch)
        if len(batch) < PAGE:
            break

    if total == 0:
        print("No new log lines.")
    else:
        print(f"{total} new lines → {LOGS}")
        for area, n in sorted(by_area.items(), key=lambda x: -x[1]):
            print(f"  {area:<9} {n}")
        if by_area.get("errors"):
            print("  ⚠ errors.log has new lines: open it first.")


if __name__ == "__main__":
    main()
