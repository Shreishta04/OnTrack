"""
Product link -> {title, price, image} extractor.

Strategies are tried from most reliable to least reliable:
  1. Shopify JSON endpoint  (Littlebox, Come Again, many small Indian brands)
  2. Amazon-specific HTML selectors + embedded price data
  3. JSON-LD schema.org/Product  (the "standard" most stores embed for Google)
  4. Meta tags (OpenGraph / itemprop)  - last resort

Usage:
    python extractor.py <url> [<url> ...]
    python extractor.py -f links.txt
    python extractor.py -f links.txt --debug     # also saves each page to debug/
"""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from bs4 import BeautifulSoup

# Tracking junk added by ads/social apps. Removing it gives a clean, stable URL
# (so the same product saved twice is recognised as a duplicate).
TRACKING_PARAMS = re.compile(
    r"^(utm_.*|fbclid|gclid|ref|ref_|tag|campaign_id|ad_id|sr|qid|ub_cl|skcPGs|"
    r"social_share|psc|smid|th|lang)$"
)
AMAZON_ASIN = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})")
CANONICAL_LINK = re.compile(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']', re.I)
SAVANA_ID = re.compile(r"/details/(?:[^/?]*-)?(\d+)")

@dataclass
class Page:
    status: int
    url: str        # final URL after redirects
    text: str


# A "fetcher" is any function url -> Page. The real one uses curl_cffi; tests
# pass a fake one. Keeping network code behind this seam is what lets the
# parsing logic be tested without the internet.
Fetcher = Callable[[str], Page]


# Time limits for downloading store pages. One add can need several downloads
# (the page, a redirect hop, Shopify's .js lookup), so besides a limit per
# download there is a limit for the whole add.
REQUEST_TIMEOUT = 20      # seconds for any single download
TOTAL_TIMEOUT = 25        # seconds for everything one add is allowed to download


def deadline_fetcher(get: Callable[[str, float], Page], total: float = TOTAL_TIMEOUT,
                     clock: Callable[[], float] = time.monotonic) -> Fetcher:
    """Wrap a downloader so all its downloads TOGETHER stop after `total` seconds.

    Each download gets whatever time is left (at most REQUEST_TIMEOUT). Once
    the time is used up, the next download is refused with a TimeoutError,
    which extract() turns into a normal "Needs a price" error message.
    """
    end = clock() + total

    def fetch(url: str) -> Page:
        left = end - clock()
        if left <= 0:
            raise TimeoutError(f"the store took too long (gave up after {total:g} s)")
        return get(url, min(REQUEST_TIMEOUT, left))

    return fetch


def make_fetcher() -> Fetcher:
    # curl_cffi reproduces Chrome's TLS handshake. Bot-protection services
    # fingerprint that handshake, so a fake User-Agent alone isn't enough.
    from curl_cffi import requests as creq

    session = creq.Session(impersonate="chrome")
    session.headers.update({"Accept-Language": "en-IN,en;q=0.9"})

    def get(url: str, timeout: float) -> Page:
        r = session.get(url, timeout=timeout, allow_redirects=True)
        return Page(status=r.status_code, url=str(r.url), text=r.text)

    return deadline_fetcher(get)


def html_fetcher(url: str, html: str) -> Fetcher:
    """A fetcher for a page someone else already downloaded (e.g. the iPhone).

    The first request gets that page. Any further request (Shopify's .js
    lookup, a redirect hop) gets a 404, because we must not go online for it.
    """
    m = CANONICAL_LINK.search(html)
    page = Page(200, m.group(1) if m else url, html)
    calls = []

    def fetch(u: str) -> Page:
        calls.append(u)
        return page if len(calls) == 1 else Page(404, u, "")
    
    return fetch


@dataclass
class Product:
    url: str
    ok: bool = False
    title: str | None = None
    price: float | None = None    # what you'd pay today
    mrp: float | None = None      # original/struck-through price, when known
    currency: str = "INR"
    image: str | None = None
    method: str | None = None     # which strategy succeeded
    error: str | None = None


# ----------------------------------------------------------------- helpers

def clean_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if "amazon." in parts.netloc and (m := AMAZON_ASIN.search(parts.path)):
        return urlunsplit((parts.scheme, parts.netloc, f"/dp/{m.group(1)}", "", ""))
    if parts.netloc in ("www.savana.com", "savana.com") and (m := SAVANA_ID.search(parts.path)):
        vid = dict(parse_qsl(parts.query)).get("vid")
        query = urlencode({"vid": vid}) if vid else ""
        return urlunsplit(("https", "www.savana.com", f"/details/{m.group(1)}", query, ""))
    query = [(k, v) for k, v in parse_qsl(parts.query) if not TRACKING_PARAMS.match(k)]
    path = re.sub(r"/ref=[^/]*$", "", parts.path)   # Amazon's /ref=sr_1_19 suffix
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), ""))


def parse_price(raw) -> float | None:
    """'₹1,299.00' / '1299' / 1299 / 'Rs. 1,299' -> 1299.0"""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    match = re.search(r"\d[\d,]*(?:\.\d+)?", str(raw))
    return float(match.group().replace(",", "")) if match else None


# ----------------------------------------------------------- strategies

def try_shopify(fetch: Fetcher, url: str, html: str) -> Product | None:
    """Shopify serves any product as JSON at <product-url>.js."""
    if "cdn.shopify.com" not in html and "Shopify" not in html:
        return None
    path = urlsplit(url).path.rstrip("/")

    if "/products/" not in path:
        # A /collections/ page is a list of many products, not one item.
        return Product(url=url, method="shopify",
                       error="This is a category/collection page, not a single product. "
                             "Open the exact item and share that link.")

    base = urlunsplit(urlsplit(url)._replace(path=path, query="", fragment=""))
    page = fetch(base + ".js")
    if page.status != 200:
        return None
    data = json.loads(page.text)
    image = data.get("featured_image")
    if image and image.startswith("//"):
        image = "https:" + image
    return Product(
        url=url, ok=True, method="shopify",
        title=data.get("title"),
        price=data["price"] / 100,   # Shopify .js prices are in paise
        image=image,
    )


# Amazon keeps the price in several places; layouts differ by product category
# and A/B test, so we try visible elements first, then hidden data.
AMAZON_PRICE_SELECTORS = [
    "#corePriceDisplay_desktop_feature_div .priceToPay .a-offscreen",
    "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
    "#corePrice_feature_div .a-price .a-offscreen",
    "#corePrice_desktop .a-price .a-offscreen",
    "#apex_desktop .a-price .a-offscreen",
    "#apex_offerDisplay_desktop .a-price .a-offscreen",
    ".priceToPay .a-offscreen",
    "#priceblock_dealprice", "#priceblock_ourprice", "#price_inside_buybox",
    "#tp_price_block_total_price_ww .a-offscreen",
]
AMAZON_PRICE_PATTERNS = [
    r'id="twister-plus-price-data-price"[^>]*value="([\d.]+)"',
    r'"priceAmount"\s*:\s*([\d.]+)',
    r'"displayPrice"\s*:\s*"([^"]+)"',
]


def try_amazon(soup: BeautifulSoup, url: str, html: str) -> Product | None:
    if "amazon." not in urlsplit(url).netloc:
        return None
    if "validateCaptcha" in html or "Enter the characters you see below" in html:
        return Product(url=url, method="amazon",
                       error="Amazon showed a bot-check page instead of the product.")

    title_el = soup.select_one("#productTitle")
    price = None
    for sel in AMAZON_PRICE_SELECTORS:
        el = soup.select_one(sel)
        if el and (price := parse_price(el.get_text())):
            break
    if price is None:
        whole = soup.select_one(".priceToPay .a-price-whole, #corePriceDisplay_desktop_feature_div .a-price-whole")
        price = parse_price(whole.get_text()) if whole else None
    if price is None:
        for pattern in AMAZON_PRICE_PATTERNS:
            if (m := re.search(pattern, html)) and (price := parse_price(m.group(1))):
                break

    # The struck-through "M.R.P.: ₹279" shown beside the deal price.
    mrp_el = soup.select_one(
        "#corePriceDisplay_desktop_feature_div .basisPrice .a-offscreen, "
        "#corePriceDisplay_desktop_feature_div .a-text-price[data-a-strike] .a-offscreen, "
        ".basisPrice .a-offscreen")
    mrp = parse_price(mrp_el.get_text()) if mrp_el else None

    img_el = soup.select_one("#landingImage, #imgBlkFront")
    if not title_el and price is None:
        return None
    no_buybox = "See All Buying Options" in html or "Currently unavailable" in html
    return Product(
        url=url, ok=price is not None, method="amazon",
        title=title_el.get_text(strip=True) if title_el else None,
        price=price,
        mrp=mrp if (mrp and price and mrp > price) else None,
        image=(img_el.get("data-old-hires") or img_el.get("src")) if img_el else None,
        error=None if price is not None else (
            "Amazon shows no main seller/price for this item right now." if no_buybox
            else "Found the product but couldn't locate the price (run with --debug)."),
    )


def _json_str(raw: str) -> str:
    """Decode a JSON string body (handles \\u escapes, \\" etc.)."""
    try:
        return json.loads(f'"{raw}"')
    except json.JSONDecodeError:
        return raw


def try_savana(url: str, html: str) -> Product | None:
    """Savana (and its sister sites) embed the product-detail API response in
    the page for their own JavaScript. Field meanings:
      salesPrice   = MRP (struck-through)
      promotePrice = discounted price, valid when isPromotion is true
    """
    if "savana." not in urlsplit(url).netloc:
        return None
    # The page embeds several API responses (and recommended products), so only
    # read blocks for THIS product: the id in /details/<id>.
    id_match = re.search(r"/details/(?:[^/?]*-)?(\d+)", urlsplit(url).path)
    goods_id = id_match.group(1) if id_match else r"\d+"
    blocks = re.finditer(
        rf'"goodsId"\s*:\s*{goods_id}\s*,\s*"goodsName"\s*:\s*"((?:[^"\\]|\\.)*)"(?=(.{{0,600}}))',
        html, re.DOTALL)

    title, prices, mrps = None, [], []
    for m in blocks:
        title = title or _json_str(m.group(1))
        # Stop where the next product's data begins, so a nearby recommended
        # item's price can't leak into this one.
        block = re.split(r'"goodsId"\s*:', m.group(2), maxsplit=1)[0]

        def num(field):
            f = re.search(rf'"{field}"\s*:\s*"?([\d.]+)', block)
            return parse_price(f.group(1)) if f else None

        sales, promo = num("salesPrice"), num("promotePrice")
        on_promo = re.search(r'"isPromotion"\s*:\s*true', block) is not None
        price = promo if (on_promo and promo) else sales
        if price is not None:
            prices.append(price)
        if sales is not None:
            mrps.append(sales)

    if not prices:
        return None
    # Different blocks can be incomplete (one copy here lacks promotePrice), and
    # all describe the same product, so the lowest price is the current deal.
    price, mrp = min(prices), max(mrps) if mrps else None
    image = re.search(r'"picThumb"\s*:\s*"([^"]+)"', html)
    return Product(url=url, ok=True, method="savana", title=title, price=price,
                   mrp=mrp if mrp and mrp > price else None,
                   image=image.group(1) if image else None)


def _walk(node):
    """Yield every dict inside nested JSON (JSON-LD is often wrapped in @graph/lists)."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def try_json_ld(soup: BeautifulSoup, url: str) -> Product | None:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        for node in _walk(data):
            types = node.get("@type")
            types = types if isinstance(types, list) else [types]
            if "Product" not in types:
                continue
            offers = node.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price = parse_price(offers.get("price") or offers.get("lowPrice"))
            image = node.get("image")
            if isinstance(image, list):
                image = image[0] if image else None
            if isinstance(image, dict):
                image = image.get("url")
            if price is not None:
                return Product(url=url, ok=True, method="json-ld",
                               title=node.get("name"), price=price, image=image,
                               currency=offers.get("priceCurrency") or "INR")
    return None


def try_meta(soup: BeautifulSoup, url: str) -> Product | None:
    def meta(*names):
        for n in names:
            el = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n}) \
                 or soup.find(attrs={"itemprop": n})
            if el and (el.get("content") or el.get_text(strip=True)):
                return el.get("content") or el.get_text(strip=True)
        return None

    price = parse_price(meta("product:price:amount", "og:price:amount", "price"))
    title = meta("og:title") or (soup.title.get_text(strip=True) if soup.title else None)
    if price is None and title is None:
        return None
    return Product(url=url, ok=price is not None, method="meta", title=title,
                   price=price, image=meta("og:image"),
                   error=None if price is not None else
                   "Got the name but no price - this page probably loads its price with JavaScript.")


# ------------------------------------------------- JavaScript redirects

# Share links (e.g. sharein.savana.com) are tiny "loading..." pages whose
# JavaScript sends the browser on to the real product page. HTTP libraries
# follow server redirects (301/302) automatically, but never run JavaScript,
# so we spot these redirect scripts ourselves.
JS_REDIRECT_PATTERNS = [
    r"""location\.replace\(\s*(?:decodeURIComponent\()?\s*['"](https?://[^'"]+)['"]""",
    r"""location(?:\.href)?\s*=\s*['"](https?://[^'"]+)['"]""",
    r"""const\s+link\s*=\s*['"](https?://[^'"]+)['"]""",
    r"""<meta[^>]+http-equiv=["']?refresh["']?[^>]+url=([^"'>\s]+)""",
]
# Only small pages count as redirect pages. A real product page may contain
# "location.href = ..." in some unrelated script, and we must not follow that.
REDIRECT_PAGE_MAX_CHARS = 20_000
MAX_REDIRECT_HOPS = 3


def find_js_redirect(html: str) -> str | None:
    if len(html) > REDIRECT_PAGE_MAX_CHARS:
        return None
    for pattern in JS_REDIRECT_PATTERNS:
        if m := re.search(pattern, html, re.IGNORECASE):
            return m.group(1)
    return None


# ----------------------------------------------------------------- main

def extract(url: str, fetch: Fetcher, debug_dir: Path | None = None) -> Product:
    try:
        page = fetch(clean_url(url))   # follows amzn.in short links to the real page
        for _ in range(MAX_REDIRECT_HOPS):
            target = find_js_redirect(page.text) if page.status < 400 else None
            if not target:
                break
            page = fetch(clean_url(target))
    except Exception as exc:
        return Product(url=url, error=f"Network error: {exc.__class__.__name__}: {exc}")

    final_url = clean_url(page.url)
    if debug_dir:
        debug_dir.mkdir(exist_ok=True)
        name = re.sub(r"[^A-Za-z0-9]+", "_", urlsplit(final_url).netloc + urlsplit(final_url).path)[:80]
        (debug_dir / f"{name}.html").write_text(page.text, encoding="utf-8")

    if page.status >= 400:
        return Product(url=final_url, error=f"Store returned HTTP {page.status} (blocked or not found)")
    soup = BeautifulSoup(page.text, "lxml")

    best = None
    for attempt in (
        lambda: try_shopify(fetch, final_url, page.text),
        lambda: try_amazon(soup, final_url, page.text),
        lambda: try_savana(final_url, page.text),
        lambda: try_json_ld(soup, final_url),
        lambda: try_meta(soup, final_url),
    ):
        result = attempt()
        if result and result.ok:
            return result
        best = best or result      # keep the first partial result / explanation
    return best or Product(url=final_url, error="Couldn't find product details on this page.")


def main(argv: list[str]) -> None:
    debug = "--debug" in argv
    argv = [a for a in argv if a != "--debug"]
    if argv[:1] == ["-f"]:
        with open(argv[1], encoding="utf-8") as f:
            urls = [l.strip() for l in f if l.strip().startswith("http")]
    else:
        urls = argv
    if not urls:
        print(__doc__)
        return

    fetch = make_fetcher()
    debug_dir = Path("debug") if debug else None
    total = 0.0
    for url in urls:
        p = extract(url, fetch, debug_dir)
        if p.ok:
            total += p.price
            mrp = f" (MRP ₹{p.mrp:,.0f})" if p.mrp else ""
            print(f"✅ ₹{p.price:>9,.0f}  {(p.title or '?')[:60]}{mrp}   [{p.method}]")
        else:
            print(f"❌ {'':>10}  {p.error}\n   {(p.title or '')[:60]}  {p.url[:80]}")
    print(f"\nTotal of items found: ₹{total:,.0f}")
    if debug:
        print("Saved each page's HTML to the debug/ folder.")


if __name__ == "__main__":
    main(sys.argv[1:])
