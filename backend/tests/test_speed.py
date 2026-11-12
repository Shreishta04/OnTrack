"""Speed: the list costs the same few database queries however long it is.

It used to be one query per item, per link and per link's history: 74 for a
33-item list, each a round trip to Neon. Now the items, all their links and
all their history are read in one query each. This test fails if a change
brings the one-query-per-item pattern back.
"""

import pytest

import db
from test_api import H, client  # noqa: F401  (client is a pytest fixture)


def count_queries(client, monkeypatch, method, path, body=None):
    conn = db.connect()
    is_pg = isinstance(conn, db.PgConnection)
    conn.close()
    if not is_pg:
        pytest.skip("counted on Postgres, the live database")
    counts = {"n": 0}
    real = db.PgConnection.execute

    def counting(self, *a, **k):
        counts["n"] += 1
        return real(self, *a, **k)

    monkeypatch.setattr(db.PgConnection, "execute", counting)
    client.request(method, path, json=body, headers=H)
    monkeypatch.setattr(db.PgConnection, "execute", real)
    return counts["n"]


def add(client, n):
    for i in range(n):
        client.post("/items", json={"name": f"Item {i}", "price": 100 + i}, headers=H)


def test_summary_queries_dont_grow_with_the_list(client, monkeypatch):
    add(client, 5)
    client.get("/summary", headers=H)       # the first visit also saves the first budget period, once
    small = count_queries(client, monkeypatch, "GET", "/summary")
    add(client, 40)
    big = count_queries(client, monkeypatch, "GET", "/summary")
    assert big == small, (small, big)       # 5 items or 45: the same number of trips
    assert big <= 15, big


def test_periods_and_moves_stay_small(client, monkeypatch):
    add(client, 30)
    first = client.get("/items", headers=H).json()[0]["id"]
    assert count_queries(client, monkeypatch, "GET", "/periods") <= 12
    assert count_queries(client, monkeypatch, "PATCH", f"/items/{first}", {"status": "later"}) <= 10


def test_connections_are_reused(client):
    """Borrowed from the pool and handed back, not opened per request."""
    first = db.connect()
    if not isinstance(first, db.PgConnection):
        pytest.skip("Postgres only")
    # Start from a pool with one connection in it: earlier tests (alerts sent
    # after the answer, on a second connection) can leave two, taken in turn.
    first.close()
    db.close_pools()
    first = db.connect()
    raw = first.raw
    first.close()
    again = db.connect()
    assert again.raw is raw
    again.close()
