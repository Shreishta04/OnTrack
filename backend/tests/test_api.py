"""API tests: a real FastAPI app and real SQLite database (a temp file),
but a fake extractor, so no store is ever contacted."""

import pytest
from fastapi.testclient import TestClient

import sqlite3
import main
import services
from extractor import Product

KEY = "test-key"
H = {"X-API-Key": KEY}

# Fake store catalogue: url -> what the extractor "finds" there.
CATALOGUE = {
    "https://amzn.in/d/watch": Product(url="https://www.amazon.in/dp/B0WATCH", ok=True,
                                       title="Fastrack Ryz Watch", price=1999, mrp=3499, method="amazon"),
    "https://www.fastrack.in/ryz.html": Product(url="https://www.fastrack.in/ryz.html", ok=True,
                                                title="Fastrack Ryz Women Smartwatch", price=2499, method="json-ld"),
    "https://www.savana.com/details/1": Product(url="https://www.savana.com/details/1", ok=True,
                                                title="Cherry Cable Cover", price=273, mrp=390, method="savana"),
    "https://blocked.example/p": Product(url="https://blocked.example/p", title="Mystery Item",
                                         error="Store returned HTTP 403"),
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ONTRACK_API_KEY", KEY)
    monkeypatch.setenv("ONTRACK_DB", str(tmp_path / "test.db"))
    monkeypatch.setattr(services, "REFRESH_DELAY", (0, 0))
    catalogue = dict(CATALOGUE)

    def fake_extract(url):
        if url in catalogue:
            return catalogue[url]
        # refresh() calls with the stored (final) URL
        return next(p for p in catalogue.values() if p.url == url)

    main.app.dependency_overrides[main.get_extract] = lambda: fake_extract
    with TestClient(main.app) as c:          # `with` runs startup (creates tables)
        c.catalogue = catalogue              # tests can change "store prices"
        yield c
    main.app.dependency_overrides.clear()


def test_requires_api_key(client):
    assert client.get("/summary").status_code == 422                      # header missing
    assert client.get("/summary", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/health").status_code == 200                       # public


def test_add_from_link_uses_product_title_and_short_link_resolves(client):
    r = client.post("/items/from-link", json={"url": "https://amzn.in/d/watch"}, headers=H)
    assert r.status_code == 201
    item = r.json()
    assert item["name"] == "Fastrack Ryz Watch"
    assert item["price"] == 1999 and item["mrp"] == 3499
    assert item["links"][0]["url"] == "https://www.amazon.in/dp/B0WATCH"


def test_cheapest_link_wins_and_total_counts_item_once(client):
    item = client.post("/items/from-link", json={"url": "https://www.fastrack.in/ryz.html",
                                                  "name": "Smartwatch"}, headers=H).json()
    assert item["price"] == 2499
    item = client.post(f"/items/{item['id']}/links", json={"url": "https://amzn.in/d/watch"}, headers=H).json()
    assert len(item["links"]) == 2 and item["price"] == 1999      # Amazon is cheaper

    s = client.get("/summary", headers=H).json()
    assert s["planned_total"] == 1999                               # not 1999 + 2499


def test_duplicate_link_rejected_even_via_short_link(client):
    client.post("/items/from-link", json={"url": "https://amzn.in/d/watch"}, headers=H)
    r = client.post("/items/from-link", json={"url": "https://www.amazon.in/dp/B0WATCH?psc=1"}, headers=H)
    assert r.status_code == 409
    assert len(client.get("/items", headers=H).json()) == 1        # no empty item left behind


def test_failed_extraction_still_saves_item_for_manual_price(client):
    item = client.post("/items/from-link", json={"url": "https://blocked.example/p"}, headers=H).json()
    assert item["name"] == "Mystery Item" and item["needs_price"]
    assert "403" in item["links"][0]["last_error"]
    item = client.patch(f"/items/{item['id']}", json={"manual_price": 500}, headers=H).json()
    assert item["price"] == 500 and not item["needs_price"]


def test_summary_budget_mrp_and_what_fits(client):
    client.put("/budget", json={"amount": 2000}, headers=H)
    client.post("/items/from-link", json={"url": "https://amzn.in/d/watch", "priority": 2}, headers=H)
    client.post("/items/from-link", json={"url": "https://www.savana.com/details/1", "priority": 1}, headers=H)
    client.post("/items", json={"name": "Charm bracelet", "price": 1500}, headers=H)

    s = client.get("/summary", headers=H).json()
    assert s["planned_total"] == 1999 + 273 + 1500
    assert s["remaining"] == 2000 - (1999 + 273 + 1500)
    assert s["savings_vs_mrp"] == (3499 - 1999) + (390 - 273)      # discounted total, MRP alongside
    fits = {i["name"]: i["fits_budget"] for i in s["items"]}
    assert fits == {"Fastrack Ryz Watch": True, "Cherry Cable Cover": False, "Charm bracelet": False}


def test_unplanned_items_dont_count(client):
    client.post("/items", json={"name": "Maybe later", "price": 999}, headers=H)
    item = client.post("/items", json={"name": "Needed", "price": 100}, headers=H).json()
    first = client.get("/items", headers=H).json()[0]
    client.patch(f"/items/{first['id']}", json={"status": "later"}, headers=H)
    assert client.get("/summary", headers=H).json()["planned_total"] == 100


def test_refresh_cooldown_force_and_price_history(client):
    item = client.post("/items/from-link", json={"url": "https://www.savana.com/details/1"}, headers=H).json()

    r = client.post("/refresh", headers=H).json()                 # just checked -> skipped
    assert r["checked"] == 0 and r["skipped_recent"] == 1

    client.catalogue["https://www.savana.com/details/1"] = Product(
        url="https://www.savana.com/details/1", ok=True, title="Cherry Cable Cover",
        price=250, mrp=390, method="savana")                          # store drops the price
    r = client.post("/refresh?force=true", headers=H).json()
    assert r["changed"] == [{"link_id": item["links"][0]["id"], "old_price": 273, "new_price": 250}]

    link = client.get(f"/items/{item['id']}", headers=H).json()["links"][0]
    assert link["price"] == 250 and link["price_when_saved"] == 273
    assert link["previous_price"] == 273 and link["lowest_price_seen"] == 250


def test_failed_refresh_keeps_last_price(client):
    item = client.post("/items/from-link", json={"url": "https://www.savana.com/details/1"}, headers=H).json()
    client.catalogue["https://www.savana.com/details/1"] = Product(
        url="https://www.savana.com/details/1", error="Amazon showed a bot-check page")
    r = client.post(f"/items/{item['id']}/refresh", headers=H).json()
    assert r["failed"] and r["item"]["price"] == 273              # last known price kept
    assert "bot-check" in r["item"]["links"][0]["last_error"]


def test_delete_cascades(client):
    item = client.post("/items/from-link", json={"url": "https://amzn.in/d/watch"}, headers=H).json()
    assert client.delete(f"/items/{item['id']}", headers=H).status_code == 204
    assert client.get(f"/items/{item['id']}", headers=H).status_code == 404
    # link row was removed too, so the same URL can be saved again
    assert client.post("/items/from-link", json={"url": "https://amzn.in/d/watch"}, headers=H).status_code == 201


def test_status_moves_are_logged(client, tmp_path):
    item = client.post("/items", json={"name": "Milk frother", "price": 439}, headers=H).json()
    url = f"/items/{item['id']}"
    client.patch(url, json={"status": "later"}, headers=H)
    client.patch(url, json={"status": "later"}, headers=H)      # already later: must NOT be logged
    client.patch(url, json={"status": "planned"}, headers=H)

    conn = sqlite3.connect(tmp_path / "test.db")
    rows = conn.execute(
        "SELECT from_status, to_status FROM status_changes WHERE item_id = ? ORDER BY id",
        (item["id"],)).fetchall()
    conn.close()
    assert rows == [(None, "planned"), ("planned", "later"), ("later", "planned")]

    
def test_mark_bought_saves_price_and_date_undo_clears(client):
    item = client.post("/items", json={"name": "MARS lipstick", "price": 237}, headers=H).json()

    item = client.patch(f"/items/{item['id']}", json={"status": "purchased"}, headers=H).json()
    assert item["purchased_price"] == 237 and item["purchased_at"] is not None

    item = client.patch(f"/items/{item['id']}", json={"status": "planned"}, headers=H).json()
    assert item["purchased_price"] is None and item["purchased_at"] is None