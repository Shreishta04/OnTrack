"""
Database layer: one SQLite file, five tables.

  settings       key/value pairs (the monthly budget lives here)
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
"""

from __future__ import annotations

import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'planned',  -- 'planned' | 'later' | 'purchased'
    priority     INTEGER NOT NULL DEFAULT 0,   -- higher = buy first
    manual_price REAL,                         -- used only when no link has a price
    note         TEXT,
    purchased_price REAL,                      -- what you actually paid
    purchased_at TEXT,                         -- when you actually bought it
    created_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS links (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id      INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    url          TEXT    NOT NULL UNIQUE,      -- cleaned URL, so the same product can't be saved twice
    title        TEXT,
    price        REAL,                         -- what you'd pay (latest successful check)
    mrp          REAL,                         -- struck-through price, if the store shows one
    image        TEXT,
    method       TEXT,                         -- which extractor strategy worked
    last_checked TEXT,                         -- when we last TRIED (success or not)
    last_error   TEXT,                         -- why the last try failed, NULL if it worked
    created_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS price_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    link_id    INTEGER NOT NULL REFERENCES links(id) ON DELETE CASCADE,
    price      REAL    NOT NULL,
    mrp        REAL,
    checked_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS status_changes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id    INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    from_status TEXT,
    to_status   TEXT   NOT NULL,
    changed_at  TEXT   NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_links_item   ON links(item_id);
CREATE INDEX IF NOT EXISTS idx_history_link ON price_history(link_id, checked_at);
"""


def db_path() -> str:
    return os.getenv("ONTRACK_DB", "ontrack.db")


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row          # rows behave like dicts: row["price"]
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite ignores REFERENCES/CASCADE unless this is on
    return conn


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
