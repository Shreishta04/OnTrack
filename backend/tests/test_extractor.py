"""Offline tests: fake store pages, so the logic can be checked without the internet."""
import json
from extractor import extract, clean_url, parse_price, Page

AMAZON = """<html><body>
<span id="productTitle"> Maybelline Instant Age Rewind Eraser Concealer </span>
<div id="corePriceDisplay_desktop_feature_div"><span class="a-price"><span class="a-offscreen">₹749.00</span></span>
<span class="basisPrice">M.R.P.: <span class="a-price a-text-price" data-a-strike="true"><span class="a-offscreen">₹899.00</span></span></span></div>
<img id="landingImage" src="https://m.media-amazon.com/x.jpg"></body></html>"""

# Visible price block missing, but the hidden twister input carries it.
AMAZON_HIDDEN_PRICE = """<html><body><span id="productTitle">Coffee Mixer</span>
<input type="hidden" id="twister-plus-price-data-price" value="299.0"></body></html>"""

AMAZON_JSON_PRICE = """<html><body><span id="productTitle">Bottle Cleaner</span>
<script>var data = {"priceAmount":199.00,"currencySymbol":"₹"};</script></body></html>"""

AMAZON_NO_BUYBOX = """<html><body><span id="productTitle">Mars Sinful</span>
<a>See All Buying Options</a></body></html>"""

AMAZON_CAPTCHA = "<html><form action='/errors/validateCaptcha'></form></html>"

JSON_LD = """<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@graph":[{"@type":"BreadcrumbList"},
 {"@type":"Product","name":"Fastrack Ryz Women Smartwatch","image":["https://f.in/a.jpg"],
  "offers":{"@type":"Offer","price":"2499.00","priceCurrency":"INR"}}]}
</script></head></html>"""

META_NO_PRICE = '<html><head><meta property="og:title" content="Cherry Data Cable Cover"></head></html>'

SHOPIFY_PAGE = '<html><script src="https://cdn.shopify.com/x.js"></script></html>'
SHOPIFY_PRODUCT_JS = json.dumps({"title": "Evil Eye Charm", "price": 14900, "featured_image": "//cdn.shopify.com/e.jpg"})


def fake_fetch(routes, redirects=None, status=200):
    """Returns a fetcher that serves pages from a dict instead of the internet."""
    redirects = redirects or {}

    def fetch(url):
        url = redirects.get(url, url)
        key = url.split("://", 1)[1].split("?")[0]
        return Page(status=status, url=url, text=routes.get(key, ""))
    return fetch


def test_amazon_short_link_redirect_and_price():
    fetch = fake_fetch({"www.amazon.in/dp/B0TEST": AMAZON},
                       redirects={"https://amzn.in/d/abc": "https://www.amazon.in/dp/B0TEST"})
    p = extract("https://amzn.in/d/abc", fetch)
    assert p.ok and p.price == 749 and "Maybelline" in p.title and p.method == "amazon"
    assert p.mrp == 899


def test_amazon_hidden_input_fallback():
    p = extract("https://www.amazon.in/dp/X", fake_fetch({"www.amazon.in/dp/X": AMAZON_HIDDEN_PRICE}))
    assert p.ok and p.price == 299


def test_amazon_embedded_json_fallback():
    p = extract("https://www.amazon.in/dp/X", fake_fetch({"www.amazon.in/dp/X": AMAZON_JSON_PRICE}))
    assert p.ok and p.price == 199


def test_amazon_no_buybox_explained():
    p = extract("https://www.amazon.in/dp/X", fake_fetch({"www.amazon.in/dp/X": AMAZON_NO_BUYBOX}))
    assert not p.ok and p.title == "Mars Sinful" and "no main seller" in p.error


def test_amazon_captcha_is_reported():
    p = extract("https://www.amazon.in/dp/X", fake_fetch({"www.amazon.in/dp/X": AMAZON_CAPTCHA}))
    assert not p.ok and "bot-check" in p.error


def test_http_403_reported():
    p = extract("https://www.fastrack.in/p.html", fake_fetch({}, status=403))
    assert not p.ok and "403" in p.error


def test_json_ld_inside_graph():
    p = extract("https://www.fastrack.in/product/ryz.html", fake_fetch({"www.fastrack.in/product/ryz.html": JSON_LD}))
    assert p.ok and p.price == 2499 and p.method == "json-ld"


def test_meta_without_price_explains_why():
    p = extract("https://sharein.savana.com/cc/x", fake_fetch({"sharein.savana.com/cc/x": META_NO_PRICE}))
    assert not p.ok and p.title == "Cherry Data Cable Cover" and "JavaScript" in p.error


# Trimmed from the real sharein.savana.com page: spinner + delayed JS redirect.
SAVANA_SHARE = """<html><head>
<meta property='og:title' content='Cherry Pattern Data Cable Cover' />
<script>
  const timer = setTimeout(function () {
    const link = 'https://in.savana.com/details/1801032?utm_source=Free&utm_medium=ItemShare&vid=327';
    if (!['','/'].includes(link)) { window.location.replace(decodeURIComponent(link)); }
  }, 800)
</script></head><body><div class="load-box"></div></body></html>"""

SAVANA_REAL = """<html><head><script type="application/ld+json">
{"@type":"Product","name":"Cherry Pattern Data Cable Cover","offers":{"price":"199","priceCurrency":"INR"}}
</script></head></html>"""


# Real layout: two copies of the product data, only the second has promotePrice,
# plus a recommended product that must be ignored.
SAVANA_PRODUCT_PAGE = """<script>window.__ICE_APP_DATA__={
"/n/api/trade/intention/item/detail":{"isWish":false,"goodsId":1801032,"goodsName":"Cherry Pattern Data Cable Cover",
  "shortGoodsName":"Cherry","isPromotion":true,"salesPrice":390,"vipPrice":null,"salesPriceText":"₹390",
  "images":[{"picThumb":"https://img201.savana.com/goods-pic/abc_w1440_q90"}]},
"recs":[{"goodsId":555,"goodsName":"Cheap Phone Case","isPromotion":true,"salesPrice":150,"promotePrice":99}],
"/n/api/intention/item/v4/detail":{"isWish":false,"goodsId":1801032,"goodsName":"Cherry Pattern Data Cable Cover",
  "isPromotion":true,"salesPrice":390,"promotePrice":273,"promotePriceText":"₹273"}}</script>"""


def test_savana_uses_promo_price_and_ignores_recommendations():
    fetch = fake_fetch({"www.savana.com/details/1801032": SAVANA_PRODUCT_PAGE})
    p = extract("https://www.savana.com/details/1801032?vid=327", fetch)
    assert p.ok and p.method == "savana"
    assert p.price == 273 and p.mrp == 390          # not 390, and not the ₹99 recommendation
    assert p.title == "Cherry Pattern Data Cable Cover"


def test_js_redirect_share_page_is_followed():
    fetch = fake_fetch({"sharein.savana.com/cc/details/x": SAVANA_SHARE,
                        "in.savana.com/details/1801032": SAVANA_REAL})
    p = extract("https://sharein.savana.com/cc/details/x", fetch)
    assert p.ok and p.price == 199 and p.url.startswith("https://in.savana.com/details/1801032")
    assert "utm_source" not in p.url


def test_big_pages_never_treated_as_redirects():
    big = JSON_LD + "<script>location.href='https://evil.example/'</script>" + " " * 25_000
    p = extract("https://www.fastrack.in/product/ryz.html", fake_fetch({"www.fastrack.in/product/ryz.html": big}))
    assert p.ok and p.price == 2499


def test_shopify_collection_rejected_and_product_parsed():
    routes = {"comeagain.co.in/collections/charms": SHOPIFY_PAGE,
              "comeagain.co.in/products/evil-eye": SHOPIFY_PAGE,
              "comeagain.co.in/products/evil-eye.js": SHOPIFY_PRODUCT_JS}
    col = extract("https://comeagain.co.in/collections/charms", fake_fetch(routes))
    assert not col.ok and "collection" in col.error
    prod = extract("https://comeagain.co.in/products/evil-eye", fake_fetch(routes))
    assert prod.ok and prod.price == 149 and prod.image.startswith("https:")


def test_tracking_params_stripped():
    assert clean_url("https://x.in/p?fbclid=abc&utm_source=fb&variant=42&ad_id=9") == "https://x.in/p?variant=42"
    assert clean_url("https://www.amazon.in/dp/B0X?psc=1&social_share=cm_sw") == "https://www.amazon.in/dp/B0X"
    assert clean_url("https://www.amazon.in/Name/dp/B0X/ref=sr_1_19?sr=8-19") == "https://www.amazon.in/Name/dp/B0X"


def test_parse_price_formats():
    assert parse_price("₹1,299.00") == 1299
    assert parse_price("Rs. 79") == 79
    assert parse_price(2499) == 2499
    assert parse_price("out of stock") is None




def test_slow_store_gives_up_after_total_time_limit():
    """One add can need several downloads (a page that redirects twice, say).
    All of them together must stop after 25 s, so "Adding..." can't hang for minutes."""
    from extractor import deadline_fetcher

    now = [0.0]                                   # a fake clock we move by hand
    timeouts = []

    def slow_get(url, timeout):
        timeouts.append(timeout)
        now[0] += 10                              # every download takes 10 s
        # a tiny "redirect" page, like Savana share links, so extract() keeps going
        return Page(200, url, '<script>location.href = "https://shop.example/next"</script>')

    p = extract("https://shop.example/start", deadline_fetcher(slow_get, total=25, clock=lambda: now[0]))

    assert timeouts == [20, 15, 5]                # each download only gets the time that's left
    assert not p.ok and "took too long" in p.error


