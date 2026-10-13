"""Accounts: sign-up by invite, logins, device tokens, resets, and above all
that one person can never see or change another person's list.

Like test_api.py, every test runs on SQLite and (with TEST_DATABASE_URL) on Postgres."""

import os
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import auth
import db
import main
import services
from extractor import Product

KEY = "owner-key-long-enough-for-the-startup-check"
TEST_PG = os.getenv("TEST_DATABASE_URL")
SHANE = {"email": "Shane@Example.com", "password": "correct horse battery", "name": "Shane"}
PRIYA = {"email": "priya@example.com", "password": "another long password", "name": "Priya",
         "currency": "USD", "country": "US", "timezone": "America/New_York"}
LIPSTICK = Product(url="https://www.savana.com/details/7", ok=True, title="MARS lipstick",
                   price=237, method="savana")


def _wipe_postgres(url):
    import psycopg
    with psycopg.connect(url) as conn:
        conn.execute("DROP TABLE IF EXISTS status_changes, price_history, links, items, settings, "
                     "invites, tokens, users CASCADE")


@pytest.fixture(params=["sqlite", "postgres"])
def app(request, tmp_path, monkeypatch):
    """A server with NO accounts yet (unlike test_api.py's client)."""
    monkeypatch.setenv("ONTRACK_API_KEY", KEY)
    if request.param == "postgres":
        if not TEST_PG:
            pytest.skip("TEST_DATABASE_URL not set")
        _wipe_postgres(TEST_PG)
        monkeypatch.setenv("DATABASE_URL", TEST_PG)
    else:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("ONTRACK_DB", str(tmp_path / "test.db"))
    monkeypatch.setattr(auth, "SCRYPT_N", 2 ** 10)
    main.app.dependency_overrides[main.get_extract] = lambda: (lambda url: LIPSTICK)
    main.app.dependency_overrides[main.get_resolver] = lambda: (
        lambda host, port, **kw: [(2, 1, 6, "", ("93.184.216.34", port))])
    main.rate_limiter.reset()
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


def h(token):
    return {"X-API-Key": token}


def signup(app, invite, person):
    return app.post("/auth/signup", json={"invite": invite, **person})


def owner_and_friend(app):
    """Shane (owner) and Priya (invited). Returns their tokens."""
    shane = signup(app, KEY, SHANE).json()["token"]
    code = app.post("/invites", json={"note": "Priya"}, headers=h(shane)).json()["code"]
    priya = signup(app, code, PRIYA).json()["token"]
    return shane, priya


# ------------------------------------------------------------ first account

def test_first_account_needs_the_owner_key_as_its_invite(app):
    r = signup(app, "guess", SHANE)
    assert r.status_code == 400 and "ONTRACK_API_KEY" in r.json()["detail"]
    r = signup(app, KEY, SHANE)
    assert r.status_code == 201
    user = r.json()["user"]
    assert user["is_admin"] and user["email"] == "shane@example.com"     # stored lower-case
    assert "password_hash" not in user
    assert signup(app, KEY, {**SHANE, "email": "x@example.com"}).status_code == 400   # only once


def test_owner_key_before_any_account_says_what_to_do(app):
    r = app.get("/summary", headers=h(KEY))
    assert r.status_code == 401 and "invite code" in r.json()["detail"]


def test_owner_key_still_works_and_acts_as_the_owner(app):
    """So the Shortcuts and the extension keep working on the day this goes live."""
    token = signup(app, KEY, SHANE).json()["token"]
    app.post("/items", json={"name": "Lamp", "price": 500}, headers=h(token))
    assert [i["name"] for i in app.get("/items", headers=h(KEY)).json()] == ["Lamp"]


def test_the_list_from_before_accounts_goes_to_the_owner(app):
    """Rows saved before Accounts have no owner; the first sign-up gets them all,
    with the old budget."""
    conn = db.connect()
    conn.execute("INSERT INTO settings (key, value) VALUES ('budget', '1000')")
    item = conn.execute("INSERT INTO items (name, created_at) VALUES ('Old watch', '2026-10-01') "
                        "RETURNING id").fetchone()["id"]
    conn.execute("INSERT INTO links (item_id, url, price, created_at) "
                 "VALUES (?, 'https://www.amazon.in/dp/B0OLD', 1999, '2026-10-01')", (item,))
    conn.commit()
    conn.close()

    token = signup(app, KEY, SHANE).json()["token"]
    s = app.get("/summary", headers=h(token)).json()
    assert s["budget"] == 1000 and [i["name"] for i in s["items"]] == ["Old watch"]
    # The old link now belongs to Shane too: saving it again is a duplicate.
    r = app.post("/items", json={"name": "Again", "price": 1, "url": "https://www.amazon.in/dp/B0OLD"},
                 headers=h(token))
    assert r.status_code == 409


# ------------------------------------------------------------------ invites

def test_an_invite_works_once_and_only_for_seven_days(app, monkeypatch):
    shane = signup(app, KEY, SHANE).json()["token"]
    code = app.post("/invites", json={"note": "Priya"}, headers=h(shane)).json()["code"]
    assert signup(app, code, PRIYA).status_code == 201
    r = signup(app, code, {**PRIYA, "email": "someone@example.com"})
    assert r.status_code == 400 and "already used" in r.json()["detail"]

    late = app.post("/invites", json={}, headers=h(shane)).json()["code"]
    eight_days = datetime.now(timezone.utc) + timedelta(days=8)
    monkeypatch.setattr(services, "_utcnow", lambda: eight_days)
    assert signup(app, late, {**PRIYA, "email": "late@example.com"}).status_code == 400


def test_only_the_owner_can_invite_or_see_everyone(app):
    shane, priya = owner_and_friend(app)
    assert app.post("/invites", json={}, headers=h(priya)).status_code == 403
    assert app.get("/users", headers=h(priya)).status_code == 403
    people = app.get("/users", headers=h(shane)).json()
    assert [p["email"] for p in people] == ["shane@example.com", "priya@example.com"]


def test_the_same_email_cant_sign_up_twice(app):
    shane = signup(app, KEY, SHANE).json()["token"]
    code = app.post("/invites", json={}, headers=h(shane)).json()["code"]
    r = signup(app, code, {**PRIYA, "email": "SHANE@example.com"})
    assert r.status_code == 400 and "already an account" in r.json()["detail"]


def test_sign_up_checks_password_email_and_time_zone(app):
    assert signup(app, KEY, {**SHANE, "password": "short"}).status_code == 400
    assert signup(app, KEY, {**SHANE, "email": "not-an-email"}).status_code == 400
    assert signup(app, KEY, {**SHANE, "timezone": "Asia/Kolkatta"}).status_code == 400
    assert signup(app, KEY, {**SHANE, "currency": "XYZ"}).status_code == 400


# --------------------------------------------------- separate lists (the point)

def test_people_never_see_or_change_each_others_lists(app):
    shane, priya = owner_and_friend(app)
    app.put("/budget", json={"amount": 15000}, headers=h(shane))
    watch = app.post("/items", json={"name": "Watch", "price": 1999,
                                     "url": "https://www.amazon.in/dp/B0WATCH"}, headers=h(shane)).json()
    link_id = watch["links"][0]["id"]

    s = app.get("/summary", headers=h(priya)).json()
    assert s["items"] == [] and s["budget"] is None          # her own empty list and budget

    # Every way of reaching Shane's item answers "not found" for Priya.
    assert app.get(f"/items/{watch['id']}", headers=h(priya)).status_code == 404
    assert app.patch(f"/items/{watch['id']}", json={"name": "Mine"}, headers=h(priya)).status_code == 404
    assert app.delete(f"/items/{watch['id']}", headers=h(priya)).status_code == 404
    assert app.get(f"/items/{watch['id']}/history", headers=h(priya)).status_code == 404
    assert app.post(f"/items/{watch['id']}/links", json={"url": "https://x.example/p"},
                    headers=h(priya)).status_code == 404
    assert app.post(f"/items/{watch['id']}/refresh", headers=h(priya)).status_code == 404
    assert app.delete(f"/links/{link_id}", headers=h(priya)).status_code == 404
    assert app.post(f"/links/{link_id}/from-html", files={"html": ("p.html", "<html></html>", "text/html")},
                    headers=h(priya)).status_code == 404
    assert app.get("/refresh/phone-list?force=true", headers=h(priya)).json() == []

    mine = app.get(f"/items/{watch['id']}", headers=h(shane)).json()
    assert mine["name"] == "Watch" and len(mine["links"]) == 1      # untouched


def test_two_people_can_save_the_same_link(app):
    shane, priya = owner_and_friend(app)
    url = LIPSTICK.url
    assert app.post("/items/from-link", json={"url": url}, headers=h(shane)).status_code == 201
    assert app.post("/items/from-link", json={"url": url}, headers=h(priya)).status_code == 201
    assert app.post("/items/from-link", json={"url": url}, headers=h(priya)).status_code == 409  # her own duplicate


def test_each_person_has_their_own_currency_and_time_zone(app):
    shane, priya = owner_and_friend(app)
    me = app.get("/me", headers=h(priya)).json()
    assert (me["currency"], me["country"], me["timezone"]) == ("USD", "US", "America/New_York")
    assert app.get("/me", headers=h(shane)).json()["currency"] == "INR"
    r = app.patch("/me", json={"currency": "gbp", "timezone": "Europe/London"}, headers=h(priya))
    assert r.json()["currency"] == "GBP"
    assert app.patch("/me", json={"timezone": "Mars/Base"}, headers=h(priya)).status_code == 400


# ------------------------------------------------------------- logging in

def test_log_in_and_out(app):
    signup(app, KEY, SHANE)
    r = app.post("/auth/login", json={"email": "SHANE@example.com ", "password": SHANE["password"]})
    assert r.status_code == 200
    token = r.json()["token"]
    assert app.get("/me", headers=h(token)).json()["name"] == "Shane"
    assert app.post("/auth/logout", headers=h(token)).status_code == 204
    assert app.get("/me", headers=h(token)).status_code == 401


def test_wrong_password_and_unknown_email_get_the_same_answer(app):
    """Different answers would tell a stranger which emails have accounts."""
    signup(app, KEY, SHANE)
    wrong = app.post("/auth/login", json={"email": SHANE["email"], "password": "not the password"})
    nobody = app.post("/auth/login", json={"email": "nobody@example.com", "password": "not the password"})
    assert wrong.status_code == nobody.status_code == 401
    assert wrong.json() == nobody.json()


def test_logging_in_is_rate_limited(app):
    signup(app, KEY, SHANE)
    main.rate_limiter.reset()
    codes = [app.post("/auth/login", json={"email": SHANE["email"], "password": "guess number %d" % i}
                      ).status_code for i in range(main.RATE_LIMIT_LOGIN + 1)]
    assert codes[:-1] == [401] * main.RATE_LIMIT_LOGIN and codes[-1] == 429


def test_passwords_and_tokens_are_never_stored_as_they_are(app):
    r = signup(app, KEY, SHANE)
    conn = db.connect()
    row = conn.execute("SELECT password_hash FROM users").fetchone()
    hashes = [t["token_hash"] for t in conn.execute("SELECT token_hash FROM tokens").fetchall()]
    conn.close()
    assert SHANE["password"] not in row["password_hash"] and row["password_hash"].startswith("scrypt$")
    assert r.json()["token"] not in hashes


# ----------------------------------------------------------- device tokens

def test_device_tokens_work_until_revoked(app):
    shane = signup(app, KEY, SHANE).json()["token"]
    device = app.post("/tokens", json={"name": "iPhone Shortcuts"}, headers=h(shane)).json()
    assert app.get("/summary", headers=h(device["token"])).status_code == 200

    listed = app.get("/tokens", headers=h(shane)).json()
    assert {t["name"] for t in listed} == {"Web app", "iPhone Shortcuts"}
    assert all("token" not in t and "token_hash" not in t for t in listed)   # never shown again
    assert [t["current"] for t in listed] == [True, False]

    phone = next(t for t in listed if t["kind"] == "device")
    assert app.delete(f"/tokens/{phone['id']}", headers=h(shane)).status_code == 204
    assert app.get("/summary", headers=h(device["token"])).status_code == 401


def test_nobody_can_revoke_someone_elses_token(app):
    shane, priya = owner_and_friend(app)
    shanes = app.get("/tokens", headers=h(shane)).json()[0]["id"]
    assert app.delete(f"/tokens/{shanes}", headers=h(priya)).status_code == 404
    assert app.get("/me", headers=h(shane)).status_code == 200


# ------------------------------------------------------------- passwords

def test_reset_link_sets_a_new_password_and_signs_out_old_logins(app):
    shane, priya = owner_and_friend(app)
    device = app.post("/tokens", json={"name": "Phone"}, headers=h(priya)).json()["token"]
    priya_id = app.get("/me", headers=h(priya)).json()["id"]
    code = app.post(f"/users/{priya_id}/reset", headers=h(shane)).json()["code"]

    assert signup(app, code, {**PRIYA, "email": "new@example.com"}).status_code == 400   # not an invite
    r = app.post("/auth/reset", json={"code": code, "password": "a brand new password"})
    assert r.status_code == 200 and r.json()["user"]["email"] == "priya@example.com"
    assert app.get("/me", headers=h(priya)).status_code == 401              # old login signed out
    assert app.get("/me", headers=h(device)).status_code == 200             # the phone keeps working
    assert app.post("/auth/login", json={"email": PRIYA["email"], "password": "a brand new password"}
                    ).status_code == 200
    assert app.post("/auth/reset", json={"code": code, "password": "yet another password"}
                    ).status_code == 400                                     # used once


def test_changing_password_needs_the_current_one(app):
    shane = signup(app, KEY, SHANE).json()["token"]
    other = app.post("/auth/login", json={"email": SHANE["email"], "password": SHANE["password"]}).json()["token"]
    r = app.post("/me/password", json={"current": "wrong wrong wrong", "new": "a brand new password"},
                 headers=h(shane))
    assert r.status_code == 400
    r = app.post("/me/password", json={"current": SHANE["password"], "new": "a brand new password"},
                 headers=h(shane))
    assert r.status_code == 204
    assert app.get("/me", headers=h(shane)).status_code == 200      # this login stays
    assert app.get("/me", headers=h(other)).status_code == 401      # other logins are signed out


# -------------------------------------------------- upgrading an old database

OLD_SCHEMA = """
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned', priority INTEGER NOT NULL DEFAULT 0,
    manual_price DOUBLE PRECISION, note TEXT, purchased_price DOUBLE PRECISION,
    purchased_at TEXT, created_at TEXT NOT NULL);
CREATE TABLE links (id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    url TEXT NOT NULL UNIQUE, title TEXT, price DOUBLE PRECISION, mrp DOUBLE PRECISION,
    image TEXT, method TEXT, last_checked TEXT, last_error TEXT, created_at TEXT NOT NULL);
CREATE TABLE price_history (id INTEGER PRIMARY KEY AUTOINCREMENT,
    link_id INTEGER NOT NULL REFERENCES links(id) ON DELETE CASCADE,
    price DOUBLE PRECISION NOT NULL, mrp DOUBLE PRECISION, checked_at TEXT NOT NULL);
CREATE TABLE status_changes (id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    from_status TEXT, to_status TEXT NOT NULL, changed_at TEXT NOT NULL);
INSERT INTO items (id, name, created_at) VALUES (4, 'Old watch', '2026-10-01');
INSERT INTO links (id, item_id, url, price, created_at) VALUES (9, 4, 'https://www.amazon.in/dp/B0OLD', 1999, '2026-10-01');
INSERT INTO price_history (link_id, price, checked_at) VALUES (9, 2199, '2026-10-01'), (9, 1999, '2026-10-02');
"""


@pytest.mark.parametrize("backend", ["sqlite", "postgres"])
def test_an_old_database_is_upgraded_without_losing_anything(backend, tmp_path, monkeypatch):
    """The live Neon database and my ontrack.db were made before Accounts:
    links.url was unique for everyone. Starting the new code must keep every
    row (and its price history) and then let two people save the same link."""
    if backend == "postgres":
        if not TEST_PG:
            pytest.skip("TEST_DATABASE_URL not set")
        _wipe_postgres(TEST_PG)
        monkeypatch.setenv("DATABASE_URL", TEST_PG)
        conn = db.connect()
        conn.executescript(OLD_SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT",
                                              "INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY"))
        conn.commit()
    else:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        conn = db.connect(str(tmp_path / "old.db"))
        conn.executescript(OLD_SCHEMA)

    db.init(conn)
    db.init(conn)                                     # every start runs it: twice must be harmless
    history = conn.execute("SELECT price FROM price_history WHERE link_id = 9 ORDER BY id").fetchall()
    assert [r["price"] for r in history] == [2199, 1999]
    assert "user_id" in db.columns(conn, "items") and "user_id" in db.columns(conn, "links")

    a = conn.execute("INSERT INTO users (email, name, password_hash, created_at) "
                     "VALUES ('a@x.com', 'A', 'x', 'now') RETURNING id").fetchone()["id"]
    b = conn.execute("INSERT INTO users (email, name, password_hash, created_at) "
                     "VALUES ('b@x.com', 'B', 'x', 'now') RETURNING id").fetchone()["id"]
    auth._give_old_list_to(conn, a)
    assert services.item_view(conn, a, 4)["price"] == 1999
    item_b = services.create_manual_item(conn, b, "Same watch", 1999, url="https://www.amazon.in/dp/B0OLD")
    assert services.item_view(conn, b, item_b)["links"][0]["url"] == "https://www.amazon.in/dp/B0OLD"
    with pytest.raises(services.Duplicate):          # but still unique for one person
        services.create_manual_item(conn, a, "Again", 1, url="https://www.amazon.in/dp/B0OLD")
    if backend == "sqlite":                           # deleting an item still deletes its links
        services.delete_item(conn, a, 4)
        assert conn.execute("SELECT COUNT(*) AS n FROM price_history").fetchone()["n"] == 0
    conn.close()
