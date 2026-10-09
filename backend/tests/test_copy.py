"""Tests for copy_to_postgres.py: make a small list in SQLite, copy it into an
empty Postgres database, and check nothing was lost or changed.

Needs TEST_DATABASE_URL (an empty test database); skipped without it."""

import os

import pytest

import copy_to_postgres
import db
import services
from extractor import Product

TEST_PG = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_PG, reason="TEST_DATABASE_URL not set")


@pytest.fixture
def sqlite_list(tmp_path, monkeypatch):
    """A SQLite file with a budget, items in every list, links, price history and moves."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    path = str(tmp_path / "ontrack.db")
    conn = db.connect(path)
    db.init(conn)
    services.set_budget(conn, 5000)

    watch = Product(url="https://www.amazon.in/dp/B0WATCH", ok=True, title="Fastrack Ryz Watch",
                    price=1999, mrp=3499, method="amazon")
    watch_id = services.create_item_from_link(conn, watch.url, lambda u: watch)
    later_id = services.create_manual_item(conn, "Milk frother", 439)
    bought_id = services.create_manual_item(conn, "MARS lipstick", 237)
    services.update_item(conn, later_id, status="later")
    services.update_item(conn, bought_id, status="purchased")
    services.delete_item(conn, services.create_manual_item(conn, "Deleted thing", 10))  # leaves a gap in ids

    # A second, cheaper price check, so the watch has price history to copy.
    cheaper = Product(url=watch.url, ok=True, title="Fastrack Ryz Watch", price=1799, mrp=3499, method="amazon")
    link_id = conn.execute("SELECT id FROM links WHERE item_id = ?", (watch_id,)).fetchone()["id"]
    services._record_check(conn, link_id, cheaper)
    conn.commit()
    conn.close()
    import psycopg                         # only here: Postgres runs only with TEST_DATABASE_URL
    with psycopg.connect(TEST_PG) as pg:
        pg.execute("DROP TABLE IF EXISTS status_changes, price_history, links, items, settings CASCADE")
    return path


def _dump(conn, table):
    order = "key" if table == "settings" else "id"
    return [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()]


def test_copy_keeps_every_row_and_id(sqlite_list):
    copied = copy_to_postgres.copy(sqlite_list, TEST_PG)
    assert copied["items"] == 3 and copied["price_history"] == 2

    src, dst = db.connect(sqlite_list), db.PgConnection(TEST_PG)
    for table in copy_to_postgres.TABLES:
        assert _dump(dst, table) == _dump(src, table), table      # same rows, same ids, same values
    src.close(), dst.close()


def test_new_items_after_copy_get_fresh_ids(sqlite_list, monkeypatch):
    """Without moving the id counters, the first new item would be given id 1,
    which the copied watch already has, and adding anything would fail."""
    copy_to_postgres.copy(sqlite_list, TEST_PG)
    monkeypatch.setenv("DATABASE_URL", TEST_PG)
    conn = db.connect()
    new_id = services.create_manual_item(conn, "Bottle brush", 170)
    assert new_id == 5                     # 4 ids were used in SQLite (one item was deleted)
    assert services.summary(conn)["budget"] == 5000
    conn.close()


def test_refuses_to_copy_into_a_database_that_has_items(sqlite_list):
    copy_to_postgres.copy(sqlite_list, TEST_PG)
    with pytest.raises(SystemExit, match="already has 3 items"):
        copy_to_postgres.copy(sqlite_list, TEST_PG)        # running it twice can't double the list


# ---- the .sql file (for computers that can't connect to Postgres directly) ----

def _run_script(script):
    """Run the file the way Neon's SQL Editor would: the whole text at once."""
    import psycopg
    with psycopg.connect(TEST_PG, autocommit=True) as pg:
        pg.execute(script)


def test_sql_file_gives_the_same_result_as_copying(sqlite_list):
    script, copied = copy_to_postgres.to_sql(sqlite_list)
    _run_script(script)

    src, dst = db.connect(sqlite_list), db.PgConnection(TEST_PG)
    for table in copy_to_postgres.TABLES:
        assert _dump(dst, table) == _dump(src, table), table
    assert copied["items"] == 3
    src.close(), dst.close()


def test_sql_file_sets_id_counters_and_refuses_a_second_run(sqlite_list, monkeypatch):
    import psycopg
    script, _ = copy_to_postgres.to_sql(sqlite_list)
    _run_script(script)

    monkeypatch.setenv("DATABASE_URL", TEST_PG)
    conn = db.connect()
    assert services.create_manual_item(conn, "Bottle brush", 170) == 5     # same as SQLite would give
    conn.close()

    with pytest.raises(psycopg.errors.RaiseException, match="already has items"):
        _run_script(script)                                             # pasting twice can't double the list


def test_sql_file_survives_awkward_names(tmp_path, monkeypatch):
    """Quotes end a SQL string early, and % or ? look like placeholders.
    Names like these must arrive exactly as typed."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    path = str(tmp_path / "awkward.db")
    conn = db.connect(path)
    db.init(conn)
    names = ["Levi's 'slim' jeans", "100% cotton tee?", "Kurta 🌸 (pack of 2)", "Line one\nline two"]
    for name in names:
        services.create_manual_item(conn, name, 499.5, note="it's \"great\"")
    conn.close()
    import psycopg
    with psycopg.connect(TEST_PG) as pg:
        pg.execute("DROP TABLE IF EXISTS status_changes, price_history, links, items, settings CASCADE")

    script, _ = copy_to_postgres.to_sql(path)
    _run_script(script)

    dst = db.PgConnection(TEST_PG)
    rows = dst.execute("SELECT name, note, manual_price FROM items ORDER BY id").fetchall()
    dst.close()
    assert [r["name"] for r in rows] == names
    assert all(r["note"] == "it's \"great\"" and r["manual_price"] == 499.5 for r in rows)