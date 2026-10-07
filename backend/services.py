"""
Business logic: everything the app *does*, independent of HTTP.

main.py only translates web requests into calls to these functions. Keeping
them apart means the rules (cheapest link wins, what fits the budget, refresh
cooldown) can be tested directly, and a future Telegram bot or CLI could reuse
them unchanged.

`extract_fn` is passed in rather than imported, so tests can supply a fake
that never touches the internet.
"""

from __future__ import annotations

import asyncio
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Callable
from urllib.parse import urlsplit

from extractor import Product, clean_url, extract, html_fetcher, make_fetcher

ExtractFn = Callable[[str], Product]

REFRESH_COOLDOWN = timedelta(hours=1)   # skip links checked more recently than this
REFRESH_CONCURRENCY = 3                 # at most 3 store pages being fetched at once
REFRESH_DELAY = (0.5, 1.5)              # random pause (seconds) before each fetch


class NotFound(Exception):
    pass


class Duplicate(Exception):
    def __init__(self, item_id: int):
        self.item_id = item_id


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_extract(url: str) -> Product:
    # A fresh session per call: curl_cffi sessions aren't safe to share
    # across the threads that refresh() runs extractions on.
    return extract(url, make_fetcher())

def _is_amazon(url: str | None) -> bool:
    host = urlsplit(url or "").netloc
    return "amazon." in host or "amzn." in host


def extract_from_html(html: str, fallback: ExtractFn | None = None) -> ExtractFn:
    """Read a page the phone already fetched. If that gives no price and the
    store isn't Amazon, let the server fetch the page itself instead."""
    def run(url: str) -> Product:
        p = extract(url, html_fetcher(url, html))
        if p.ok or fallback is None or _is_amazon(url) or _is_amazon(p.url):
            return p
        return fallback(url)
    return run

# ------------------------------------------------------------------ budget

def get_budget(conn: sqlite3.Connection) -> float | None:
    row = conn.execute("SELECT value FROM settings WHERE key = 'budget'").fetchone()
    return float(row["value"]) if row else None


def set_budget(conn: sqlite3.Connection, amount: float) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('budget', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (str(amount),))
    conn.commit()


# ------------------------------------------------------------------ writes
def _log_status(conn, item_id, from_status, to_status):
    conn.execute(
        "INSERT INTO status_changes (item_id, from_status, to_status, changed_at) VALUES (?, ?, ?, ?)",
        (item_id, from_status, to_status, now())
    )

def _record_check(conn: sqlite3.Connection, link_id: int, p: Product) -> None:
    """Store the result of one extraction attempt on a link."""
    if p.ok:
        conn.execute(
            """UPDATE links SET title = COALESCE(?, title), price = ?, mrp = ?,
                   image = COALESCE(?, image), method = ?, last_checked = ?, last_error = NULL
               WHERE id = ?""",
            (p.title, p.price, p.mrp, p.image, p.method, now(), link_id))
        conn.execute(
            "INSERT INTO price_history (link_id, price, mrp, checked_at) VALUES (?, ?, ?, ?)",
            (link_id, p.price, p.mrp, now()))
        # A link saved by hand may be a short link (amzn.in/d/…) we never
        # followed. Once a page is read, store its real, cleaned address, so
        # the duplicate check recognises the product when it's shared again.
        real_url = clean_url(p.url)
        conn.execute(
            "UPDATE links SET url = ? WHERE id = ? AND url != ? "
            "AND NOT EXISTS (SELECT 1 FROM links WHERE url = ?)",
            (real_url, link_id, real_url, real_url))
    else:
        # Keep the last known price; just note that this attempt failed.
        conn.execute(
            "UPDATE links SET title = COALESCE(title, ?), last_checked = ?, last_error = ? WHERE id = ?",
            (p.title, now(), p.error, link_id))
    if p.title:
        # Items saved while nothing could be read are named after their URL.
        # The first check that finds a real title renames them (names you
        # typed yourself never start with "http", so they're left alone).
        conn.execute(
            "UPDATE items SET name = ? WHERE id = (SELECT item_id FROM links WHERE id = ?) "
            "AND name LIKE 'http%'", (p.title, link_id))


def _known_link(conn: sqlite3.Connection, url: str) -> sqlite3.Row | None:
    """A link we already have for this URL, or None.

    A known link WITH a price is a real duplicate. A known link WITHOUT a
    price is a stuck one (e.g. Amazon showed the server a bot-check), so we
    return it to be filled in instead of refusing.
    """
    row = conn.execute("SELECT id, item_id, price FROM links WHERE url = ?", (url,)).fetchone()
    if row and row["price"] is not None:
        raise Duplicate(row["item_id"])
    return row


def _fetch_link(conn: sqlite3.Connection, url: str,
                extract_fn: ExtractFn) -> tuple[str, Product, sqlite3.Row | None]:
    """Download and read a store page. Only READS the database, so it never
    holds a write lock while we wait for the store (which can take 20+ s).

    Returns the cleaned final URL, what the page said, and the stuck link this
    URL already has (None if the link is new).
    """
    cleaned = clean_url(url)
    stuck = _known_link(conn, cleaned)

    p = extract_fn(url)                        # the slow part: no write lock held here
    final_url = clean_url(p.url or cleaned)   # e.g. amzn.in short link -> amazon.in/dp/...
    return final_url, p, stuck or _known_link(conn, final_url)


def _save_link(conn: sqlite3.Connection, item_id: int, final_url: str, p: Product) -> None:
    """Write a link we've already fetched. Fast: milliseconds."""
    cur = conn.execute("INSERT INTO links (item_id, url, created_at) VALUES (?, ?, ?)",
                       (item_id, final_url, now()))
    _record_check(conn, cur.lastrowid, p)


def _fill_stuck_link(conn: sqlite3.Connection, stuck: sqlite3.Row, p: Product) -> int:
    """Record a new attempt on a link that had no price (_record_check also
    gives the item its real name if it was still named after its URL)."""
    _record_check(conn, stuck["id"], p)
    return stuck["item_id"]


def create_item_from_link(conn, url: str, extract_fn: ExtractFn,
                          name: str | None = None, priority: int = 0) -> int:
    """Paste a link -> new item named after the product.

    If extraction fails the item is still created (with the store's link and
    whatever title we got), so you can type the price yourself instead of
    losing the link. Adding that same link again later (e.g. from the phone)
    fills in the existing item instead of making a second one.

    Order matters: fetch the page FIRST, then write. Writing first would lock
    the database for the whole download, and every other change would fail.
    """
    final_url, p, stuck = _fetch_link(conn, url, extract_fn)
    if stuck:
        item_id = _fill_stuck_link(conn, stuck, p)
        conn.commit()
        return item_id

    cur = conn.execute("INSERT INTO items (name, priority, created_at) VALUES (?, ?, ?)",
                       (name or p.title or p.url or url, priority, now()))
    item_id = cur.lastrowid
    _log_status(conn, item_id, None, "planned")  # initial status
    _save_link(conn, item_id, final_url, p)
    conn.commit()
    return item_id


def add_link(conn, item_id: int, url: str, extract_fn: ExtractFn) -> None:
    """Attach another store's link to an existing item (Amazon + Fastrack for one watch)."""
    _require_item(conn, item_id)
    final_url, p, stuck = _fetch_link(conn, url, extract_fn)
    if stuck and stuck["item_id"] != item_id:
        raise Duplicate(stuck["item_id"])      # that link belongs to another item
    if stuck:
        _fill_stuck_link(conn, stuck, p)
    else:
        _save_link(conn, item_id, final_url, p)
    conn.commit()


def create_manual_item(conn, name: str, price: float | None, note: str | None = None,
                       priority: int = 0, url: str | None = None) -> int:
    """An item you type in yourself. The optional link is saved WITHOUT
    contacting the store (the point of adding by hand is that the store
    blocked us). It starts with no store price, so Refresh picks it up later,
    and once the store's price arrives it replaces the typed one."""
    link_url = clean_url(url) if url else None
    if link_url and (known := _known_link(conn, link_url)):
        raise Duplicate(known["item_id"])     # already saved, even if still stuck

    cur = conn.execute(
        "INSERT INTO items (name, manual_price, note, priority, created_at) VALUES (?, ?, ?, ?, ?)",
        (name, price, note, priority, now()))
    item_id = cur.lastrowid
    _log_status(conn, item_id, None, "planned")
    if link_url:
        conn.execute("INSERT INTO links (item_id, url, created_at) VALUES (?, ?, ?)",
                     (item_id, link_url, now()))
    conn.commit()
    return item_id


def update_item(conn, item_id: int, **fields) -> None:
    _require_item(conn, item_id)
    old_status = conn.execute("SELECT status FROM items WHERE id = ?", (item_id,)).fetchone()["status"]
    allowed = {"name", "status", "priority", "manual_price", "note", "purchased_price"}
    changes = {k: v for k, v in fields.items() if k in allowed}
    new_status = changes.get("status")                               # NEW: moved up

    if "purchased_price" in changes and (new_status or old_status) != "purchased":
        del changes["purchased_price"]
    if new_status == "purchased" and old_status != "purchased":      # NEW
        changes.setdefault("purchased_price", item_view(conn, item_id)["price"])
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


def delete_item(conn, item_id: int) -> None:
    _require_item(conn, item_id)
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))   # links + history cascade
    conn.commit()


def delete_link(conn, link_id: int) -> None:
    if conn.execute("DELETE FROM links WHERE id = ?", (link_id,)).rowcount == 0:
        raise NotFound(f"link {link_id}")
    conn.commit()


def _require_item(conn, item_id: int) -> None:
    if not conn.execute("SELECT 1 FROM items WHERE id = ?", (item_id,)).fetchone():
        raise NotFound(f"item {item_id}")


# ------------------------------------------------------------------- reads
def _link_view(conn, row: sqlite3.Row) -> dict:
    hist = conn.execute(
        "SELECT price FROM price_history WHERE link_id = ? ORDER BY checked_at, id", (row["id"],)
    ).fetchall()
    prices = [h["price"] for h in hist]
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


def item_view(conn, item_id: int) -> dict:
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise NotFound(f"item {item_id}")
    links = [_link_view(conn, l) for l in conn.execute(
        "SELECT * FROM links WHERE item_id = ? ORDER BY id", (item_id,))]

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


def list_items(conn, status: str | None = None) -> list[dict]:
    if status:
        rows = conn.execute("SELECT id FROM items WHERE status = ? ORDER BY priority DESC, id", (status,))
    else:
        rows = conn.execute("SELECT id FROM items ORDER BY priority DESC, id")
    ids = [r["id"] for r in rows]
    return [item_view(conn, i) for i in ids]


def price_history(conn, item_id: int) -> list[dict]:
    _require_item(conn, item_id)
    rows = conn.execute(
        """SELECT price_history.link_id, links.url, price_history.price,
                  price_history.mrp, price_history.checked_at
           FROM price_history JOIN links ON links.id = price_history.link_id
           WHERE links.item_id = ?
           ORDER BY price_history.checked_at, price_history.id""",
        (item_id,)).fetchall()
    return [dict(r) for r in rows]


def summary(conn) -> dict:
    """The numbers at the top of the app."""
    budget = get_budget(conn)
    items = list_items(conn)
    month = now()[:7]                                   # e.g. "2026-10"
    spent = sum(i["purchased_price"] or 0 for i in items
                if i["status"] == "purchased" and (i["purchased_at"] or "").startswith(month))
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
        "spent_this_month": spent,
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

async def refresh(conn, extract_fn: ExtractFn, force: bool = False,
                  item_id: int | None = None, delay: tuple[float, float] | None = None) -> dict:
    """Re-check prices. Skips links checked within REFRESH_COOLDOWN unless force=True.

    Fetching runs on worker threads (the extractor is ordinary blocking code),
    at most REFRESH_CONCURRENCY at a time, with a small random pause before
    each request so we don't hit a store with a burst that looks like a bot.
    Database writes happen back on this thread, one at a time.
    """
    delay = REFRESH_DELAY if delay is None else delay
    query = ("SELECT links.id, links.url, links.price, links.last_checked FROM links "
             "JOIN items ON items.id = links.item_id WHERE items.status != 'purchased'")
    params = ()
    if item_id is not None:
        _require_item(conn, item_id)
        query, params = query + " AND links.item_id = ?", (item_id,)
    links = conn.execute(query, params).fetchall()

    due = [l for l in links if _is_due(l["last_checked"], force)]

    gate = asyncio.Semaphore(REFRESH_CONCURRENCY)

    async def check(link):
        async with gate:
            if delay[1] > 0:
                await asyncio.sleep(random.uniform(*delay))
            return link, await asyncio.to_thread(extract_fn, link["url"])

    results = await asyncio.gather(*(check(l) for l in due))

    changes, failed = [], []
    for link, p in results:
        _record_check(conn, link["id"], p)
        if not p.ok:
            failed.append({"link_id": link["id"], "error": p.error})
        elif link["price"] is not None and p.price != link["price"]:
            changes.append({"link_id": link["id"], "old_price": link["price"], "new_price": p.price})
    conn.commit()
    return {"checked": len(due), "skipped_recent": len(links) - len(due),
            "changed": changes, "failed": failed}

def phone_refresh_list(conn, force: bool = False) -> list[dict]:
    """Amazon links the phone should re-download: not bought, and either due for
    a check or still without a price. A link with no price skips the cooldown:
    a failed attempt (e.g. a bot-check page) shouldn't make us wait an hour."""
    rows = conn.execute(
        "SELECT links.id, links.url, links.price, links.last_checked FROM links "
        "JOIN items ON items.id = links.item_id WHERE items.status != 'purchased' ORDER BY links.id"
    ).fetchall()
    return [{"link_id": r["id"], "url": r["url"]} for r in rows
            if _is_amazon(r["url"]) and (r["price"] is None or _is_due(r["last_checked"], force))]


def refresh_link_from_html(conn, link_id: int, html: str) -> dict:
    """Record a price check from a page the phone downloaded for this link."""
    row = conn.execute("SELECT url, price FROM links WHERE id = ?", (link_id,)).fetchone()
    if not row:
        raise NotFound(f"link {link_id}")
    p = extract_from_html(html)(row["url"])           # no fallback: this is the Amazon path
    _record_check(conn, link_id, p)
    conn.commit()
    return {"link_id": link_id, "ok": p.ok, "old_price": row["price"],
            "new_price": p.price, "error": p.error}