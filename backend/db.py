"""
Database layer: eleven tables, on SQLite (my laptop) or Postgres (deployed).

Which one is decided by the DATABASE_URL setting:
  not set                      -> SQLite file (ONTRACK_DB, default ontrack.db)
  postgresql://user:pw@host/db -> Postgres

  users          one row per person: email, password hash, default budget,
                 reset day, currency, country and time zone
  periods        one row per budget period ("25 Oct – 24 Nov"), saved when it
                 starts with the budget it had, so history never shifts when
                 the default budget or the reset day changes later
  tokens         keys that let a phone, the extension or a logged-in browser act
                 as one user; only a hash is stored, so a database leak doesn't
                 leak working keys
  invites        one-time sign-up links (and password-reset links) made by the admin
  settings       key/value pairs; only the old single-user budget, read once
                 when the owner's account is created
  items          things you want to buy ("Smartwatch")
  links          store pages for an item (Amazon AND Fastrack for the watch);
                 an item's price is its cheapest link
  price_history  one row per successful price check, so we can show
                 "↓ ₹40 since you saved it" and the lowest price seen
  status_changes one row per status move (planned → later → planned → purchased),
                 so we can answer "what did I postpone?"

Items and links are separate tables because one thing you want can be sold in
several places. If every link were its own item, the watch would be counted
twice in the budget.

Every item and link carries a user_id. Links carry it too (not only their
item) so the database itself can say "one person can't save the same link
twice" while two different people still can.
"""

from __future__ import annotations

import atexit
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE,     -- always stored lower-case
    name          TEXT    NOT NULL,
    password_hash TEXT    NOT NULL,            -- scrypt, never the password itself
    is_admin      INTEGER NOT NULL DEFAULT 0,  -- the owner: can invite people
    budget        DOUBLE PRECISION,            -- default budget for each period, NULL until set
    reset_day     INTEGER,                     -- 1-31: the day each period starts; NULL until chosen (works as the 1st)
    currency      TEXT    NOT NULL DEFAULT 'INR',
    country       TEXT    NOT NULL DEFAULT 'IN',
    timezone      TEXT    NOT NULL DEFAULT 'Asia/Kolkata',
    notify        TEXT    NOT NULL DEFAULT 'price_drop,budget_reset,waiting,back_in_stock',  -- alerts switched on
    daily_on      TEXT,                        -- local date of the last 9 am round (price check, reminders)
    created_at    TEXT    NOT NULL
);

-- Phones (and browsers) that receive alerts: Firebase gives each one a token.
CREATE TABLE IF NOT EXISTS push_devices (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token      TEXT    NOT NULL UNIQUE,
    platform   TEXT,                          -- iphone / android / computer
    created_at TEXT    NOT NULL
);

-- Alerts waiting to be sent, and those sent (kept so nothing goes out twice).
-- An alert found at night waits until 8 am on the person's own clock.
CREATE TABLE IF NOT EXISTS alerts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind       TEXT    NOT NULL,              -- price_drop / budget_reset / waiting / back_in_stock / test
    item_id    INTEGER,                       -- the item it's about, if any (tapping opens the app)
    title      TEXT    NOT NULL,
    body       TEXT    NOT NULL,
    dedupe     TEXT    NOT NULL,              -- the same dedupe key is only ever queued once
    created_at TEXT    NOT NULL,
    sent_at    TEXT,                          -- NULL: still waiting
    UNIQUE (user_id, dedupe)
);

CREATE TABLE IF NOT EXISTS periods (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    starts_on  TEXT    NOT NULL,             -- first day, on the person's own calendar (YYYY-MM-DD)
    ends_on    TEXT    NOT NULL,             -- last day, included
    budget     DOUBLE PRECISION,             -- this period's budget (NULL: none set)
    custom     INTEGER NOT NULL DEFAULT 0,   -- 1: set "just for this period"
    created_at TEXT    NOT NULL,
    UNIQUE (user_id, starts_on)
);

CREATE TABLE IF NOT EXISTS tokens (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash   TEXT    NOT NULL UNIQUE,      -- SHA-256 of the token
    kind         TEXT    NOT NULL,             -- 'session' (a login) | 'device' (Shortcut, extension)
    name         TEXT    NOT NULL,             -- "Web app", "iPhone Shortcuts", ...
    created_at   TEXT    NOT NULL,
    last_used_at TEXT
);

CREATE TABLE IF NOT EXISTS invites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code_hash   TEXT    NOT NULL UNIQUE,
    created_by  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    for_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,  -- set: a password-reset link
    note        TEXT,                          -- who it's for, so the list makes sense
    created_at  TEXT    NOT NULL,
    expires_at  TEXT    NOT NULL,
    used_at     TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER REFERENCES users(id) ON DELETE CASCADE,  -- NULL only before the owner signs up
    name         TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'planned',  -- 'planned' | 'later' | 'purchased'
    priority     INTEGER NOT NULL DEFAULT 0,   -- higher = buy first
    manual_price DOUBLE PRECISION,                         -- used only when no link has a price
    note         TEXT,
    purchased_price DOUBLE PRECISION,                      -- what you actually paid
    purchased_at TEXT,                         -- when you actually bought it
    created_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS links (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id      INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    user_id      INTEGER REFERENCES users(id) ON DELETE CASCADE,  -- same as the item's
    url          TEXT    NOT NULL,             -- cleaned URL; unique PER PERSON (index below)
    title        TEXT,
    price        DOUBLE PRECISION,                         -- what you'd pay (latest successful check)
    mrp          DOUBLE PRECISION,                         -- struck-through price, if the store shows one
    image        TEXT,
    method       TEXT,                         -- which extractor strategy worked
    last_checked TEXT,                         -- when we last TRIED (success or not)
    last_error   TEXT,                         -- why the last try failed, NULL if it worked
    read_via     TEXT,                         -- who downloaded the page last time: 'server' or 'upload' (phone / extension)
    created_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS price_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    link_id    INTEGER NOT NULL REFERENCES links(id) ON DELETE CASCADE,
    price      DOUBLE PRECISION NOT NULL,
    mrp        DOUBLE PRECISION,
    checked_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS status_changes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id    INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    from_status TEXT,
    to_status   TEXT   NOT NULL,
    changed_at  TEXT   NOT NULL
);
"""

# Indexes come after migrate(): on an old database, user_id doesn't exist
# until migrate() adds it, and an index on a missing column fails.
INDEXES = """
CREATE INDEX IF NOT EXISTS idx_links_item   ON links(item_id);
CREATE INDEX IF NOT EXISTS idx_history_link ON price_history(link_id, checked_at);
CREATE INDEX IF NOT EXISTS idx_items_user   ON items(user_id);
CREATE INDEX IF NOT EXISTS idx_tokens_user  ON tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_periods_user ON periods(user_id, starts_on);
CREATE INDEX IF NOT EXISTS idx_push_user    ON push_devices(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_wait  ON alerts(user_id, sent_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_links_user_url ON links(user_id, url);
"""


def db_path() -> str:
    return os.getenv("ONTRACK_DB", "ontrack.db")


def database_url() -> str | None:
    """The Postgres address, or None for SQLite."""
    return os.getenv("DATABASE_URL") or None


# Postgres spells "a number that counts up by itself" differently. Everything
# else in SCHEMA already works on both, so we translate this one phrase
# instead of keeping two copies of every table.
# BY DEFAULT (not ALWAYS) lets the copy script keep the ids from ontrack.db.
PG_SCHEMA = SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT",
                           "INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY")
# Everything the app creates, in one piece (used by copy_to_postgres.py).
FULL_PG_SCHEMA = PG_SCHEMA + INDEXES


def _to_pg(sql: str) -> str:
    """SQLite writes placeholders as ?, Postgres (psycopg) as %s.
    psycopg also treats a lone % as the start of a placeholder, so a real %
    (as in LIKE 'http%') must be written %%. Order matters: double the
    existing % signs first, then turn ? into %s.
    Our SQL never has a ? inside quotes, so a plain replace is safe."""
    return sql.replace("%", "%%").replace("?", "%s")


# A few open connections kept ready (a "pool"), instead of a new one for
# every request. Opening a connection to Neon is a secure handshake of several
# round trips before the first query; borrowing an open one skips all that.
#   max_size 5     enough for one small server; Neon's free plan allows far more
#   max_idle 240s  close connections unused for 4 minutes, before Neon itself
#                  goes to sleep (5 minutes) and would cut them off
#   check          a quick "still there?" when one is borrowed, so a connection
#                  cut off while idle is replaced instead of failing a request
_POOLS: dict = {}


def close_pools() -> None:
    """Close every pool (the server stopping, or the tests finishing)."""
    for pool in _POOLS.values():
        pool.close()
    _POOLS.clear()


atexit.register(close_pools)


def _pool(url: str):
    if url not in _POOLS:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
        _POOLS[url] = ConnectionPool(url, min_size=0, max_size=5, max_idle=240, open=True,
                                     kwargs={"row_factory": dict_row}, check=ConnectionPool.check_connection)
    return _POOLS[url]


class PgConnection:
    """A Postgres connection that looks like our SQLite one, so services.py
    doesn't need to know which database it's talking to: same execute(),
    same ? placeholders, rows readable as row["price"], commit(), close().
    It's borrowed from the pool, and close() hands it back."""

    def __init__(self, url: str):
        self._pool = _pool(url)
        self.raw = self._pool.getconn()

    def execute(self, sql: str, params=()):
        # Always pass a tuple (even an empty one) so psycopg always reads
        # placeholders, and the %% from _to_pg always turns back into %.
        return self.raw.execute(_to_pg(sql), tuple(params))

    def executescript(self, script: str) -> None:
        self.raw.execute(script)             # no params: several statements at once

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        """Hand the connection back. Anything not committed is rolled back first,
        so the next request never inherits half a change."""
        if self.raw is None:
            return
        try:
            if self.raw.info.transaction_status != 0:   # 0 = idle, nothing open
                self.raw.rollback()
        except Exception:
            pass                                       # a broken one: the pool replaces it
        self._pool.putconn(self.raw)
        self.raw = None


def connect(path: str | None = None):
    url = database_url()
    if url and path is None:
        return PgConnection(url)
    conn = sqlite3.connect(path or db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row          # rows behave like dicts: row["price"]
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite ignores REFERENCES/CASCADE unless this is on
    return conn


def columns(conn, table: str) -> list[str]:
    """Column names of a table, in either database ([] if it doesn't exist)."""
    if isinstance(conn, PgConnection):
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = ? ORDER BY ordinal_position", (table,)).fetchall()
        return [r["column_name"] for r in rows]
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]


# The links table as it was before Accounts, rebuilt on SQLite (see below).
_LINKS_COPY = ("id, item_id, url, title, price, mrp, image, method, "
               "last_checked, last_error, created_at")


def migrate(conn) -> None:
    """Bring a database made before Accounts up to date. Safe to run every
    start: each step checks first and does nothing if it was already done.

    1. items and links get a user_id column (empty until the owner signs up,
       when auth.signup() gives every existing row to them).
    2. links.url stops being unique for the WHOLE table, so two people can
       save the same lipstick. The unique-per-person index in INDEXES
       replaces it.
       Postgres can simply drop the old rule. SQLite can't remove a rule from
       a table, so there we follow SQLite's own recipe: make the new table,
       copy the rows (ids kept, so price history still points at them),
       drop the old one, rename the new one.
    3. (budget periods) users get a reset_day column, empty for everyone at
       first: "not chosen yet", which the app treats as the 1st and reminds
       the person to set. The periods table itself is new, so CREATE TABLE
       IF NOT EXISTS in SCHEMA makes it.
    4. (fix-items) links get a read_via column: who downloaded the page the
       last time ('server', or 'upload' from the phone or the extension).
       Empty for older links.
    """
    pg = isinstance(conn, PgConnection)
    if "reset_day" not in columns(conn, "users"):
        conn.execute("ALTER TABLE users ADD COLUMN reset_day INTEGER")
    if "notify" not in columns(conn, "users"):      # (notifications) every alert on to begin with
        conn.execute("ALTER TABLE users ADD COLUMN notify TEXT NOT NULL "
                     "DEFAULT 'price_drop,budget_reset,waiting,back_in_stock'")
    if "daily_on" not in columns(conn, "users"):
        conn.execute("ALTER TABLE users ADD COLUMN daily_on TEXT")
    if columns(conn, "links") and "read_via" not in columns(conn, "links"):
        conn.execute("ALTER TABLE links ADD COLUMN read_via TEXT")
    if "user_id" not in columns(conn, "items"):
        conn.execute("ALTER TABLE items ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
    if pg:
        if "user_id" not in columns(conn, "links"):
            conn.execute("ALTER TABLE links ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
        # The old rule is usually called links_url_key, but look it up rather
        # than trust the name: any unique rule on url alone must go.
        old_rules = conn.execute(
            "SELECT con.conname FROM pg_constraint con "
            "JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = con.conkey[1] "
            "WHERE con.conrelid = 'links'::regclass AND con.contype = 'u' "
            "AND array_length(con.conkey, 1) = 1 AND att.attname = 'url'").fetchall()
        for rule in old_rules:
            conn.execute(f'ALTER TABLE links DROP CONSTRAINT "{rule["conname"]}"')
    else:
        old = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'links'").fetchone()
        if old and "user_id" not in columns(conn, "links"):
            conn.commit()
            conn.execute("PRAGMA foreign_keys = OFF")      # so DROP TABLE doesn't delete price history
            try:
                links_table = SCHEMA[SCHEMA.index("CREATE TABLE IF NOT EXISTS links"):]
                links_table = links_table[:links_table.index(");") + 2]
                conn.executescript(
                    "BEGIN;"
                    + links_table.replace("IF NOT EXISTS links", "links_new")
                    + f"INSERT INTO links_new ({_LINKS_COPY}) SELECT {_LINKS_COPY} FROM links;"
                    "DROP TABLE links;"
                    "ALTER TABLE links_new RENAME TO links;"
                    "COMMIT;")
            finally:
                conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()


def init(conn) -> None:
    """Create the tables (first run), bring old ones up to date, add indexes."""
    pg = isinstance(conn, PgConnection)
    conn.executescript(PG_SCHEMA if pg else SCHEMA)
    migrate(conn)
    conn.executescript(INDEXES)
    conn.commit()
