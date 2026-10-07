"""API tests: a real FastAPI app and real SQLite database (a temp file),
but a fake extractor, so no store is ever contacted."""

import pytest
from fastapi.testclient import TestClient

import sqlite3
import main
import services
from extractor import Product, clean_url

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


def test_spent_this_month_comes_off_the_budget(client):
    client.put("/budget", json={"amount": 1000}, headers=H)
    bought = client.post("/items", json={"name": "Concealer", "price": 400}, headers=H).json()
    client.post("/items", json={"name": "Bottle brush", "price": 170}, headers=H)
    client.patch(f"/items/{bought['id']}", json={"status": "purchased"}, headers=H)

    s = client.get("/summary", headers=H).json()
    assert s["spent_this_month"] == 400
    assert s["planned_total"] == 170                    # bought item no longer planned
    assert s["remaining"] == 1000 - 400 - 170


def test_refresh_skips_bought_items(client):
    item = client.post("/items/from-link", json={"url": "https://www.savana.com/details/1"}, headers=H).json()
    client.patch(f"/items/{item['id']}", json={"status": "purchased"}, headers=H)
    client.catalogue["https://www.savana.com/details/1"] = Product(
        url="https://www.savana.com/details/1", ok=True, title="Cherry Cable Cover",
        price=199, mrp=390, method="savana")                    # store price changes

    r = client.post("/refresh?force=true", headers=H).json()
    assert r["checked"] == 0                                    # bought item not fetched
    assert client.get(f"/items/{item['id']}", headers=H).json()["price"] == 273

def test_items_filtered_by_status(client):
    client.post("/items", json={"name": "Watch", "price": 1999}, headers=H)
    frother = client.post("/items", json={"name": "Frother", "price": 439}, headers=H).json()
    client.patch(f"/items/{frother['id']}", json={"status": "later"}, headers=H)

    def names(status):
        return [i["name"] for i in client.get(f"/items?status={status}", headers=H).json()]

    assert names("planned") == ["Watch"]
    assert names("later") == ["Frother"]
    assert names("purchased") == []
    assert sorted(names("all")) == ["Frother", "Watch"]
    assert client.get("/items?status=latr", headers=H).status_code == 422

def test_purchased_price_can_be_set_and_edited(client):
    item = client.post("/items", json={"name": "Frother", "price": 439}, headers=H).json()
    url = f"/items/{item['id']}"

    item = client.patch(url, json={"status": "purchased", "purchased_price": 399}, headers=H).json()
    assert item["purchased_price"] == 399                        # your price beats the listed 439

    item = client.patch(url, json={"purchased_price": 380}, headers=H).json()
    assert item["purchased_price"] == 380                        # editable afterwards

    other = client.post("/items", json={"name": "Brush", "price": 170}, headers=H).json()
    other = client.patch(f"/items/{other['id']}", json={"purchased_price": 100}, headers=H).json()
    assert other["purchased_price"] is None                      # not bought -> ignored

def test_price_history_for_an_item(client):
    item = client.post("/items/from-link", json={"url": "https://www.savana.com/details/1"}, headers=H).json()
    client.catalogue["https://www.savana.com/details/1"] = Product(
        url="https://www.savana.com/details/1", ok=True, title="Cherry Cable Cover",
        price=250, mrp=390, method="savana")
    client.post(f"/items/{item['id']}/refresh", headers=H)

    history = client.get(f"/items/{item['id']}/history", headers=H).json()
    assert [h["price"] for h in history] == [273, 250]          # saved, then dropped
    assert client.get("/items/999/history", headers=H).status_code == 404


def test_amazon_links_reduce_to_dp_asin():
    expected = "https://www.amazon.in/dp/B0DBJ7VRJ2"
    assert clean_url("https://www.amazon.in/dp/B0DBJ7VRJ2?_encoding=UTF8") == expected
    assert clean_url("https://www.amazon.in/Aesthetic-Highlighter/dp/B0DBJ7VRJ2/ref=sr_1_3?crid=X&th=1") == expected
    assert clean_url("https://www.amazon.in/gp/product/B0DBJ7VRJ2?pf_rd_r=ABC") == expected


PHONE_PAGE = (
    '<html><head><link rel="canonical" href="https://www.amazon.in/Pastel-Highlighters/dp/B0TESTHTML?s=bazaar"/></head>'
    '<body><span id="productTitle">Pastel Highlighters</span>'
    '<div class="priceToPay"><span class="a-offscreen">₹289</span></div></body></html>')


def test_add_from_phone_html_with_short_link(client):
    form = {"url": "https://amzn.in/d/xyz"}
    page = {"html": ("page.html", PHONE_PAGE, "text/html")}
    r = client.post("/items/from-html", data=form, files=page, headers=H)
    assert r.status_code == 201
    item = r.json()
    assert item["name"] == "Pastel Highlighters" and item["price"] == 289
    assert item["links"][0]["url"] == "https://www.amazon.in/dp/B0TESTHTML"   # from the canonical tag

    assert client.post("/items/from-html", data=form, files=page, headers=H).status_code == 409   # duplicate


def test_from_html_falls_back_to_server_for_other_stores(client):
    loading_page = "<html><title>Loading…</title></html>"           # e.g. a Savana share page
    form = {"url": "https://www.savana.com/details/1"}
    item = client.post("/items/from-html", data=form,
                       files={"html": ("p.html", loading_page, "text/html")}, headers=H).json()
    assert item["name"] == "Cherry Cable Cover" and item["price"] == 273   # came from the server fetch


def test_from_html_never_falls_back_for_amazon(client):
    no_price = '<html><body><span id="productTitle">Mystery Pen</span></body></html>'
    form = {"url": "https://www.amazon.in/dp/B0NOPRICE1"}
    item = client.post("/items/from-html", data=form,
                       files={"html": ("p.html", no_price, "text/html")}, headers=H).json()
    assert item["name"] == "Mystery Pen" and item["needs_price"]

def test_savana_links_keep_only_product_and_colour():
    expected = "https://www.savana.com/details/1789982?vid=6"
    assert clean_url("https://www.savana.com/details/1789982?vid=6&shem=aimgspe%2C") == expected
    assert clean_url("https://savana.com/details/printed-pullover-t-shirt-1789982?ub_cl=in_en-IN&vid=6") == expected
    assert clean_url("https://www.savana.com/details/1789982?vid=2") != expected      # another colour = another link


def test_phone_refresh_list_and_upload(client):
    item = client.post("/items/from-link", json={"url": "https://amzn.in/d/watch"}, headers=H).json()
    client.post("/items/from-link", json={"url": "https://www.savana.com/details/1"}, headers=H)

    due = client.get("/refresh/phone-list?force=true", headers=H).json()
    assert [d["url"] for d in due] == ["https://www.amazon.in/dp/B0WATCH"]    # Amazon only
    assert client.get("/refresh/phone-list", headers=H).json() == []         # just checked: cooldown

    page = ('<html><body><span id="productTitle">Fastrack Ryz Watch</span>'
            '<div class="priceToPay"><span class="a-offscreen">₹1,799</span></div></body></html>')
    upload = {"html": ("p.html", page, "text/html")}
    r = client.post(f"/links/{due[0]['link_id']}/from-html", files=upload, headers=H).json()
    assert r["ok"] and r["old_price"] == 1999 and r["new_price"] == 1799

    item = client.get(f"/items/{item['id']}", headers=H).json()
    assert item["price"] == 1799 and item["links"][0]["lowest_price_seen"] == 1799
    assert client.post("/links/999/from-html", files=upload, headers=H).status_code == 404




def test_database_not_locked_while_store_page_downloads(client, tmp_path):
    """While we wait for a slow store, other changes (like editing the budget)
    must still work. Before the fix, adding a link locked the database for the
    whole download, and every other change failed with 'database is locked'."""
    results = []

    def slow_store(url):
        # Pretend the store is still sending its page. Meanwhile, try a write
        # from a second connection with no patience at all (timeout=0).
        other = sqlite3.connect(tmp_path / "test.db", timeout=0)
        try:
            other.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('budget', '5000')")
            other.commit()
            results.append("write worked")
        except sqlite3.OperationalError as exc:      # "database is locked"
            results.append(str(exc))
        finally:
            other.close()
        return Product(url=url, ok=True, title="Slow Store Lamp", price=999, method="json-ld")

    main.app.dependency_overrides[main.get_extract] = lambda: slow_store
    r = client.post("/items/from-link", json={"url": "https://slow.example/lamp"}, headers=H)

    assert r.status_code == 201
    assert r.json()["name"] == "Slow Store Lamp"
    assert results == ["write worked"]