"""Recently deleted: Delete moves an item to a trash for 30 days, from which
Restore brings it back exactly as it was. Undo after Delete is a Restore.

Runs on SQLite and Postgres (the `client` fixture from test_api.py), with the
clock set by hand where days matter.
"""

from datetime import datetime

import services
from extractor import Product
from test_api import H, client  # noqa: F401  (client is a pytest fixture)

WATCH = "https://www.fastrack.in/ryz.html"


def at(monkeypatch, stamp):
    monkeypatch.setattr(services, "_utcnow", lambda: datetime.fromisoformat(stamp))


def add_watch(c):
    return c.post("/items/from-link", json={"url": WATCH}, headers=H).json()


def names(c, path="/items"):
    return [i["name"] for i in c.get(path, headers=H).json()]


def test_delete_moves_it_to_recently_deleted(client, monkeypatch):
    at(monkeypatch, "2026-11-12T06:00:00+00:00")
    watch = add_watch(client)
    client.post("/items", json={"name": "Desk lamp", "price": 1499}, headers=H)
    assert client.delete(f"/items/{watch['id']}", headers=H).status_code == 204

    assert names(client) == ["Desk lamp"]                                  # off the list
    s = client.get("/summary", headers=H).json()
    assert s["planned_total"] == 1499 and [i["name"] for i in s["items"]] == ["Desk lamp"]   # and the totals
    trash = client.get("/trash", headers=H).json()
    assert [i["name"] for i in trash] == ["Fastrack Ryz Women Smartwatch"]
    assert trash[0]["gone_on"] == "2026-12-12" and trash[0]["price"] == 2499   # 30 days, prices kept


def test_restore_brings_back_everything(client):
    watch = add_watch(client)
    client.catalogue[WATCH] = Product(url=WATCH, ok=True, title="Fastrack Ryz Women Smartwatch",
                                      price=2199, method="json-ld")
    client.post("/refresh?force=true", headers=H)                         # some price history
    client.patch(f"/items/{watch['id']}", json={"status": "later", "note": "for Diwali"}, headers=H)
    client.delete(f"/items/{watch['id']}", headers=H)

    r = client.post(f"/items/{watch['id']}/restore", headers=H)
    assert r.status_code == 200
    back = r.json()
    assert (back["status"], back["note"], back["price"]) == ("later", "for Diwali", 2199)   # same list, same note
    assert len(client.get(f"/items/{watch['id']}/history", headers=H).json()) == 2        # history kept
    assert client.get("/trash", headers=H).json() == []
    assert client.post(f"/items/{watch['id']}/restore", headers=H).status_code == 404     # not in the trash now


def test_a_deleted_item_is_left_alone(client):
    watch = add_watch(client)
    link_id = watch["links"][0]["id"]
    client.delete(f"/items/{watch['id']}", headers=H)
    assert client.get(f"/items/{watch['id']}", headers=H).status_code == 404
    assert client.patch(f"/items/{watch['id']}", json={"name": "x"}, headers=H).status_code == 404
    assert client.post(f"/items/{watch['id']}/refresh", headers=H).status_code == 404
    assert client.post(f"/links/{link_id}/from-html", files={"html": ("p.html", "<html></html>", "text/html")},
                       headers=H).status_code == 404
    r = client.post("/refresh?force=true", headers=H).json()
    assert r["checked"] == 0                                               # no price checks for it


def test_saving_it_again_starts_fresh(client):
    watch = add_watch(client)
    client.delete(f"/items/{watch['id']}", headers=H)
    again = client.post("/items/from-link", json={"url": WATCH}, headers=H)
    assert again.status_code == 201                                        # not "already on your list"
    assert again.json()["id"] != watch["id"]
    assert client.get("/trash", headers=H).json() == []                    # the old copy is gone


def test_after_30_days_it_is_gone_for_good(client, monkeypatch):
    at(monkeypatch, "2026-11-01T06:00:00+00:00")
    old = add_watch(client)
    client.delete(f"/items/{old['id']}", headers=H)
    at(monkeypatch, "2026-11-25T06:00:00+00:00")
    recent = client.post("/items", json={"name": "Desk lamp", "price": 1499}, headers=H).json()
    client.delete(f"/items/{recent['id']}", headers=H)

    at(monkeypatch, "2026-12-02T06:00:00+00:00")                          # 31 days after the first
    assert [i["name"] for i in client.get("/trash", headers=H).json()] == ["Desk lamp"]
    assert client.post(f"/items/{old['id']}/restore", headers=H).status_code == 404


def test_empty_now(client):
    for name in ("A", "B"):
        item = client.post("/items", json={"name": name, "price": 10}, headers=H).json()
        client.delete(f"/items/{item['id']}", headers=H)
    assert client.delete("/trash", headers=H).status_code == 204
    assert client.get("/trash", headers=H).json() == []


def test_bought_and_deleted_doesnt_count_as_spent(client):
    item = client.post("/items", json={"name": "Shoes", "price": 3000}, headers=H).json()
    client.patch(f"/items/{item['id']}", json={"status": "purchased"}, headers=H)
    assert client.get("/summary", headers=H).json()["spent_this_month"] == 3000
    client.delete(f"/items/{item['id']}", headers=H)
    assert client.get("/summary", headers=H).json()["spent_this_month"] == 0
    client.post(f"/items/{item['id']}/restore", headers=H)
    assert client.get("/summary", headers=H).json()["spent_this_month"] == 3000


def test_each_persons_trash_is_their_own(client):
    import auth
    import db
    item = client.post("/items", json={"name": "Mine", "price": 10}, headers=H).json()
    client.delete(f"/items/{item['id']}", headers=H)
    conn = db.connect()
    owner = dict(conn.execute("SELECT * FROM users WHERE is_admin = 1").fetchone())
    code = auth.create_invite(conn, owner, "friend")["code"]
    conn.close()
    friend = client.post("/auth/signup", json={"invite": code, "email": "f@example.com", "password": "a long password",
                                               "name": "F"}).json()["token"]
    assert client.get("/trash", headers={"X-API-Key": friend}).json() == []
    assert client.post(f"/items/{item['id']}/restore", headers={"X-API-Key": friend}).status_code == 404
