"""
Database layer: eight tables, on SQLite (my laptop) or Postgres (deployed).

Which one is decided by the DATABASE_URL setting:
  not set                      -> SQLite file (ONTRACK_DB, default ontrack.db)
  postgresql://user:pw@host/db -> Postgres

  users          one row per person: email, password hash, budget, currency,
                 country and time zone
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

import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE,     -- always stored lower-case
    name          TEXT    NOT NULL,
    password_hash TEXT    NOT NULL,            -- scrypt, never the password itself
    is_admin      INTEGER NOT NULL DEFAULT 0,  -- the owner: can invite people
    budget        DOUBLE PRECISION,            -- monthly budget, NULL until set
    currency      TEXT    NOT NULL DEFAULT 'INR',
    country       TEXT    NOT NULL DEFAULT 'IN',
    timezone      TEXT    NOT NULL DEFAULT 'Asia/Kolkata',
    created_at    TEXT    NOT NULL
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


class PgConnection:
    """A Postgres connection that looks like our SQLite one, so services.py
    doesn't need to know which database it's talking to: same execute(),
    same ? placeholders, rows readable as row["price"], commit(), close()."""

    def __init__(self, url: str):
        import psycopg                       # only needed when Postgres is used
        from psycopg.rows import dict_row
        self.raw = psycopg.connect(url, row_factory=dict_row)

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
        self.raw.close()


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
    """
    pg = isinstance(conn, PgConnection)
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
