"""
Business logic: everything the app *does*, independent of HTTP.

main.py only translates web requests into calls to these functions. Keeping
them apart means the rules (cheapest link wins, what fits the budget, refresh
cooldown) can be tested directly, and a future Telegram bot or CLI could reuse
them unchanged.

`extract_fn` is passed in rather than imported, so tests can supply a fake
that never touches the internet.

Every function takes `uid`, the user it acts for, and only ever sees that
user's rows. Asking for someone else's item answers "not found" (not
"forbidden"), so nobody can even learn which item numbers exist.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
import sqlite3
import os
from dataclasses import replace
import calendar
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Callable
from urllib.parse import urlsplit

from extractor import (NO_PRICE_FROM_BROWSER, NO_PRICE_JAVASCRIPT, Product, clean_url,
                       extract, html_fetcher, make_fetcher)

ExtractFn = Callable[[str], Product]

# Uvicorn already prints this logger (on the laptop and in Railway's logs).
log = logging.getLogger("uvicorn.error")

REFRESH_COOLDOWN = timedelta(hours=1)   # skip links checked more recently than this
REFRESH_CONCURRENCY = 3                 # at most 3 store pages being fetched at once
REFRESH_DELAY = (0.5, 1.5)              # random pause (seconds) before each fetch


class NotFound(Exception):
    pass


class Duplicate(Exception):
    """This link is already saved. Carries the item AND the link, so a client
    (like the browser extension) can offer to update that link's price."""
    def __init__(self, item_id: int, link_id: int):
        self.item_id = item_id
        self.link_id = link_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)        # tests replace this to pretend it's another day


def now() -> str:
    """The time to store. Always UTC: one unambiguous clock in the database,
    turned into local time only when a person's calendar matters."""
    return _utcnow().isoformat(timespec="seconds")


def local_zone() -> ZoneInfo:
    """The default calendar, for anyone without their own time zone.
    ONTRACK_TIMEZONE takes a name from the time zone database ("Asia/Kolkata",
    "America/New_York"). Each person's own time zone is in users.timezone."""
    return ZoneInfo(os.getenv("ONTRACK_TIMEZONE", "Asia/Kolkata"))


def user_zone(conn, uid: int) -> ZoneInfo:
    row = conn.execute("SELECT timezone FROM users WHERE id = ?", (uid,)).fetchone()
    try:
        return ZoneInfo(row["timezone"]) if row else local_zone()
    except Exception:
        return local_zone()


def local_month(stamp: str | None, zone: ZoneInfo) -> str | None:
    """'2026-10-31T19:00:00+00:00' -> '2026-11' in India (it's already 00:30 on
    1 Nov there), but '2026-10' in UTC."""
    if not stamp:
        return None
    moment = datetime.fromisoformat(stamp)
    if moment.tzinfo is None:                # written without a zone: it was UTC
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(zone).strftime("%Y-%m")


def local_date(stamp: str | None, zone: ZoneInfo) -> date | None:
    """The calendar day a stored UTC time falls on, in this time zone."""
    if not stamp:
        return None
    moment = datetime.fromisoformat(stamp)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(zone).date()


def today_in(zone: ZoneInfo) -> date:
    return _utcnow().astimezone(zone).date()


# ------------------------------------------------------------- store logs
#
# One log line per store page: which store, who downloaded the page, what it
# gave, why not, and how long it took. On purpose NOT in it: the full link
# (with Accounts it would show what people shop for; the link id finds it in
# the database), the page itself, request headers, and so never the API key.
#
#   store  link=21  host=in.savana.com  via=server  result=blocked  reason="Store returned HTTP 471 (blocked or not found)"  took=1.2s

REASON_MAX = 160


def _result(p: Product) -> str:
    """One word for what a try gave, easy to search for in the logs."""
    if p.ok:
        return "ok"
    error = p.error or ""
    if error.startswith("Store returned HTTP"):
        return "blocked"
    if error.startswith("Network error"):
        return "network"
    if error.startswith("OnTrack won't open"):
        return "refused"
    return "no-price"


def _reason(error: str | None) -> str | None:
    """The error, made safe for a log line: no web addresses (curl's messages
    can contain the full link), one line, not too long, no stray quotes."""
    if not error:
        return None
    text = re.sub(r"https?://\S+", "<link>", error)
    text = " ".join(text.split()).replace('"', "'")
    return text[:REASON_MAX]


def _timed(via: str, fn: ExtractFn) -> ExtractFn:
    """Wrap an extractor so its result remembers who downloaded the page
    ("server", or "upload" for the phone and the extension) and how long it
    took. Wrapping twice does nothing, so callers can wrap without checking."""
    if getattr(fn, "timed", False):
        return fn

    def run(url: str) -> Product:
        start = time.monotonic()
        p = fn(url)
        attempt = {"via": via, "host": urlsplit(p.url or url).netloc or "?", "result": _result(p),
                   "price": p.price, "reason": _reason(p.error), "took": time.monotonic() - start}
        return replace(p, attempts=[*p.attempts, attempt])   # a copy: never edit a shared result
    run.timed = True
    return run


def _log_checks(link_id: int, p: Product) -> None:
    """Write one line per try that led to this link's result."""
    for a in p.attempts or [{"via": "?", "host": urlsplit(p.url or "").netloc or "?",
                             "result": _result(p), "price": p.price, "reason": _reason(p.error),
                             "took": None}]:
        parts = [f"link={link_id}", f"host={a['host']}", f"via={a['via']}", f"result={a['result']}"]
        if a["price"] is not None:
            parts.append(f"price={a['price']:g}")
        if a["reason"] and a["result"] != "ok":
            parts.append(f'reason="{a["reason"]}"')
        if a["took"] is not None:
            parts.append(f"took={a['took']:.1f}s")
        log.info("store    %s", "  ".join(parts))


def _server_extract(url: str) -> Product:
    # A fresh session per call: curl_cffi sessions aren't safe to share
    # across the threads that refresh() runs extractions on.
    return extract(url, make_fetcher())


# The server downloads the page itself.
default_extract = _timed("server", _server_extract)

# Stores whose pages must be downloaded on the phone, because they block
# requests from servers (bot-checks). The server never fetches these: not when
# refreshing, and not as a fallback. If another store starts blocking the
# server (likely candidates once deployed: Flipkart, Myntra), add it here.
PHONE_ONLY_STORES = ("amazon.", "amzn.")


def needs_phone(url: str | None) -> bool:
    host = urlsplit(url or "").netloc
    return any(store in host for store in PHONE_ONLY_STORES)


def extract_from_html(html: str, fallback: ExtractFn | None = None) -> ExtractFn:
    """Read a page the phone already fetched. If that gives no price and the
    store isn't Amazon, let the server fetch the page itself instead."""
    from_page = _timed("upload", lambda u: extract(u, html_fetcher(u, html)))
    from_server = _timed("server", fallback) if fallback else None

    def run(url: str) -> Product:
        p = from_page(url)
        if not (p.ok or from_server is None or needs_phone(url) or needs_phone(p.url)):
            tried = p.attempts
            p = from_server(url)
            p = replace(p, attempts=[*tried, *p.attempts])    # log both tries
        return _browser_page_wording(p)
    run.timed = True
    return run


def _browser_page_wording(p: Product) -> Product:
    """Wording for a page the phone or the extension sent. The extension sends the
    finished page, after its JavaScript ran, so "probably loads its price with
    JavaScript" is simply wrong there (the Tira case); the phone's download may
    or may not have it. Both are covered by the plain truth: not a single
    product page, or a store OnTrack can't read yet. This also applies when the
    server's own try came after it and found the same: a name but no price."""
    if not p.ok and p.error == NO_PRICE_JAVASCRIPT:
        return replace(p, error=NO_PRICE_FROM_BROWSER)     # a copy: never edit a shared result
    return p

# ---------------------------------------------------------- budget periods
#
# A budget period runs from the person's reset day (say the 25th, when their
# salary comes in) to the day before the next one: 25 Oct - 24 Nov. Rules:
#   - Every new period starts with the DEFAULT budget (users.budget).
#   - A budget can also be set "just for this period" (periods.custom = 1).
#   - Unspent money doesn't carry over.
#   - Reset day 29-31 in a shorter month: that month's last day.
#   - Changing the reset day counts from its next date AFTER today: this
#     period ends the day before it (so it can be shorter or longer once).
#   - Each period is saved when it starts, with the budget it had, so the
#     history never shifts when the default or the reset day changes later.
#   - "Today" is on the person's own calendar (their time zone).

def _clamped(year: int, month: int, day: int) -> date:
    """The reset day in a given month: the 31st in February is the 28th/29th."""
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def next_reset_after(d: date, day: int) -> date:
    """The first reset date strictly after d."""
    this_month = _clamped(d.year, d.month, day)
    if this_month > d:
        return this_month
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return _clamped(year, month, day)


def last_reset_on_or_before(d: date, day: int) -> date:
    """The most recent reset date, today included."""
    this_month = _clamped(d.year, d.month, day)
    if this_month <= d:
        return this_month
    year, month = (d.year - 1, 12) if d.month == 1 else (d.year, d.month - 1)
    return _clamped(year, month, day)


def _settings(conn, uid: int) -> dict:
    row = conn.execute("SELECT budget, reset_day FROM users WHERE id = ?", (uid,)).fetchone()
    return {"budget": row["budget"], "reset_day": row["reset_day"]}


def current_period(conn, uid: int) -> dict:
    """The period today falls in, saving it (and any missed ones) if needed."""
    zone = user_zone(conn, uid)
    today = today_in(zone)
    t = today.isoformat()
    me = _settings(conn, uid)
    day = me["reset_day"] or 1

    found = conn.execute("SELECT * FROM periods WHERE user_id = ? AND starts_on <= ? AND ends_on >= ?",
                         (uid, t, t)).fetchone()
    if found:
        return dict(found)

    latest = conn.execute("SELECT * FROM periods WHERE user_id = ? ORDER BY starts_on DESC LIMIT 1",
                          (uid,)).fetchone()
    if latest and latest["starts_on"] > t:
        # Today is before the newest saved period: the clock or the time zone
        # moved back (in tests, or a zone change at midnight). Work the
        # period out without saving it.
        start = last_reset_on_or_before(today, day)
        end = min(next_reset_after(today, day), date.fromisoformat(latest["starts_on"])) - timedelta(days=1)
        return {"id": None, "starts_on": min(start, end).isoformat(), "ends_on": end.isoformat(),
                "budget": me["budget"], "custom": 0}

    # Save every period from where the last one ended (or from the latest
    # reset, the first time) up to the one containing today. Not opened for
    # three months? Three periods are saved, each with the default budget.
    start = (date.fromisoformat(latest["ends_on"]) + timedelta(days=1)) if latest \
        else last_reset_on_or_before(today, day)
    while True:
        end = next_reset_after(start, day) - timedelta(days=1)
        # ON CONFLICT: two requests at the same moment can't save it twice
        conn.execute("INSERT INTO periods (user_id, starts_on, ends_on, budget, custom, created_at) "
                     "VALUES (?, ?, ?, ?, 0, ?) ON CONFLICT (user_id, starts_on) DO NOTHING",
                     (uid, start.isoformat(), end.isoformat(), me["budget"], now()))
        if end >= today:
            break
        start = end + timedelta(days=1)
    conn.commit()
    return dict(conn.execute("SELECT * FROM periods WHERE user_id = ? AND starts_on <= ? AND ends_on >= ?",
                             (uid, t, t)).fetchone())


def set_budget(conn, uid: int, amount: float, scope: str = "every") -> None:
    """scope "every": the new default, and this period's budget too.
    scope "once": this period only; the next one starts with the default."""
    period = current_period(conn, uid)
    if scope == "every":
        conn.execute("UPDATE users SET budget = ? WHERE id = ?", (amount, uid))
    if period["id"] is not None:
        conn.execute("UPDATE periods SET budget = ?, custom = ? WHERE id = ?",
                     (amount, 0 if scope == "every" else 1, period["id"]))
    conn.commit()


def set_reset_day(conn, uid: int, day: int) -> None:
    """A new reset day counts from its next date after today: this period now
    ends the day before it. (Today itself counts as gone: picking today's
    date doesn't restart the budget halfway through the day.)"""
    period = current_period(conn, uid)          # saved with the old day first
    conn.execute("UPDATE users SET reset_day = ? WHERE id = ?", (day, uid))
    if period["id"] is not None:
        today = today_in(user_zone(conn, uid))
        end = next_reset_after(today, day) - timedelta(days=1)
        conn.execute("UPDATE periods SET ends_on = ? WHERE id = ?", (end.isoformat(), period["id"]))
    conn.commit()


def _spent_between(items: list[dict], start: str, end: str, zone: ZoneInfo) -> float:
    total = 0.0
    for i in items:
        if i["status"] == "purchased":
            d = local_date(i["purchased_at"], zone)
            if d and start <= d.isoformat() <= end:
                total += i["purchased_price"] or 0
    return total


def period_info(conn, uid: int, period: dict | None = None) -> dict:
    """What the app needs to show about the current period."""
    period = period or current_period(conn, uid)
    me = _settings(conn, uid)
    today = today_in(user_zone(conn, uid))
    return {
        "starts_on": period["starts_on"],
        "ends_on": period["ends_on"],
        "budget": period["budget"],
        "custom": bool(period["custom"]),
        "default_budget": me["budget"],
        "reset_day": me["reset_day"],            # None: not chosen yet (the app reminds you)
        "days_left": (date.fromisoformat(period["ends_on"]) - today).days + 1,
        "days_total": (date.fromisoformat(period["ends_on"]) - date.fromisoformat(period["starts_on"])).days + 1,
    }


def list_periods(conn, uid: int, limit: int = 24) -> list[dict]:
    """Saved periods, newest first, each with what was spent in it."""
    current = current_period(conn, uid)
    zone = user_zone(conn, uid)
    items = list_items(conn, uid)
    rows = conn.execute("SELECT * FROM periods WHERE user_id = ? ORDER BY starts_on DESC LIMIT ?",
                        (uid, limit)).fetchall()
    return [{
        "starts_on": r["starts_on"],
        "ends_on": r["ends_on"],
        "budget": r["budget"],
        "custom": bool(r["custom"]),
        "spent": _spent_between(items, r["starts_on"], r["ends_on"], zone),
        "current": r["id"] == current["id"],
    } for r in rows]


# ------------------------------------------------------------------ writes
def _log_status(conn, item_id, from_status, to_status):
    conn.execute(
        "INSERT INTO status_changes (item_id, from_status, to_status, changed_at) VALUES (?, ?, ?, ?)",
        (item_id, from_status, to_status, now())
    )

def _via(p: Product) -> str | None:
    """Who downloaded the page: 'upload' if the phone or the extension sent one
    (even when the server then tried as well), else 'server'."""
    vias = [a["via"] for a in p.attempts or []]
    return "upload" if "upload" in vias else (vias[-1] if vias else None)


def _record_check(conn: sqlite3.Connection, link_id: int, p: Product, keep_error: bool = False) -> None:
    """Store the result of one extraction attempt on a link.

    keep_error: the refresh found nothing, but the last reading came from the
    phone, which sees the store the way a shopper does. The server's own
    failure (a bot-check, the Singapore version of the page) says less than
    the phone's, so only "when we last tried" is updated."""
    _log_checks(link_id, p)
    if p.ok:
        conn.execute(
            """UPDATE links SET title = COALESCE(?, title), price = ?, mrp = ?,
                   image = COALESCE(?, image), method = ?, last_checked = ?, last_error = NULL,
                   read_via = ?
               WHERE id = ?""",
            (p.title, p.price, p.mrp, p.image, p.method, now(), _via(p), link_id))
        conn.execute(
            "INSERT INTO price_history (link_id, price, mrp, checked_at) VALUES (?, ?, ?, ?)",
            (link_id, p.price, p.mrp, now()))
        # A link saved by hand may be a short link (amzn.in/d/…) we never
        # followed. Once a page is read, store its real, cleaned address, so
        # the duplicate check recognises the product when it's shared again.
        real_url = clean_url(p.url)
        # (Only if this person has no other link with that address already.)
        conn.execute(
            "UPDATE links SET url = ? WHERE id = ? AND url != ? AND NOT EXISTS "
            "(SELECT 1 FROM links AS other WHERE other.url = ? AND other.user_id = links.user_id)",
            (real_url, link_id, real_url, real_url))
    elif keep_error:
        conn.execute("UPDATE links SET last_checked = ? WHERE id = ?", (now(), link_id))
    else:
        # Keep the last known price; just note that this attempt failed.
        conn.execute(
            "UPDATE links SET title = COALESCE(title, ?), last_checked = ?, last_error = ?, read_via = ? "
            "WHERE id = ?",
            (p.title, now(), p.error, _via(p), link_id))
    if p.title:
        # Items saved while nothing could be read are named after their URL.
        # The first check that finds a real title renames them (names you
        # typed yourself never start with "http", so they're left alone).
        conn.execute(
            "UPDATE items SET name = ? WHERE id = (SELECT item_id FROM links WHERE id = ?) "
            "AND name LIKE 'http%'", (p.title, link_id))


def _known_link(conn: sqlite3.Connection, uid: int, url: str) -> sqlite3.Row | None:
    """A link we already have for this URL, or None.

    A known link WITH a price is a real duplicate. A known link WITHOUT a
    price is a stuck one (e.g. Amazon showed the server a bot-check), so we
    return it to be filled in instead of refusing.
    """
    row = conn.execute("SELECT id, item_id, price FROM links WHERE url = ? AND user_id = ?",
                       (url, uid)).fetchone()
    if row and row["price"] is not None:
        raise Duplicate(row["item_id"],row["id"])
    return row


def _fetch_link(conn: sqlite3.Connection, uid: int, url: str,
                extract_fn: ExtractFn) -> tuple[str, Product, sqlite3.Row | None]:
    """Download and read a store page. Only READS the database, so it never
    holds a write lock while we wait for the store (which can take 20+ s).

    Returns the cleaned final URL, what the page said, and the stuck link this
    URL already has (None if the link is new).
    """
    cleaned = clean_url(url)
    stuck = _known_link(conn, uid, cleaned)

    p = _timed("server", extract_fn)(url)      # the slow part: no write lock held here
    final_url = clean_url(p.url or cleaned)   # e.g. amzn.in short link -> amazon.in/dp/...
    return final_url, p, stuck or _known_link(conn, uid, final_url)


def _save_link(conn: sqlite3.Connection, uid: int, item_id: int, final_url: str, p: Product) -> None:
    """Write a link we've already fetched. Fast: milliseconds."""
    link_id = conn.execute(
        "INSERT INTO links (item_id, user_id, url, created_at) VALUES (?, ?, ?, ?) RETURNING id",
        (item_id, uid, final_url, now())).fetchone()["id"]
    _record_check(conn, link_id, p)


def _fill_stuck_link(conn: sqlite3.Connection, stuck: sqlite3.Row, p: Product) -> int:
    """Record a new attempt on a link that had no price (_record_check also
    gives the item its real name if it was still named after its URL)."""
    _record_check(conn, stuck["id"], p)
    return stuck["item_id"]


def create_item_from_link(conn, uid: int, url: str, extract_fn: ExtractFn,
                          name: str | None = None, priority: int = 0) -> int:
    """Paste a link -> new item named after the product.

    If extraction fails the item is still created (with the store's link and
    whatever title we got), so you can type the price yourself instead of
    losing the link. Adding that same link again later (e.g. from the phone)
    fills in the existing item instead of making a second one.

    Order matters: fetch the page FIRST, then write. Writing first would lock
    the database for the whole download, and every other change would fail.
    """
    final_url, p, stuck = _fetch_link(conn, uid, url, extract_fn)
    if stuck:
        item_id = _fill_stuck_link(conn, stuck, p)
        conn.commit()
        return item_id

    item_id = conn.execute(
        "INSERT INTO items (user_id, name, priority, created_at) VALUES (?, ?, ?, ?) RETURNING id",
        (uid, name or p.title or p.url or url, priority, now())).fetchone()["id"]
    _log_status(conn, item_id, None, "planned")  # initial status
    _save_link(conn, uid, item_id, final_url, p)
    conn.commit()
    return item_id


def add_link(conn, uid: int, item_id: int, url: str, extract_fn: ExtractFn) -> None:
    """Attach another store's link to an existing item (Amazon + Fastrack for one watch)."""
    _require_item(conn, uid, item_id)
    final_url, p, stuck = _fetch_link(conn, uid, url, extract_fn)
    if stuck and stuck["item_id"] != item_id:
        raise Duplicate(stuck["item_id"],stuck["id"])      # that link belongs to another item
    if stuck:
        _fill_stuck_link(conn, stuck, p)
    else:
        _save_link(conn, uid, item_id, final_url, p)
    conn.commit()


def create_manual_item(conn, uid: int, name: str, price: float | None, note: str | None = None,
                       priority: int = 0, url: str | None = None) -> int:
    """An item you type in yourself. The optional link is saved WITHOUT
    contacting the store (the point of adding by hand is that the store
    blocked us). It starts with no store price, so Refresh picks it up later,
    and once the store's price arrives it replaces the typed one."""
    link_url = clean_url(url) if url else None
    if link_url and (known := _known_link(conn, uid, link_url)):
        raise Duplicate(known["item_id"], known["id"])     # already saved, even if still stuck

    item_id = conn.execute(
        "INSERT INTO items (user_id, name, manual_price, note, priority, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
        (uid, name, price, note, priority, now())).fetchone()["id"]
    _log_status(conn, item_id, None, "planned")
    if link_url:
        conn.execute("INSERT INTO links (item_id, user_id, url, created_at) VALUES (?, ?, ?, ?)",
                     (item_id, uid, link_url, now()))
    conn.commit()
    return item_id


def update_item(conn, uid: int, item_id: int, **fields) -> None:
    _require_item(conn, uid, item_id)
    old_status = conn.execute("SELECT status FROM items WHERE id = ?", (item_id,)).fetchone()["status"]
    allowed = {"name", "status", "priority", "manual_price", "note", "purchased_price"}
    changes = {k: v for k, v in fields.items() if k in allowed}
    new_status = changes.get("status")                               # NEW: moved up

    if "purchased_price" in changes and (new_status or old_status) != "purchased":
        del changes["purchased_price"]
    if new_status == "purchased" and old_status != "purchased":      # NEW
        changes.setdefault("purchased_price", item_view(conn, uid, item_id)["price"])
        changes["purchased_at"] = now()
    elif old_status == "purchased" and new_status not in (None, "purchased"):  # NEW
        changes["purchased_price"] = None
        changes["purchased_at"] = None

    if changes:
        sets = ", ".join(f"{k} = ?" for k in changes)
        conn.execute(f"UPDATE items SET {sets} WHERE id = ?", (*changes.values(), item_id))
        if new_status is not None and new_status != old_status:
            _log_status(conn, item_id, old_status, new_status)
        conn.commit()


def delete_item(conn, uid: int, item_id: int) -> None:
    _require_item(conn, uid, item_id)
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))   # links + history cascade
    conn.commit()


def delete_link(conn, uid: int, link_id: int) -> None:
    if conn.execute("DELETE FROM links WHERE id = ? AND user_id = ?", (link_id, uid)).rowcount == 0:
        raise NotFound(f"link {link_id}")
    conn.commit()


def _require_item(conn, uid: int, item_id: int) -> None:
    if not conn.execute("SELECT 1 FROM items WHERE id = ? AND user_id = ?", (item_id, uid)).fetchone():
        raise NotFound(f"item {item_id}")


# ------------------------------------------------------------------- reads
def _link_view(row, prices: list) -> dict:
    """One link, given its price history (oldest first)."""
    return {
        "id": row["id"],
        "url": row["url"],
        "title": row["title"],
        "price": row["price"],
        "mrp": row["mrp"],
        "image": row["image"],
        "last_checked": row["last_checked"],
        "last_error": row["last_error"],
        "price_when_saved": prices[0] if prices else None,
        "previous_price": prices[-2] if len(prices) >= 2 else None,
        "lowest_price_seen": min(prices) if prices else None,
    }


def _item_view(row, links: list[dict]) -> dict:
    priced = [l for l in links if l["price"] is not None]
    best = min(priced, key=lambda l: l["price"]) if priced else None
    price = best["price"] if best else row["manual_price"]
    return {
        "id": row["id"],
        "name": row["name"],
        "status": row["status"],
        "purchased_price": row["purchased_price"],
        "purchased_at": row["purchased_at"],
        "priority": row["priority"],
        "note": row["note"],
        "manual_price": row["manual_price"],
        "price": price,                              # cheapest link, else the typed price
        "mrp": best["mrp"] if best else None,
        "best_link_id": best["id"] if best else None,
        "image": next((l["image"] for l in links if l["image"]), None),
        "needs_price": price is None,
        "links": links,
        "created_at": row["created_at"],
    }


def _views(conn, rows) -> list[dict]:
    """Many items at once, in three queries whatever the list's size: the
    items (already read), all their links, and all those links' price history.
    (It used to be one query per item, per link and per history: 74 for a
    33-item list, each a round trip to the database.)"""
    rows = list(rows)
    if not rows:
        return []
    marks = ",".join("?" * len(rows))
    links = conn.execute(f"SELECT * FROM links WHERE item_id IN ({marks}) ORDER BY id",
                         [r["id"] for r in rows]).fetchall()
    history: dict[int, list] = {}
    if links:
        marks = ",".join("?" * len(links))
        for h in conn.execute(f"SELECT link_id, price FROM price_history WHERE link_id IN ({marks}) "
                              "ORDER BY checked_at, id", [l["id"] for l in links]):
            history.setdefault(h["link_id"], []).append(h["price"])
    by_item: dict[int, list] = {}
    for l in links:
        by_item.setdefault(l["item_id"], []).append(_link_view(l, history.get(l["id"], [])))
    return [_item_view(r, by_item.get(r["id"], [])) for r in rows]


def item_view(conn, uid: int, item_id: int) -> dict:
    row = conn.execute("SELECT * FROM items WHERE id = ? AND user_id = ?", (item_id, uid)).fetchone()
    if not row:
        raise NotFound(f"item {item_id}")
    return _views(conn, [row])[0]


def list_items(conn, uid: int, status: str | None = None) -> list[dict]:
    if status:
        rows = conn.execute("SELECT * FROM items WHERE user_id = ? AND status = ? "
                            "ORDER BY priority DESC, id", (uid, status))
    else:
        rows = conn.execute("SELECT * FROM items WHERE user_id = ? ORDER BY priority DESC, id", (uid,))
    return _views(conn, rows.fetchall())


def price_history(conn, uid: int, item_id: int) -> list[dict]:
    _require_item(conn, uid, item_id)
    rows = conn.execute(
        """SELECT price_history.link_id, links.url, price_history.price,
                  price_history.mrp, price_history.checked_at
           FROM price_history JOIN links ON links.id = price_history.link_id
           WHERE links.item_id = ?
           ORDER BY price_history.checked_at, price_history.id""",
        (item_id,)).fetchall()
    return [dict(r) for r in rows]


def summary(conn, uid: int) -> dict:
    """The numbers at the top of the app, for the current budget period."""
    period = current_period(conn, uid)
    budget = period["budget"]
    items = list_items(conn, uid)
    zone = user_zone(conn, uid)
    spent = _spent_between(items, period["starts_on"], period["ends_on"], zone)
    planned = [i for i in items if i["status"] == "planned" and i["price"] is not None]
    # Walk planned items in priority order and mark which still fit the budget.
    running, fits = spent, {}
    for item in planned:
        running += item["price"]
        fits[item["id"]] = budget is None or running <= budget
    for item in items:
        item["fits_budget"] = fits.get(item["id"])

    total = sum(i["price"] for i in planned)
    mrp_total = sum(i["mrp"] or i["price"] for i in planned)
    return {
        "budget": budget,
        "planned_total": total,                       # discounted prices only
        "remaining": None if budget is None else budget - spent - total,
        "spent_this_month": spent,                    # this period's (the name is older than periods)
        "period": period_info(conn, uid, period),
        "mrp_total": mrp_total,
        "savings_vs_mrp": mrp_total - total,
        "planned_count": len(planned),
        "needs_price_count": sum(1 for i in items if i["needs_price"]),
        "items": items,
    }


# ----------------------------------------------------------------- refresh

def _is_due(last_checked: str | None, force: bool) -> bool:
    """A link needs checking if forced, never checked, or checked over an hour ago."""
    if force or not last_checked:
        return True
    return datetime.fromisoformat(last_checked) < datetime.now(timezone.utc) - REFRESH_COOLDOWN


def _needs_check(link, force: bool) -> bool:
    """Due for a check, or still without a price. A link with no price skips the
    cooldown: the last attempt failed (a bot-check, a slow store), and waiting an
    hour before trying again helps nobody. Used by the server's refresh and the
    phone's list alike, so both follow the same rule."""
    return link["price"] is None or _is_due(link["last_checked"], force)

async def refresh(conn, uid: int, extract_fn: ExtractFn, force: bool = False,
                  item_id: int | None = None, delay: tuple[float, float] | None = None) -> dict:
    """Re-check prices. Skips links checked within REFRESH_COOLDOWN unless force=True
    (links still without a price are always retried), and links from phone-only
    stores (Amazon), which the phone refreshes instead.

    Fetching runs on worker threads (the extractor is ordinary blocking code),
    at most REFRESH_CONCURRENCY at a time, with a small random pause before
    each request so we don't hit a store with a burst that looks like a bot.
    Database writes happen back on this thread, one at a time.
    """
    delay = REFRESH_DELAY if delay is None else delay
    query = ("SELECT links.id, links.url, links.price, links.last_checked, links.read_via FROM links "
             "JOIN items ON items.id = links.item_id WHERE items.status != 'purchased' "
             "AND items.user_id = ?")
    params = (uid,)
    if item_id is not None:
        _require_item(conn, uid, item_id)
        query, params = query + " AND links.item_id = ?", (uid, item_id)
    links = conn.execute(query, params).fetchall()
    phone_only = [l for l in links if needs_phone(l["url"])]
    links = [l for l in links if not needs_phone(l["url"])]

    due = [l for l in links if _needs_check(l, force)]

    gate = asyncio.Semaphore(REFRESH_CONCURRENCY)

    async def check(link):
        async with gate:
            if delay[1] > 0:
                await asyncio.sleep(random.uniform(*delay))
            return link, await asyncio.to_thread(_timed("server", extract_fn), link["url"])

    results = await asyncio.gather(*(check(l) for l in due))

    changes, failed = [], []
    for link, p in results:
        _record_check(conn, link["id"], p, keep_error=not p.ok and link["read_via"] == "upload")
        if not p.ok:
            failed.append({"link_id": link["id"], "error": p.error})
        elif link["price"] is not None and p.price != link["price"]:
            changes.append({"link_id": link["id"], "old_price": link["price"], "new_price": p.price})
    conn.commit()
    return {"checked": len(due), "skipped_recent": len(links) - len(due),
            "phone_only": len(phone_only), "changed": changes, "failed": failed}

def phone_refresh_list(conn, uid: int, force: bool = False) -> list[dict]:
    """Amazon links the phone should re-download: not bought, and either due for
    a check or still without a price. A link with no price skips the cooldown:
    a failed attempt (e.g. a bot-check page) shouldn't make us wait an hour."""
    rows = conn.execute(
        "SELECT links.id, links.url, links.price, links.last_checked FROM links "
        "JOIN items ON items.id = links.item_id WHERE items.status != 'purchased' "
        "AND items.user_id = ? ORDER BY links.id", (uid,)).fetchall()
    return [{"link_id": r["id"], "url": r["url"]} for r in rows
            if needs_phone(r["url"]) and _needs_check(r, force)]


def refresh_link_from_html(conn, uid: int, link_id: int, html: str) -> dict:
    """Record a price check from a page the phone downloaded for this link."""
    row = conn.execute("SELECT url, price FROM links WHERE id = ? AND user_id = ?", (link_id, uid)).fetchone()
    if not row:
        raise NotFound(f"link {link_id}")
    p = extract_from_html(html)(row["url"])           # no fallback: this is the Amazon path
    _record_check(conn, link_id, p)
    conn.commit()
    return {"link_id": link_id, "ok": p.ok, "old_price": row["price"],
            "new_price": p.price, "error": p.error}