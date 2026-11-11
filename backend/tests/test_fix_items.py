"""fix-items: plain-sentence replies for the Shortcuts, more ways of writing a
price in the standard product data, and refresh not overwriting what the
phone found with the server's (weaker) view of the store.
"""

import logging

from bs4 import BeautifulSoup

import db
import replies
from extractor import NO_PRICE_FROM_BROWSER, NO_PRICE_JAVASCRIPT, Product, try_json_ld
from test_api import H, client  # noqa: F401  (client is a pytest fixture)

PAGE = '<html><head><meta property="og:title" content="{name}"></head><body>{body}</body></html>'


def json_ld(block: str, kind: str = "application/ld+json") -> Product | None:
    soup = BeautifulSoup(f'<html><script type="{kind}">{block}</script></html>', "lxml")
    return try_json_ld(soup, "https://shop.example/p")


def upload(c, url, html, query=""):
    return c.post(f"/items/from-html{query}", data={"url": url},
                  files={"html": ("p.html", html, "text/html")}, headers=H)


# --------------------------------------------------- reading the product data

def test_price_inside_price_specification():
    p = json_ld('{"@type":"Product","name":"Halter Top","offers":{"@type":"Offer",'
                '"priceSpecification":{"@type":"UnitPriceSpecification","price":"24.00","priceCurrency":"USD"}}}')
    assert (p.title, p.price, p.currency) == ("Halter Top", 24.0, "USD")


def test_price_specification_as_a_list_and_offers_inside_offers():
    p = json_ld('{"@type":"Product","name":"Mist","offers":{"@type":"Offer","priceSpecification":'
                '[{"@type":"PriceSpecification"},{"price":2999}]}}')
    assert p.price == 2999
    p = json_ld('{"@type":"Product","name":"Mist","offers":{"@type":"AggregateOffer",'
                '"offers":[{"@type":"Offer","price":"1,499"}]}}')
    assert p.price == 1499


def test_product_group_takes_the_price_from_its_variants():
    p = json_ld('{"@type":"ProductGroup","name":"Teri Bag","image":"https://img/bag.jpg","hasVariant":['
                '{"@type":"Product","offers":{"price":33999,"priceCurrency":"INR"}}]}')
    assert (p.title, p.price, p.image) == ("Teri Bag", 33999, "https://img/bag.jpg")   # name and photo from the group


def test_small_mistakes_in_the_data_are_forgiven():
    trailing_comma = '{"@type":"Product","name":"Kurta","offers":{"price":899,},}'
    line_break = '{"@type":"Product","name":"Kurta\nCotton","offers":{"price":899}}'
    in_a_comment = '<!-- {"@type":"Product","name":"Kurta","offers":{"price":899}} -->'
    for block in (trailing_comma, line_break, in_a_comment):
        assert json_ld(block).price == 899, block
    assert json_ld('{"@type":"Product","name":"Kurta","offers":{"price":899}}',
                   kind="application/ld+json; charset=utf-8").price == 899


def test_still_no_price_when_there_is_none():
    assert json_ld('{"@type":"Product","name":"Kurta"}') is None
    assert json_ld('{not json at all') is None


# ------------------------------------------------------ sentences for phones

def test_money_in_words():
    assert replies.money(124999, "INR") == "₹1,24,999"
    assert replies.money(899.5, "INR") == "₹899.50"
    assert replies.money(1249.5, "USD") == "$1,249.50"
    assert replies.money(26.59, "USD") == "$26.59"
    assert replies.money(450, "USD") == "$450"
    assert replies.money(36.990000000000002, "USD") == "$36.99"


def test_shortcut_gets_a_sentence_when_it_asks(client):
    page = PAGE.format(name="Kurta", body='<script type="application/ld+json">'
                       '{"@type":"Product","name":"Cotton Kurta","offers":{"price":899}}</script>')
    r = upload(client, "https://shop.example/kurta", page, "?reply=text")
    assert r.status_code == 201 and r.headers["content-type"].startswith("text/plain")
    assert r.text == "Added to OnTrack · Cotton Kurta · ₹899"

    again = upload(client, "https://shop.example/kurta", page, "?reply=text")
    assert again.status_code == 409 and again.text == "Already on your list · Cotton Kurta"


def test_without_reply_text_it_is_json_as_before(client):
    page = PAGE.format(name="Kurta", body='<script type="application/ld+json">'
                       '{"@type":"Product","name":"Cotton Kurta","offers":{"price":899}}</script>')
    r = upload(client, "https://shop.example/kurta", page)
    assert r.json()["price"] == 899                     # old Shortcuts keep working


def test_no_price_sentence(client):
    client.catalogue["https://www.target.com/p/top"] = Product(
        url="https://www.target.com/p/top", title="Satin Halter Top", error=NO_PRICE_JAVASCRIPT)
    r = upload(client, "https://www.target.com/p/top", PAGE.format(name="Satin Halter Top", body=""), "?reply=text")
    assert r.text == "Added, but no price yet · Satin Halter Top. Open OnTrack to type one."


def test_errors_are_sentences_too(client):
    page = PAGE.format(name="x", body="")
    wrong_key = client.post("/items/from-html?reply=text", data={"url": "https://shop.example/a"},
                            files={"html": ("p.html", page, "text/html")}, headers={"X-API-Key": "nope"})
    assert wrong_key.status_code == 401 and "doesn't recognise this Shortcut's key" in wrong_key.text
    not_a_link = upload(client, "Source: Victoria's Secret", page, "?reply=text")
    assert not_a_link.status_code == 422 and not_a_link.text.startswith("OnTrack couldn't read that link")


def test_a_broken_upload_is_explained_and_logged(client, caplog):
    broken = b'--XyZ\r\nContent-Disposition: form-data; name="url"\r\n\r\nhttps://shop.example/a\r\n--XyZ\r\nNoColon\r\n'
    headers = {**H, "content-type": "multipart/form-data; boundary=XyZ", "user-agent": "Shortcuts/1"}
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        r = client.post("/items/from-html?reply=text", content=broken, headers=headers)
    assert r.status_code == 400 and r.text.startswith("The page didn't upload properly")
    line = next(m for m in caplog.messages if m.startswith("upload   unreadable form"))
    assert "boundary=XyZ" in line and "Shortcuts/1" in line and H["X-API-Key"] not in line
    plain = client.post("/items/from-html", content=broken, headers=headers)
    assert plain.json()["detail"] == "Invalid multipart data."       # JSON callers see what they always did


def test_refresh_shortcut_line(client):
    item = client.post("/items/from-link", json={"url": "https://amzn.in/d/watch"}, headers=H).json()
    link_id = item["links"][0]["id"]
    page = ('<html><body><span id="productTitle">Fastrack Ryz Watch</span>'
            '<div class="priceToPay"><span class="a-offscreen">₹1,799</span></div></body></html>')
    r = client.post(f"/links/{link_id}/from-html?reply=text", files={"html": ("p.html", page, "text/html")}, headers=H)
    assert r.text == "Fastrack Ryz Watch: ↓ ₹1,799 (was ₹1,999)", r.text


# -------------------------------------------- refresh vs what the phone found

def test_refresh_keeps_the_phones_explanation(client):
    """Added from the phone, no price. The server's refresh then fails too
    (from Singapore, without JavaScript): the phone's explanation stays."""
    url = "https://www.target.com/p/top"
    client.catalogue[url] = Product(url=url, title="Satin Halter Top", error=NO_PRICE_JAVASCRIPT)
    item = upload(client, url, PAGE.format(name="Satin Halter Top", body="")).json()
    assert item["links"][0]["last_error"] == NO_PRICE_FROM_BROWSER
    client.post("/refresh?force=true", headers=H)
    link = client.get(f"/items/{item['id']}", headers=H).json()["links"][0]
    assert link["last_error"] == NO_PRICE_FROM_BROWSER                 # not "…loads its price with JavaScript"
    assert link["last_checked"] is not None


def test_refresh_still_reports_server_failures_for_server_links(client):
    client.post("/items/from-link", json={"url": "https://blocked.example/p"}, headers=H)
    client.catalogue["https://blocked.example/p"] = Product(url="https://blocked.example/p", title="Mystery Item",
                                                            error="Store returned HTTP 471")
    client.post("/refresh?force=true", headers=H)
    items = client.get("/items", headers=H).json()
    assert items[0]["links"][0]["last_error"] == "Store returned HTTP 471"


def test_old_links_table_gets_read_via(client):
    conn = db.connect()
    conn.execute("ALTER TABLE links DROP COLUMN read_via")            # as the live database is today
    conn.commit()
    db.init(conn)
    db.init(conn)
    assert "read_via" in db.columns(conn, "links")
    conn.close()


# ------------------------------------------------- Set up this phone (links)

def test_setup_links_come_from_railway_variables(client, monkeypatch):
    monkeypatch.delenv("ONTRACK_SHORTCUT_ADD_URL", raising=False)
    monkeypatch.delenv("ONTRACK_SHORTCUT_REFRESH_URL", raising=False)
    assert client.get("/setup", headers=H).json() == {"add_shortcut_url": None, "refresh_shortcut_url": None}
    monkeypatch.setenv("ONTRACK_SHORTCUT_ADD_URL", " https://www.icloud.com/shortcuts/abc123 ")
    monkeypatch.setenv("ONTRACK_SHORTCUT_REFRESH_URL", "https://evil.example/shortcuts/x")   # not iCloud: ignored
    assert client.get("/setup", headers=H).json() == {
        "add_shortcut_url": "https://www.icloud.com/shortcuts/abc123", "refresh_shortcut_url": None}
    assert client.get("/setup").status_code == 401
