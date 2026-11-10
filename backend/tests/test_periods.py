"""Budget periods: a default budget, a reset day, and periods that are saved
as they start.

The first tests check the date arithmetic on its own. The rest go through the
API on SQLite and Postgres (the `client` fixture from test_api.py), with the
clock set by hand: services._utcnow is what the app thinks "now" is. Times
are UTC; India is 5.5 hours ahead, so 06:00 UTC is 11:30 the same day there.
"""

from datetime import date, datetime

import pytest

import services
from test_api import H, client  # noqa: F401  (client is a pytest fixture)


def at(monkeypatch, stamp):
    """Pretend it's this moment (UTC)."""
    monkeypatch.setattr(services, "_utcnow", lambda: datetime.fromisoformat(stamp))


def summary(c):
    return c.get("/summary", headers=H).json()


# ------------------------------------------------------------ the arithmetic

def test_next_reset_is_strictly_after_the_day():
    assert services.next_reset_after(date(2026, 11, 10), 25) == date(2026, 11, 25)   # still to come
    assert services.next_reset_after(date(2026, 11, 10), 5) == date(2026, 12, 5)     # already gone
    assert services.next_reset_after(date(2026, 11, 25), 25) == date(2026, 12, 25)   # today doesn't count
    assert services.next_reset_after(date(2026, 12, 20), 1) == date(2027, 1, 1)      # over the new year


def test_the_31st_becomes_the_last_day_of_a_short_month():
    assert services.next_reset_after(date(2027, 1, 31), 31) == date(2027, 2, 28)
    assert services.next_reset_after(date(2028, 1, 31), 31) == date(2028, 2, 29)     # leap year
    assert services.next_reset_after(date(2027, 2, 28), 31) == date(2027, 3, 31)
    assert services.last_reset_on_or_before(date(2027, 2, 28), 30) == date(2027, 2, 28)
    assert services.last_reset_on_or_before(date(2027, 1, 5), 25) == date(2026, 12, 25)


# ----------------------------------------------------------- through the API

def test_without_a_reset_day_the_period_is_the_calendar_month(client, monkeypatch):
    at(monkeypatch, "2026-11-10T06:00:00+00:00")
    p = summary(client)["period"]
    assert (p["starts_on"], p["ends_on"]) == ("2026-11-01", "2026-11-30")
    assert p["reset_day"] is None                      # not chosen: the app shows a reminder
    assert p["days_left"] == 21 and p["days_total"] == 30


def test_a_reset_day_still_to_come_ends_this_period_early(client, monkeypatch):
    at(monkeypatch, "2026-11-10T06:00:00+00:00")
    r = client.put("/budget", json={"amount": 30000, "reset_day": 25}, headers=H)
    assert r.status_code == 200
    p = r.json()["period"]
    assert (p["starts_on"], p["ends_on"], p["reset_day"]) == ("2026-11-01", "2026-11-24", 25)

    at(monkeypatch, "2026-11-25T06:00:00+00:00")       # payday: a fresh period
    p = summary(client)["period"]
    assert (p["starts_on"], p["ends_on"]) == ("2026-11-25", "2026-12-24")
    assert p["budget"] == 30000


def test_a_reset_day_already_gone_waits_for_next_month(client, monkeypatch):
    at(monkeypatch, "2026-11-10T06:00:00+00:00")
    p = client.put("/budget", json={"amount": 30000, "reset_day": 5}, headers=H).json()["period"]
    assert (p["starts_on"], p["ends_on"]) == ("2026-11-01", "2026-12-04")   # one long period


def test_spent_resets_on_the_reset_day(client, monkeypatch):
    at(monkeypatch, "2026-11-10T06:00:00+00:00")
    client.put("/budget", json={"amount": 1000, "reset_day": 25}, headers=H)
    before = client.post("/items", json={"name": "Kurta", "price": 400}, headers=H).json()
    after = client.post("/items", json={"name": "Lipstick", "price": 250}, headers=H).json()

    at(monkeypatch, "2026-11-24T17:00:00+00:00")       # 24 Nov, 22:30 in India: old period
    client.patch(f"/items/{before['id']}", json={"status": "purchased"}, headers=H)
    assert summary(client)["spent_this_month"] == 400

    at(monkeypatch, "2026-11-24T19:00:00+00:00")       # 25 Nov, 00:30 in India: new period
    assert summary(client)["spent_this_month"] == 0    # spent starts again; nothing carries over
    client.patch(f"/items/{after['id']}", json={"status": "purchased"}, headers=H)
    s = summary(client)
    assert s["spent_this_month"] == 250 and s["remaining"] == 1000 - 250


def test_just_this_period_then_back_to_the_default(client, monkeypatch):
    at(monkeypatch, "2026-11-10T06:00:00+00:00")
    client.put("/budget", json={"amount": 30000, "reset_day": 1}, headers=H)
    p = client.put("/budget", json={"amount": 45000, "scope": "once"}, headers=H).json()["period"]
    assert p["budget"] == 45000 and p["custom"] and p["default_budget"] == 30000

    at(monkeypatch, "2026-12-02T06:00:00+00:00")       # December: back to the default
    p = summary(client)["period"]
    assert p["budget"] == 30000 and not p["custom"]


def test_changing_the_default_never_rewrites_past_periods(client, monkeypatch):
    at(monkeypatch, "2026-10-10T06:00:00+00:00")
    client.put("/budget", json={"amount": 20000, "reset_day": 1}, headers=H)
    at(monkeypatch, "2026-11-10T06:00:00+00:00")
    client.put("/budget", json={"amount": 30000}, headers=H)          # "every period" is the default scope
    periods = client.get("/periods", headers=H).json()
    assert [(p["starts_on"], p["budget"], p["current"]) for p in periods] == [
        ("2026-11-01", 30000, True), ("2026-10-01", 20000, False)]


def test_missed_months_are_saved_with_the_default(client, monkeypatch):
    at(monkeypatch, "2026-08-10T06:00:00+00:00")
    client.put("/budget", json={"amount": 15000, "reset_day": 1}, headers=H)
    at(monkeypatch, "2026-11-10T06:00:00+00:00")                       # app not opened for 3 months
    starts = [p["starts_on"] for p in client.get("/periods", headers=H).json()]
    assert starts == ["2026-11-01", "2026-10-01", "2026-09-01", "2026-08-01"]


def test_periods_show_what_was_spent_in_each(client, monkeypatch):
    at(monkeypatch, "2026-10-10T06:00:00+00:00")
    client.put("/budget", json={"amount": 5000, "reset_day": 1}, headers=H)
    oct_item = client.post("/items", json={"name": "Shoes", "price": 3000}, headers=H).json()
    client.patch(f"/items/{oct_item['id']}", json={"status": "purchased"}, headers=H)
    at(monkeypatch, "2026-11-10T06:00:00+00:00")
    nov_item = client.post("/items", json={"name": "Bag", "price": 1200}, headers=H).json()
    client.patch(f"/items/{nov_item['id']}", json={"status": "purchased"}, headers=H)
    spent = {p["starts_on"]: p["spent"] for p in client.get("/periods", headers=H).json()}
    assert spent == {"2026-11-01": 1200, "2026-10-01": 3000}


def test_the_31st_in_february(client, monkeypatch):
    at(monkeypatch, "2027-01-31T06:00:00+00:00")
    client.put("/budget", json={"amount": 10000, "reset_day": 31}, headers=H)
    at(monkeypatch, "2027-02-28T06:00:00+00:00")                       # February's "31st" is the 28th
    p = summary(client)["period"]
    assert (p["starts_on"], p["ends_on"]) == ("2027-02-28", "2027-03-30")


def test_bad_values_are_refused(client):
    assert client.put("/budget", json={"amount": 100, "reset_day": 0}, headers=H).status_code == 422
    assert client.put("/budget", json={"amount": 100, "reset_day": 32}, headers=H).status_code == 422
    assert client.put("/budget", json={"amount": 100, "scope": "forever"}, headers=H).status_code == 422


@pytest.mark.parametrize("path", ["/periods"])
def test_periods_need_a_login(client, path):
    assert client.get(path).status_code == 401


def test_the_live_database_is_upgraded_on_start(client, monkeypatch):
    """Neon already has a users table (from Accounts) but no reset_day column
    and no periods table. Starting the new code adds both, keeps the budget,
    and leaves the reset day empty so the app asks for it."""
    import db
    at(monkeypatch, "2026-11-10T06:00:00+00:00")
    client.put("/budget", json={"amount": 1000}, headers=H)
    conn = db.connect()
    conn.execute("DROP TABLE periods")
    conn.execute("ALTER TABLE users DROP COLUMN reset_day")       # as the live database is today
    conn.commit()
    db.init(conn)
    db.init(conn)                                                  # every start runs it: twice is harmless
    assert "reset_day" in db.columns(conn, "users")
    conn.close()
    p = summary(client)["period"]
    assert p["budget"] == 1000 and p["reset_day"] is None
    assert (p["starts_on"], p["ends_on"]) == ("2026-11-01", "2026-11-30")
