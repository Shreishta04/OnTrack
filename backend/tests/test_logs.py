"""The logs: every change and every problem is written down in its area, the
person sees a plain sentence with a reference code (never "Not found: item
65"), and the owner can read it all (pull_logs.py) without secrets in it.

Runs on SQLite and Postgres. In tests the log's writer thread is off
(conftest.py), so each test calls events.flush() before reading.
"""

from datetime import datetime, timedelta, timezone

import auth
import db
import events
import main
import services
from test_api import H, OWNER, client  # noqa: F401  (client is a pytest fixture)


def logged(area=None):
    events.flush()
    conn = db.connect()
    try:
        return events.read(conn, area=area)
    finally:
        conn.close()


def friend_token(c):
    conn = db.connect()
    owner = dict(conn.execute("SELECT * FROM users WHERE is_admin = 1").fetchone())
    code = auth.create_invite(conn, owner, "friend")["code"]
    conn.close()
    return c.post("/auth/signup", json={"invite": code, "email": "f@example.com", "password": "a long password",
                                        "name": "Friend"}).json()["token"]


def test_a_change_is_logged_in_its_area_with_who_and_what(client):
    item = client.post("/items", json={"name": "Desk lamp", "price": 1499}, headers=H).json()
    client.patch(f"/items/{item['id']}", json={"status": "later"}, headers=H)
    client.delete(f"/items/{item['id']}", headers=H)
    lines = logged("items")
    added, moved, deleted = lines[-3:]
    assert added["event"] == "item added by hand (POST /items → 201)" and added["user_name"] == "Shane"
    assert moved["event"].startswith("moved to Later (PATCH")
    assert '"moved": "planned → later"' in moved["detail"] and f'"item_id": {item["id"]}' in moved["detail"]
    assert deleted["event"].startswith("moved to Recently deleted (DELETE /items/{item_id} → 204)")


def test_reads_that_went_fine_are_not_logged(client):
    client.get("/summary", headers=H)                  # (the first one saves this budget period: logged once)
    before = len(logged())
    client.get("/summary", headers=H)
    client.get("/items", headers=H)
    assert len(logged()) == before


def test_not_found_is_a_plain_sentence_with_a_reference(client):
    r = client.post("/items/999/restore", headers=H)
    detail = r.json()["detail"]
    assert r.status_code == 404 and detail.startswith("That item isn't in Recently deleted any more.")
    assert "999" not in detail.split("(ref")[0]                         # no ids for the person
    ref = detail.rsplit("ref ", 1)[1].rstrip(")")
    line = next(e for e in logged("items") if e["ref"] == ref)          # …but the log has the real story
    assert line["level"] == "warn" and "not found: deleted item 999" in line["detail"]


def test_a_crash_becomes_a_sentence_and_a_full_error_log(client, monkeypatch):
    def broken(*a, **k):
        raise ZeroDivisionError("the numbers went wrong")
    monkeypatch.setattr(services, "summary", broken)
    r = client.get("/summary", headers=H)
    assert r.status_code == 500
    assert r.json()["detail"].startswith("Something went wrong on OnTrack's side. Try again in a moment. (ref E-")
    crash = next(e for e in logged("errors") if e["event"] == "crashed: GET /summary")
    assert "ZeroDivisionError: the numbers went wrong" in crash["detail"] and "Traceback" in crash["detail"]
    assert crash["ref"] in r.json()["detail"] and crash["user_name"] == "Shane"


def test_bad_input_is_a_sentence_and_the_log_says_which_field(client):
    r = client.put("/budget", json={"amount": "lots"}, headers=H)
    assert r.status_code == 422 and r.json()["detail"].startswith("Something in that didn't look right.")
    line = logged("budget")[-1]
    assert "amount" in line["detail"] and line["ref"] in r.json()["detail"]


def test_slow_requests_say_where_the_time_went(client, monkeypatch):
    monkeypatch.setattr(main, "SLOW_REQUEST_SECONDS", 0)
    client.get("/summary", headers=H)
    line = next(e for e in logged("speed") if e["event"] == "GET /summary → 200")
    assert '"period"' in line["detail"] and '"items"' in line["detail"] and line["took_ms"] is not None


def test_store_pages_go_to_stores_log(client):
    client.post("/items/from-link", json={"url": "https://www.savana.com/details/1"}, headers=H)
    line = logged("stores")[-1]
    assert line["event"] == "www.savana.com · ok" and '"via": "server"' in line["detail"]
    assert "details/1" not in line["detail"]                             # the store, never the full link


def test_no_secrets_in_the_logs(client):
    client.post("/auth/login", json={"email": OWNER["email"], "password": "not the password at all"})
    client.post("/auth/login", json={"email": OWNER["email"], "password": OWNER["password"]})
    client.post("/tokens", json={"name": "Laptop"}, headers=H)
    everything = " ".join(f"{e['event']} {e['detail']}" for e in logged())
    for secret in (OWNER["password"], "not the password at all", OWNER["email"], H["X-API-Key"]):
        assert secret not in everything
    failed = next(e for e in logged("accounts") if e["event"].startswith("login failed"))
    assert failed["level"] == "warn"


def test_only_the_owner_reads_the_logs_and_after_id_gives_whats_new(client):
    client.post("/items", json={"name": "A", "price": 1}, headers=H)
    first = client.get("/logs", headers=H).json()
    assert first and all({"id", "at", "area", "event", "user_name"} <= set(e) for e in first)
    client.post("/items", json={"name": "B", "price": 2}, headers=H)
    new = client.get(f"/logs?after_id={first[-1]['id']}", headers=H).json()
    assert [e["event"] for e in new if e["area"] == "items"] == ["item added by hand (POST /items → 201)"]
    assert client.get("/logs?area=stores", headers=H).json() == [e for e in client.get("/logs", headers=H).json()
                                                                 if e["area"] == "stores"]
    assert client.get("/logs", headers={"X-API-Key": friend_token(client)}).status_code == 403


def test_the_app_reports_its_own_problems(client, monkeypatch):
    r = client.post("/logs/app", json={"where": "Undo", "message": "TypeError: x is undefined",
                                       "detail": "at runUndo (App.tsx:200)"}, headers=H)
    ref = r.json()["ref"]
    line = next(e for e in logged("app") if e["ref"] == ref)
    assert line["event"] == "app problem: Undo" and "x is undefined" in line["detail"]
    monkeypatch.setattr(main, "APP_REPORTS_PER_MINUTE", 1)
    main._app_reports.clear()
    client.post("/logs/app", json={"where": "x", "message": "y"}, headers=H)
    assert client.post("/logs/app", json={"where": "x", "message": "y"}, headers=H).json() == {"ref": None}


def test_logs_older_than_60_days_are_removed(client):
    conn = db.connect()
    old = (datetime.now(timezone.utc) - timedelta(days=61)).isoformat()
    conn.execute("INSERT INTO events (at, area, level, event) VALUES (?, 'items', 'info', 'ancient')", (old,))
    conn.commit()
    assert events.purge(conn) == 1
    conn.close()
