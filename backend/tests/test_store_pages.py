"""Real store pages, saved from a browser, read the way the phone's page is read.

Each page in tests/pages/ is a product (or list) page someone saved with
Ctrl+U → Ctrl+S, stored gzipped. Every row below says what OnTrack must get
from it, so a change made for one store can't quietly break another.

To add a store: save its page, `gzip -9` it into tests/pages/, add one row.
"""

import gzip
from pathlib import Path

import pytest

from extractor import HOME_PAGE, LIST_PAGE, OUT_OF_STOCK, extract, html_fetcher

PAGES = Path(__file__).parent / "pages"

# file, the address it was saved from, then what must come out:
# (name starts with, price, MRP) for a product, or the explanation when there's no price.
STORES = [
    pytest.param("littleboxindia.html.gz",
                 "https://littleboxindia.com/products/combo-set-of-two-light-brown-black-premium-trousers?variant=46196916093215",
                 ("Combo : Set Of Two Light Brown", 1449, None), None, id="littlebox"),
    pytest.param("meesho.html.gz", "https://www.meesho.com/s/p/9obc3j",
                 None, OUT_OF_STOCK, id="meesho-out-of-stock"),
    pytest.param("victoriassecret.html.gz", "https://www.victoriassecret.in/beauty/fragrance/bombshell-fragrance",
                 None, LIST_PAGE, id="victoriassecret-list-page"),
    # Home pages are full of products and prices: the readers must not pick one of them.
    pytest.param("myntra-home.html.gz", "https://www.myntra.com/", None, HOME_PAGE, id="myntra-home"),
    pytest.param("nykaa-home.html.gz", "https://www.nykaa.com/", None, HOME_PAGE, id="nykaa-home"),
    pytest.param("flipkart-home.html.gz", "https://www.flipkart.com/", None, HOME_PAGE, id="flipkart-home"),
    pytest.param("target-home.html.gz", "https://www.target.com/", None, HOME_PAGE, id="target-home"),
    pytest.param("savana-home.html.gz", "https://www.savana.com/", None, HOME_PAGE, id="savana-home"),
]


def read(file: str, url: str):
    html = gzip.decompress((PAGES / file).read_bytes()).decode("utf-8")
    return extract(url, html_fetcher(url, html))


@pytest.mark.parametrize("file, url, product, explanation", STORES)
def test_store_page(file, url, product, explanation):
    p = read(file, url)
    if product:
        name, price, mrp = product
        assert p.ok, p.error
        assert p.title.startswith(name), p.title
        assert p.price == price
        assert p.mrp == mrp
        assert p.image and p.image.startswith("http")
    else:
        assert not p.ok
        assert p.error == explanation, p.error


def test_every_saved_page_has_a_row():
    """A page added to tests/pages/ without a row here would never be checked."""
    listed = {param.values[0] for param in STORES}
    assert {f.name for f in PAGES.glob("*.html.gz")} == listed


# ----------------------------------------------- the explanations, on their own

def explain(html: str):
    from bs4 import BeautifulSoup

    from extractor import explain_no_price
    return explain_no_price(BeautifulSoup(html, "lxml"))


def ld(block: str) -> str:
    return f'<script type="application/ld+json">{block}</script>'


def test_out_of_stock_written_different_ways():
    for availability in ("OutOfStock", "https://schema.org/OutOfStock", "http://schema.org/SoldOut", "Discontinued"):
        page = ld('{"@type":"Product","name":"Pendant","offers":{"availability":"%s"}}' % availability)
        assert explain(page) == OUT_OF_STOCK, availability
    assert explain('<meta property="product:availability" content="out of stock">') == OUT_OF_STOCK


def test_in_stock_without_a_price_has_no_explanation():
    assert explain(ld('{"@type":"Product","name":"Kurta","offers":{"availability":"InStock"}}')) is None
    assert explain('<meta property="product:availability" content="instock">') is None


def test_a_product_page_with_a_list_of_related_items_is_not_a_list_page():
    """Product pages often add "you may also like" lists; the product wins."""
    page = (ld('{"@type":"Product","name":"Kurta","offers":{"availability":"InStock"}}')
            + ld('{"@type":"ItemList","itemListElement":[{"url":"a"},{"url":"b"},{"url":"c"}]}'))
    assert explain(page) is None


def test_breadcrumbs_are_not_a_list_page():
    assert explain(ld('{"@type":"BreadcrumbList","itemListElement":[{"name":"Home"},{"name":"Beauty"}]}')) is None


# ------------------------------------ data hidden in the page, shaped like real shops
#
# Built from how these shops are documented to store their data (scraping
# write-ups, Stack Overflow). The real pages above are the final word: when a
# store's real product page is saved, it gets a row there.

def page(title: str, body: str, url: str = "https://shop.example/p/123"):
    html = (f'<html><head><meta property="og:title" content="{title}">'
            f'<meta property="og:image" content="https://img.example/og.jpg"></head><body>{body}</body></html>')
    return extract(url, html_fetcher(url, html))


RELATED = '{"name":"Cotton Kurta Set Blue","price":499},{"name":"Linen Shirt","price":799}'


def test_next_js_data_picks_the_product_not_the_related_items():
    p = page("Floral Print Anarkali Kurta - Pink | Brand",
             '<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{'
             f'"related":[{RELATED}],'
             '"product":{"name":"Floral Print Anarkali Kurta - Pink","price":{"value":1299},"mrp":2599,'
             '"images":["https://img.example/kurta.jpg"]}}}}</script>')
    assert (p.method, p.title, p.price, p.mrp, p.image) == (
        "embedded", "Floral Print Anarkali Kurta - Pink", 1299, 2599, "https://img.example/kurta.jpg")


def test_initial_state_with_price_objects_like_flipkart():
    p = page("Apple iPhone 15 (Blue, 128 GB) - Flipkart",
             '<script>window.__INITIAL_STATE__ = {"pageData":{"product":{"titles":{},'
             '"title":"Apple iPhone 15 (Blue, 128 GB)","pricing":{"finalPrice":{"value":61999,"currency":"INR"},'
             '"mrp":{"value":69900}}}}};</script>')
    assert (p.price, p.mrp) == (61999, 69900)


def test_myntra_pdpdata_selling_price_inside_sizes():
    p = page("Buy Puma Men Blue Hybrid Fuego Running Shoes - Sports Shoes for Men | Myntra",
             '<script>window.__myx = {"pdpData":{"name":"Puma Men Blue Hybrid Fuego Running Shoes","mrp":6499,'
             '"sizes":[{"label":"8","sizeSellerData":[{"discountedPrice":2924}]}],'
             '"media":{"albums":[{"name":"default","images":[{"secureSrc":"https://assets.myntra.example/shoe.jpg"}]}]}}}'
             '</script>')
    assert (p.price, p.mrp, p.image) == (2924, 6499, "https://assets.myntra.example/shoe.jpg")


def test_preloaded_state_written_as_a_json_string():
    p = page("Nivea Soft Light Moisturiser 100ml",
             '<script>window.__PRELOADED_STATE__ = JSON.parse("{\\"product\\":{\\"name\\":'
             '\\"Nivea Soft Light Moisturiser 100ml\\",\\"offerPrice\\":\\"₹289\\",\\"mrp\\":\\"₹349\\"}}");</script>')
    assert (p.price, p.mrp) == (289, 349)


def test_no_matching_name_means_no_price():
    """A blob full of other products, none of them this page's: no guessing."""
    p = page("Our Story - About the Brand",
             f'<script id="__NEXT_DATA__" type="application/json">{{"props":{{"items":[{RELATED}]}}}}</script>')
    assert not p.ok


def test_an_mrp_lower_than_the_price_is_ignored():
    p = page("Steel Bottle 1L", '<script>window.__INITIAL_STATE__ = {"p":{"name":"Steel Bottle 1L",'
             '"sellingPrice":599,"mrp":399}};</script>')
    assert (p.price, p.mrp) == (599, None)


def test_microdata():
    p = page("Desk Lamp", '<div itemscope itemtype="https://schema.org/Product"><h1 itemprop="name">Desk Lamp</h1>'
             '<img itemprop="image" src="https://img.example/lamp.jpg">'
             '<div itemprop="offers" itemscope itemtype="https://schema.org/Offer">'
             '<span itemprop="price" content="1499.00">₹1,499</span></div></div>')
    assert (p.method, p.title, p.price, p.image) == ("microdata", "Desk Lamp", 1499, "https://img.example/lamp.jpg")


def test_twitter_price_tags():
    p = page("Tote Bag", '<meta name="twitter:label1" content="Price"><meta name="twitter:data1" content="₹899">')
    assert p.price == 899
