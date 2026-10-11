"""
Copy everything from my SQLite file (ontrack.db) into an empty Postgres database.

Run once, before the deployed server starts using Postgres:

    python copy_to_postgres.py "postgresql://user:password@host/dbname"

or with DATABASE_URL already set (for example in .env):

    python copy_to_postgres.py

If this computer can't connect to Postgres (my work laptop blocks psycopg),
write the same copy as a .sql file instead, then paste it into Neon's
SQL Editor in the browser and press Run:

    python copy_to_postgres.py --sql-out ontrack_copy.sql

What it does:
  1. creates the tables in Postgres (the same ones the app creates)
  2. refuses to run if Postgres already has items, so it can't mix two lists
  3. copies every table, KEEPING THE IDS, so links still point at the right
     items, and the Shortcuts' link ids stay the same
  4. moves each id counter to where SQLite's was (otherwise the next new item
     would try to reuse id 1 and fail); ids of deleted rows stay unused, as
     they do on SQLite
  5. checks that every table has the same number of rows on both sides

It all happens in one transaction: if anything goes wrong, nothing is saved.
(The .sql file does the same checks, inside one DO block, which Postgres
also runs all-or-nothing.) The SQLite file is only read, never changed.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys

from dotenv import load_dotenv

import db

# Parents before children: a link needs its item to exist first.
TABLES = ["settings", "items", "links", "price_history", "status_changes"]
WITH_IDS = ["items", "links", "price_history", "status_changes"]   # settings has no id


def _columns(conn, table: str) -> list[str]:
    """Column names of a table, in either database."""
    if isinstance(conn, db.PgConnection):
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = ? ORDER BY ordinal_position", (table,)).fetchall()
        return [r["column_name"] for r in rows]
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]


def _sqlite_counters(src) -> dict[str, int]:
    """SQLite keeps its id counters in a hidden table, sqlite_sequence, and
    never reuses an id, even after a delete."""
    try:
        return {r["name"]: r["seq"] for r in src.execute("SELECT name, seq FROM sqlite_sequence")}
    except sqlite3.OperationalError:                     # no rows ever added: no counters yet
        return {}


def _open_sqlite(sqlite_path: str):
    if not os.path.exists(sqlite_path):
        raise SystemExit(f"Can't find {sqlite_path}. Run this from the backend folder.")
    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row
    return src


def copy(sqlite_path: str, pg_url: str) -> dict[str, int]:
    """Copy all tables; returns {table: rows copied}. Raises on any problem."""
    src = _open_sqlite(sqlite_path)
    dst = db.PgConnection(pg_url)
    try:
        db.init(dst)                                   # create tables if missing
        existing = dst.execute("SELECT COUNT(*) AS n FROM items").fetchone()["n"]
        if existing:
            raise SystemExit(f"Postgres already has {existing} items. "
                             "Copy only into an empty database.")

        copied = {}
        for table in TABLES:
            # Only columns both sides have (an old ontrack.db may lack a newer one).
            cols = [c for c in _columns(src, table) if c in _columns(dst, table)]
            names = ", ".join(cols)
            marks = ", ".join("?" for _ in cols)
            rows = src.execute(f"SELECT {names} FROM {table}").fetchall()
            for row in rows:
                dst.execute(f"INSERT INTO {table} ({names}) VALUES ({marks})", tuple(row))
            copied[table] = len(rows)

        # Move each id counter to where SQLite's was (highest copied id as fallback).
        counters = _sqlite_counters(src)
        for table in WITH_IDS:
            top = dst.execute(f"SELECT COALESCE(MAX(id), 0) AS n FROM {table}").fetchone()["n"]
            last = max(top, counters.get(table, 0))
            if last:                                     # empty table: leave the counter at 1
                dst.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), {int(last)})")

        # Same number of rows on both sides, or nothing is saved.
        for table in TABLES:
            n = dst.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            if n != copied[table]:
                raise RuntimeError(f"{table}: copied {copied[table]} rows but Postgres has {n}")

        dst.commit()
        return copied
    except BaseException:
        dst.rollback()
        raise
    finally:
        dst.close()
        src.close()


def _literal(value) -> str:
    """One value written as SQL text: NULL, a number, or a 'quoted string'.
    Inside a string, a ' is written twice ('Levi''s'); nothing else needs escaping."""
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


TAG = "$ontrack_copy$"     # marks the start and end of the DO block's body


def to_sql(sqlite_path: str) -> tuple[str, dict[str, int]]:
    """The whole copy as one SQL script, for computers that can't connect to
    Postgres directly. Returns (script, {table: rows})."""
    src = _open_sqlite(sqlite_path)
    fresh = sqlite3.connect(":memory:")                  # the tables as the app makes them today,
    fresh.row_factory = sqlite3.Row                      # to know which columns Postgres will have
    fresh.executescript(db.SCHEMA)
    try:
        body, copied = [], {}
        for table in TABLES:
            cols = [c for c in _columns(src, table) if c in _columns(fresh, table)]
            rows = src.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
            for row in rows:
                values = ", ".join(_literal(v) for v in row)
                body.append(f"  INSERT INTO {table} ({', '.join(cols)}) VALUES ({values});")
            copied[table] = len(rows)

        counters = _sqlite_counters(src)
        for table in WITH_IDS:
            top = src.execute(f"SELECT COALESCE(MAX(id), 0) AS n FROM {table}").fetchone()["n"]
            last = max(top, counters.get(table, 0))
            if last:
                body.append(f"  PERFORM setval(pg_get_serial_sequence('{table}', 'id'), {int(last)});")

        checks = [f"  IF (SELECT COUNT(*) FROM {t}) <> {n} THEN\n"
                  f"    RAISE EXCEPTION '{t}: expected {n} rows'; END IF;" for t, n in copied.items()]
    finally:
        src.close()
        fresh.close()

    inserts = "\n".join(body)
    if TAG in inserts:                                   # would end the block early
        raise SystemExit("A product name contains the text " + TAG + "; can't write the file.")
    script = f"""-- OnTrack: copy of ontrack.db, made by copy_to_postgres.py
-- Paste all of this into Neon's SQL Editor and press Run.
-- Everything inside the DO block is saved together or not at all.

{db.PG_SCHEMA.strip()}

DO {TAG}
BEGIN
  IF EXISTS (SELECT 1 FROM items) THEN
    RAISE EXCEPTION 'Postgres already has items. Copy only into an empty database.';
  END IF;

{inserts}

{chr(10).join(checks)}
END
{TAG};
"""
    return script, copied


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Copy ontrack.db into Postgres.")
    parser.add_argument("pg_url", nargs="?", default=os.getenv("DATABASE_URL"),
                        help="Postgres address (default: DATABASE_URL)")
    parser.add_argument("--sqlite", default=db.db_path(),
                        help="SQLite file to copy from (default: ontrack.db)")
    parser.add_argument("--sql-out", metavar="FILE",
                        help="write a .sql file to paste into Neon's SQL Editor, instead of connecting")
    args = parser.parse_args()

    if args.sql_out:
        script, copied = to_sql(args.sqlite)
        with open(args.sql_out, "w", encoding="utf-8") as f:
            f.write(script)
        for table, n in copied.items():
            print(f"  {table:<15} {n:>5} rows")
        print(f"Wrote {args.sql_out}. Paste it into Neon's SQL Editor and press Run.")
        print("It contains your whole list: don't commit it, and delete it afterwards.")
        return

    if not args.pg_url:
        sys.exit("Give the Postgres address, or set DATABASE_URL.")

    copied = copy(args.sqlite, args.pg_url)
    for table, n in copied.items():
        print(f"  {table:<15} {n:>5} rows")
    print("Done: every table has the same number of rows in Postgres.")


if __name__ == "__main__":
    main()