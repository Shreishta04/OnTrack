"""OnTrack's logs: one place every important thing that happens is written down.

Each event goes to two places:
- Railway's log (printed), for a quick look while it's live;
- the `events` table, which is kept for 60 days. `pull_logs.py` copies it into
  a `logs` folder on my laptop, one file per area, to read in VS Code.

Areas (one log file each):
    items     add, edit, move, delete, restore, undo, links
    stores    every store page read: which store, who downloaded it, the result
    refresh   ↻, the phone's Refresh, the 9 am price check
    alerts    notifications queued, sent, held at night, phones added
    accounts  sign-ups, logins, keys, invites, remove access
    budget    budget and reset day changes
    speed     slow requests, with where the time went
    app       problems the app itself ran into on a phone or laptop
    errors    anything that went wrong, with full detail and a reference code

Never written: passwords, keys and tokens, full product links (only the
store's name), the pages themselves.

How it works: `log()` puts the event on a queue and returns at once; a
background thread writes the queue to the database a moment later, on its
own connection, so logging never slows a request down or gets mixed into its
transaction. `flush()` writes everything now (tests, shutting down).
"""

from __future__ import annotations

import atexit
import contextvars
import json
import logging
import queue
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

AREAS = ("items", "stores", "refresh", "alerts", "accounts", "budget", "speed", "app", "errors")
KEEP_DAYS = 60
DETAIL_MAX = 4000                 # characters of detail kept per event (tracebacks are long)

printer = logging.getLogger("uvicorn.error")       # what Railway shows
_queue: "queue.Queue[tuple]" = queue.Queue()
_wake = threading.Event()
_writer: threading.Thread | None = None
_lock = threading.Lock()
enabled = True                                    # False: printed only, never stored
background = True                                 # False (tests): stored only when flush() is called

# What the request being answered has gathered so far (its user, details
# services added with note(), how long each part took with span()).
_current: contextvars.ContextVar[dict | None] = contextvars.ContextVar("ontrack_request", default=None)


def new_ref() -> str:
    """A short code the person can quote ("E-7K2Q"); it's on the matching log line."""
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"            # no 0/O or 1/I/L to misread
    return "E-" + "".join(secrets.choice(alphabet) for _ in range(4))


def trace() -> str:
    """The current exception's traceback, shortened from the middle if it's long
    (the start says where it began, the end where it broke)."""
    import traceback
    text = traceback.format_exc()
    return text if len(text) <= 3000 else text[:600] + "\n  … (middle cut) …\n" + text[-2300:]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def log(area: str, event: str, *, user_id: int | None = None, level: str = "info",
        ref: str | None = None, took: float | None = None, printed: bool = True, **detail) -> None:
    """Write one event. `detail` is anything useful (ids, counts, reasons):
    never a password, key, token or full link. printed=False: the caller
    already printed its own line for Railway."""
    if area not in AREAS:
        area = "errors"
    if user_id is None and (ctx := _current.get()):
        user_id = ctx.get("user_id")
    clean = {k: v for k, v in detail.items() if v is not None}
    text = json.dumps(clean, ensure_ascii=False, default=str)[:DETAIL_MAX] if clean else ""
    took_ms = None if took is None else int(took * 1000)
    line = f"{area:<8} {event}" + (f"  {text}" if text else "") + (f"  took={took:.2f}s" if took else "") \
        + (f"  user={user_id}" if user_id else "") + (f"  ref={ref}" if ref else "")
    if printed:
        (printer.warning if level in ("warn", "error") else printer.info)("%s", line)
    if enabled:
        _queue.put((_now(), user_id, area, level, event[:200], text, ref, took_ms))
        if background:
            _start_writer()
            _wake.set()


# ----------------------------------------------------- the current request

def begin(method: str, path: str) -> contextvars.Token:
    return _current.set({"method": method, "path": path, "notes": {}, "spans": {}, "user_id": None})


def end(token: contextvars.Token) -> None:
    _current.reset(token)


def current() -> dict | None:
    return _current.get()


def set_user(user_id: int) -> None:
    if ctx := _current.get():
        ctx["user_id"] = user_id


def note(**detail) -> None:
    """Add details to the current request's log line (what was moved where…)."""
    if ctx := _current.get():
        ctx["notes"].update({k: v for k, v in detail.items() if v is not None})


@contextmanager
def span(name: str):
    """Time one part of a request: a slow request's line says where the time went."""
    start = time.monotonic()
    try:
        yield
    finally:
        if ctx := _current.get():
            ctx["spans"][name] = round(ctx["spans"].get(name, 0) + time.monotonic() - start, 3)


# ----------------------------------------------------------------- writing

def _start_writer() -> None:
    global _writer
    with _lock:
        if _writer is None or not _writer.is_alive():
            _writer = threading.Thread(target=_write_loop, name="ontrack-events", daemon=True)
            _writer.start()


def _write_loop() -> None:
    while True:
        _wake.wait()
        time.sleep(0.3)                    # gather a few events into one write
        _wake.clear()
        try:
            flush()
        except Exception as exc:           # the log must never take the server down
            printer.warning("events   couldn't write to the database: %s", exc)


def flush() -> int:
    """Write every queued event to the database now. Returns how many."""
    rows = []
    while True:
        try:
            rows.append(_queue.get_nowait())
        except queue.Empty:
            break
    if not rows:
        return 0
    import db                              # here: db doesn't import this module, but keep the start-up light
    conn = db.connect()
    try:
        for row in rows:
            conn.execute("INSERT INTO events (at, user_id, area, level, event, detail, ref, took_ms) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", row)
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def discard() -> None:
    """Forget what's queued (tests: each test starts with an empty log)."""
    while True:
        try:
            _queue.get_nowait()
        except queue.Empty:
            return


atexit.register(lambda: enabled and background and flush())


# ----------------------------------------------------------------- reading

def purge(conn) -> int:
    """Events older than KEEP_DAYS go (the free database is 0.5 GB)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).isoformat(timespec="milliseconds")
    cur = conn.execute("DELETE FROM events WHERE at < ?", (cutoff,))
    conn.commit()
    return cur.rowcount


def read(conn, after_id: int = 0, area: str | None = None, limit: int = 2000) -> list[dict]:
    """Events after `after_id`, oldest first, with the person's name (owner only)."""
    query = ("SELECT events.*, users.name AS user_name FROM events "
             "LEFT JOIN users ON users.id = events.user_id WHERE events.id > ?")
    params: list = [after_id]
    if area:
        query += " AND events.area = ?"
        params.append(area)
    rows = conn.execute(query + " ORDER BY events.id LIMIT ?", (*params, limit)).fetchall()
    return [dict(r) for r in rows]
