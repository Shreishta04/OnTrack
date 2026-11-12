"""Alerts on your phone: what to say, when, and to which phones.

Four kinds, each switched on or off in Settings → Notifications:

    price_drop     a price went down          "Kurta: ↓ ₹899 (was ₹1,099)"
    back_in_stock  it was out of stock, now has a price again
    budget_reset   the last day of a budget period: "starts again tomorrow"
    waiting        weekly (Mondays): things on the list for two weeks or more

How an alert travels:
1. queue()  writes it to the alerts table. Its dedupe key makes sure the same
            news is only ever queued once, however many times prices are checked.
2. flush()  sends what's waiting to every phone of that person, through
            Firebase (fcm.py). Between 22:00 and 08:00 on their own clock it
            waits instead, and the first flush after 8 am sends it.
3. tick()   runs every hour (GitHub Actions calls /cron/tick). At 9 am on each
            person's clock it does their daily round: check prices, add the
            reminders, then flush for everyone (which releases the morning's
            held alerts).

Nothing is queued for someone without a phone set up for alerts, so turning
alerts on later never brings a pile of old news.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Callable

import replies
import services

KINDS = ("price_drop", "budget_reset", "waiting", "back_in_stock")
QUIET_FROM, QUIET_UNTIL = 22, 8      # no alerts from 10 pm to 8 am, local time
DAILY_HOUR = 9                       # the daily round: 9 am local time
WAITING_DAYS = 14                    # "still on your list" after two weeks
MAX_SEPARATE = 3                     # more waiting at once than this: one alert that lists them
EXPIRE = timedelta(hours=24)         # news older than this isn't worth a buzz

Sender = Callable[[str, dict], str]  # (device token, message) -> "ok" | "gone" | "error"


# ------------------------------------------------------------------ settings

def settings(conn, uid: int) -> dict[str, bool]:
    row = conn.execute("SELECT notify FROM users WHERE id = ?", (uid,)).fetchone()
    on = set((row["notify"] or "").split(",")) if row else set()
    return {kind: kind in on for kind in KINDS}


def set_settings(conn, uid: int, changes: dict[str, bool]) -> dict[str, bool]:
    now_on = {**settings(conn, uid), **{k: bool(v) for k, v in changes.items() if k in KINDS}}
    conn.execute("UPDATE users SET notify = ? WHERE id = ?",
                 (",".join(k for k in KINDS if now_on[k]), uid))
    # Switched off: anything of that kind still waiting is dropped too.
    off = [k for k in KINDS if not now_on[k]]
    if off:
        conn.execute(f"DELETE FROM alerts WHERE user_id = ? AND sent_at IS NULL "
                     f"AND kind IN ({','.join('?' * len(off))})", (uid, *off))
    conn.commit()
    return now_on


# ------------------------------------------------------------------- phones

def add_device(conn, uid: int, token: str, platform: str | None) -> None:
    """Remember a phone's Firebase token. A token that belonged to someone else
    (a shared phone, a new login) moves to this person."""
    conn.execute("DELETE FROM push_devices WHERE token = ? AND user_id != ?", (token, uid))
    conn.execute("INSERT INTO push_devices (user_id, token, platform, created_at) VALUES (?, ?, ?, ?) "
                 "ON CONFLICT (token) DO NOTHING", (uid, token, platform, services.now()))
    conn.commit()


def remove_device(conn, uid: int, token: str) -> None:
    conn.execute("DELETE FROM push_devices WHERE token = ? AND user_id = ?", (token, uid))
    conn.commit()


def device_count(conn, uid: int) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM push_devices WHERE user_id = ?", (uid,)).fetchone()["n"]


# -------------------------------------------------------------------- queue

def queue(conn, uid: int, kind: str, title: str, body: str, dedupe: str,
          item_id: int | None = None) -> bool:
    """Add one alert, unless that kind is switched off, the person has no phone
    for alerts, or the same news (dedupe key) was queued before. True if added."""
    if kind != "test" and not settings(conn, uid).get(kind):
        return False
    if not device_count(conn, uid):
        return False
    added = conn.execute(
        "INSERT INTO alerts (user_id, kind, item_id, title, body, dedupe, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (user_id, dedupe) DO NOTHING RETURNING id",
        (uid, kind, item_id, title, body, dedupe, services.now())).fetchone()
    return added is not None


def price_checked(conn, link_id: int, before, p) -> None:
    """Called by services._record_check when a page was read successfully.
    `before` is the link as it was: its price and last error."""
    row = conn.execute(
        "SELECT items.id, items.name, items.status, items.user_id, users.currency FROM links "
        "JOIN items ON items.id = links.item_id JOIN users ON users.id = items.user_id "
        "WHERE links.id = ?", (link_id,)).fetchone()
    if not row or row["status"] == "purchased" or p.price is None:
        return
    name, uid, cur = replies.short(row["name"]), row["user_id"], row["currency"]
    day = services.today_in(services.user_zone(conn, uid)).isoformat()
    if before["last_error"] == services.OUT_OF_STOCK:
        queue(conn, uid, "back_in_stock", "Back in stock",
              f"{name} is back: {replies.money(p.price, cur)}",
              f"back_in_stock:{link_id}:{day}", row["id"])
    elif before["price"] is not None and p.price < before["price"] - 0.005:
        queue(conn, uid, "price_drop", "Price dropped",
              f"{name}: ↓ {replies.money(p.price, cur)} (was {replies.money(before['price'], cur)})",
              f"price_drop:{link_id}:{p.price:g}:{day}", row["id"])


# -------------------------------------------------------------------- flush

def _local(conn, uid: int, at: datetime) -> datetime:
    return at.astimezone(services.user_zone(conn, uid))


def is_quiet(local: datetime) -> bool:
    return local.hour >= QUIET_FROM or local.hour < QUIET_UNTIL


def flush(conn, uid: int, send: Sender, at: datetime | None = None, ignore_quiet: bool = False) -> dict:
    """Send this person's waiting alerts to each of their phones."""
    at = at or services._utcnow()
    result = {"sent": 0, "held": 0, "failed": 0}
    # Too old to be news (the phone was off for days, or alerts were held): drop.
    conn.execute("UPDATE alerts SET sent_at = ? WHERE user_id = ? AND sent_at IS NULL AND created_at < ?",
                 ("expired", uid, (at - EXPIRE).isoformat(timespec="seconds")))
    waiting = conn.execute("SELECT * FROM alerts WHERE user_id = ? AND sent_at IS NULL ORDER BY id",
                           (uid,)).fetchall()
    if not waiting:
        conn.commit()
        return result
    if not ignore_quiet and is_quiet(_local(conn, uid, at)):
        conn.commit()
        return {**result, "held": len(waiting)}

    if len(waiting) > MAX_SEPARATE:
        lines = [a["body"] for a in waiting]
        messages = [{"title": f"{len(waiting)} updates from OnTrack",
                     "body": "\n".join(lines[:MAX_SEPARATE] + [f"…and {len(lines) - MAX_SEPARATE} more"]),
                     "tag": "ontrack-many"}]
    else:
        messages = [{"title": a["title"], "body": a["body"], "tag": a["dedupe"]} for a in waiting]

    devices = conn.execute("SELECT id, token FROM push_devices WHERE user_id = ?", (uid,)).fetchall()
    for message in messages:
        for device in devices:
            outcome = send(device["token"], {**message, "url": "/"})
            if outcome == "ok":
                result["sent"] += 1
            elif outcome == "gone":          # app deleted, alerts turned off in iOS Settings…
                conn.execute("DELETE FROM push_devices WHERE id = ?", (device["id"],))
            else:
                result["failed"] += 1
    # Marked as sent even if one phone failed: a retry every hour would buzz the
    # phones that did get it again. (The test button shows failures instead.)
    conn.execute("UPDATE alerts SET sent_at = ? WHERE user_id = ? AND sent_at IS NULL",
                 (at.isoformat(timespec="seconds"), uid))
    conn.commit()
    return result


def send_test(conn, uid: int, send: Sender) -> dict:
    """The "Send a test" button: right away, quiet hours or not."""
    if not device_count(conn, uid):
        return {"sent": 0, "held": 0, "failed": 0, "devices": 0}
    stamp = services.now()
    queue(conn, uid, "test", "OnTrack alerts are on",
          "This is how price drops and reminders will look.", f"test:{stamp}")
    return {**flush(conn, uid, send, ignore_quiet=True), "devices": device_count(conn, uid)}


# --------------------------------------------------------------- daily round

def _reminders(conn, uid: int, today: date) -> None:
    """The two reminders that come from the calendar, not from a price."""
    period = services.current_period(conn, uid)
    if period["ends_on"] == today.isoformat():
        me = conn.execute("SELECT budget, currency FROM users WHERE id = ?", (uid,)).fetchone()
        body = (f"Your budget starts again tomorrow: {replies.money(me['budget'], me['currency'])}."
                if me["budget"] else "A new budget period starts tomorrow.")
        queue(conn, uid, "budget_reset", "New budget tomorrow", body, f"budget_reset:{period['ends_on']}")

    if today.weekday() == 0:                       # Mondays
        cutoff = (services._utcnow() - timedelta(days=WAITING_DAYS)).isoformat(timespec="seconds")
        rows = conn.execute("SELECT name FROM items WHERE user_id = ? AND status = 'planned' "
                            "AND created_at < ? ORDER BY created_at", (uid, cutoff)).fetchall()
        if rows:
            names = [replies.short(r["name"]) for r in rows]
            body = (f"{names[0]} has been on your list for 2+ weeks." if len(names) == 1 else
                    f"{len(names)} things have waited 2+ weeks: " + ", ".join(names[:3])
                    + ("…" if len(names) > 3 else ""))
            queue(conn, uid, "waiting", "Still on your wish list", body, f"waiting:{today.isoformat()}")


async def tick(conn, extract_fn, send: Sender, at: datetime | None = None) -> dict:
    """The hourly job. Each person's daily round runs once a day, at the first
    tick from 9 am on their clock (GitHub can run a scheduled job late)."""
    at = at or services._utcnow()
    done = []
    for user in conn.execute("SELECT id, daily_on FROM users ORDER BY id").fetchall():
        uid = user["id"]
        local = _local(conn, uid, at)
        today = local.date().isoformat()
        if local.hour < DAILY_HOUR or user["daily_on"] == today:
            continue
        conn.execute("UPDATE users SET daily_on = ? WHERE id = ?", (today, uid))   # first: a crash won't loop
        conn.commit()
        try:
            await services.refresh(conn, uid, extract_fn)
            _reminders(conn, uid, local.date())
            conn.commit()
            done.append(uid)
        except Exception as exc:                   # one person's problem doesn't stop the others
            conn.rollback()
            services.log.warning("daily    user=%s failed: %s", uid, exc)
    sent = {"sent": 0, "held": 0, "failed": 0}
    for row in conn.execute("SELECT DISTINCT user_id FROM alerts WHERE sent_at IS NULL").fetchall():
        for k, v in flush(conn, row["user_id"], send, at).items():
            sent[k] += v
    return {"daily_rounds": len(done), **sent}
