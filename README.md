# OnTrack

> A budget-aware wishlist for Indian online shopping. Paste a product link from any store, and OnTrack pulls the product name and price automatically, totals everything you plan to buy, and shows what's left of your monthly budget.

**Status:** 🚧 In development. Price extractor ✅ · Backend API ✅ · iPhone Shortcut 🚧 (in progress on `feature/phone-fetch`) · Frontend ⏳ · Deployment ⏳

---

## The problem

On a tight monthly budget, the list of things I want to buy keeps growing while my salary runs out. The items are scattered across Amazon, Myntra, Savana, small Shopify brands and more. I tracked them in my phone's Notes app, which meant:

- copying links by hand,
- typing every product name and price by hand,
- adding everything up by hand, and redoing it whenever a price changed,
- comparing the same product across stores by hand.

**Goal:** paste a link, and everything else is automatic.

## Does this already exist?

Before building, I checked existing apps. They fall into two groups that don't overlap:

| Type | Examples | What they do | What's missing |
|---|---|---|---|
| Universal wishlists | Moonsift, WishUpon, Chestr, Sortd | Paste a link from any store, auto-fetch name and price, price-drop alerts | No budget: nothing to measure the list against |
| Budget shopping lists | Various "wish list / budget" apps | Set a budget, total the items | Prices are typed in by hand; no link extraction |

Most universal wishlists are also built for US/UK stores, so coverage of Indian shops is patchy. **The gap OnTrack fills:** automatic extraction from Indian stores, combined with a monthly budget.

## Features

**Saving items**
- **Paste a link → item saved** with name, current price, MRP and image
- **One item, several stores:** e.g. the same watch on Amazon and Fastrack. Only the **cheapest** link counts toward the budget, so items are never counted twice
- **Duplicate detection:** the same product shared twice, even via a short link or with different tracking junk, is rejected
- **Manual items** for anything without a usable link

**Lists and buying**
- Every item is in one of three lists: **planned** (wish list, counts toward the budget), **later** (parked, not counted), **purchased** (bought)
- Items move freely between lists, and **every move is recorded** with a timestamp
- **Mark as bought** saves the purchase price and date; the price can be edited afterwards (coupons, bank offers). **Undo** clears them
- Ask for one list at a time (`?status=planned|later|purchased|all`) for the app's tabs

**Budget**
- **Total uses the discounted price**; MRP is shown alongside, with total savings
- **Spent this month** comes off the budget: `remaining = budget − spent this month − planned`
- **What fits:** planned items are walked in priority order, and each is marked as fitting the budget or not

**Prices**
- **Refresh on demand:** a button to re-check prices. Bought items are skipped
- **Price history** per item: every check, oldest first, ready for a chart ("↓ ₹40 since you saved it", lowest price seen)
- **Graceful failures:** if a store blocks a check, the last known price is kept and the reason is shown

## Architecture

```
iPhone (Shortcut + PWA) / laptop browser
                │  HTTPS + JSON
                ▼
     FastAPI backend (Python)
      ├── main.py       HTTP layer: routes, validation, auth, error → status code
      ├── services.py   Business rules: lists, budget, cheapest link, refresh
      ├── db.py         Database tables and connections
      └── extractor.py  Product link → name, price, MRP, image
                │
                ▼
        SQLite (local) → Postgres (when hosted)
```

The layers are kept separate on purpose. `services.py` doesn't know about HTTP, so its rules can be tested directly and reused (for example by a future bot). All SQL lives in `db.py` and `services.py`, so moving from SQLite to Postgres is a contained change.

**Fetching is separate from parsing.** The extractor never downloads anything itself; it calls whatever *fetcher* it is given. Tests pass a fake one, so the parsers are tested without the internet. The same seam is what will let the iPhone do the downloading (see challenge 10).

### Data model

```
items             a thing I want to buy ("Smartwatch")
  │                 status: planned / later / purchased, plus purchase price and date
  ├── links       where it's sold (Amazon ₹1,999 · Fastrack ₹2,499)
  │     └── price_history   one row per successful price check
  └── status_changes        one row per move between lists (from → to, when)
settings          key/value (the monthly budget)
```

Deleting an item removes its links, price history and status history with it (`ON DELETE CASCADE`).

## Tech stack and why

| Part | Choice | Why |
|---|---|---|
| Backend language | **Python** | Best scraping ecosystem (`curl_cffi`, BeautifulSoup) and fast iteration. Considered Java (too heavy for a small API) and Node.js (its browser-impersonation libraries are less mature, and that turned out to be the hardest part of the project) |
| API framework | **FastAPI** | Small amount of code, automatic validation with Pydantic, free interactive docs at `/docs` |
| Fetching | **curl_cffi** | Reproduces Chrome's TLS handshake. See "Challenges" below |
| Parsing | **BeautifulSoup + lxml**, regex for embedded JSON | Standard, robust HTML parsing |
| Database | **SQLite** now → **Postgres** when hosted | SQLite needs no setup locally; hosted servers don't keep local files, so production needs a separate database |
| Frontend | **React + TypeScript** (planned) | Browsers only run JavaScript; React is the most widely used frontend library |
| App type | **PWA** (Progressive Web App) | One codebase that runs in any browser and installs on the iPhone home screen. No App Store needed |
| Saving from other apps | **iOS Shortcut** | iOS doesn't let PWAs appear in the share sheet, but a Shortcut can, and it can call the API |

## Challenges and how they were solved

### 1. Amazon showed the title but no price

**Symptom:** the extractor found every Amazon product title but no price, even though the price was plainly visible in the browser.

**Cause:** Amazon decides what page to send based on who's asking. Python's HTTP library has a distinctive **TLS fingerprint** (the exact way it sets up an encrypted connection), which doesn't match any real browser. Amazon recognised it and sent a cut-down page without the price block. Faking the `User-Agent` header doesn't help, because the handshake happens before any headers are sent.

**Fix:** switched from `httpx` to **`curl_cffi`**, which performs the same TLS handshake as Chrome. Also added several fallback places to find the price (different page layouts, hidden form inputs, embedded JSON), because Amazon's layout varies by category.

### 2. Fastrack returned HTTP 403 Forbidden

**Cause and fix:** the same bot detection, but stricter, with an outright refusal. The `curl_cffi` switch fixed it too.

### 3. Savana share links led to a "loading" page

**Symptom:** a Savana share link returned only a spinner page with a title and no price.

**Cause:** the share link isn't the product page. It's a tiny page whose **JavaScript** waits 800 ms and then redirects to the real one. HTTP libraries follow server redirects (301/302) automatically, but never run JavaScript.

**Fix:** detect redirect scripts (`location.replace(...)`, `location.href = ...`, meta refresh) and follow them, **only on small pages** (< 20 KB). A real product page may contain `location.href` inside an unrelated script, and following that would take the extractor off the product page.

### 4. Savana's price lives in embedded JSON, with traps

**Discovery:** Savana renders the price with JavaScript, but the server embeds the product data in the page as JSON for its own scripts to use. That data is more stable to read than visible text: `salesPrice` (MRP) and `promotePrice` (the discounted price).

Three bugs came up, each caught by a test:
- The page contains **two copies** of the product data from different internal APIs, and only one has `promotePrice`. Reading only the first gave the MRP (₹390) instead of the real price (₹273). **Fix:** read every copy and take the lowest price.
- A nearby **recommended product's** price (₹99) leaked into our item. **Fix:** only read blocks whose `goodsId` matches the ID in the URL, and stop each block where the next product begins.
- Python regex matches can't overlap, so the first match's look-ahead window swallowed the second copy. **Fix:** use a lookahead `(?=...)`, which reads ahead without consuming text.

### 5. Come Again (Shopify) has no single-product links

Shopify stores expose any product as JSON at `<product-url>.js`, which is easy and reliable. But Come Again's charm builder puts every charm on one collection page. Reading the **cart** isn't possible from a server either, because a Shopify cart is tied to a cookie in the shopper's own browser.

**For now:** the extractor detects collection pages and explains why it can't use them, and the item can be added manually. **Later:** an iOS Shortcut can run JavaScript inside Safari (with the user's cookies) to read `/cart.js` and import the whole cart as one item.

### 6. The same item counted twice

The smartwatch was saved from both Amazon and Fastrack, so a naive total added both prices. This led to the **items vs links** data model: one item can have many links, and only the cheapest counts toward the budget.

### 7. Messy URLs, and a duplicate bug found by using the app

Links shared from apps carry tracking parameters (`fbclid`, `utm_*`, `social_share`, `ref=…`), which are stripped so the same product saved twice is recognised as a duplicate.

Trying the API by hand, I noticed a saved Amazon link still ended in `?_encoding=UTF8`. Duplicate detection compares cleaned URLs, so the same product pasted from somewhere else would have been saved **twice** and counted twice in the budget. Adding `_encoding` to the block-list would only fix this one case: Amazon has dozens of such parameters and keeps adding more, and it also puts the product title in the path (`/Aesthetic-Highlighter/dp/B0DBJ7VRJ2`).

**Fix:** for Amazon, switch from a **block-list** (remove known junk) to an **allow-list** (keep only what identifies the product). Every Amazon product, including each colour or size variant, has a 10-character ID (ASIN) after `/dp/` or `/gp/product/`. Every Amazon link is reduced to `https://www.amazon.in/dp/<ASIN>`, so all forms of a link collapse to one string.

### 8. Refreshing prices without getting blocked

Re-checking every price each time the app opens would look like a bot and risks CAPTCHAs. **Decision:** refresh only when the user taps a button. Even then, links checked in the last hour are skipped (unless forced), at most 3 are fetched at once, requests are spaced out with random pauses, and **bought items are never re-checked**. "Later" items still are, because a price drop is exactly what might move one back to the wish list.

### 9. Moving between lists without losing history

A single `status` column only knows where an item is *now*. Once something moved from planned to later, the fact that it was ever planned was gone. **Fix:** a `status_changes` table that records every move. Decisions made along the way:
- The history row is written **in the same transaction** as the change it describes, so a rolled-back change never leaves a history row behind.
- The **old status is read before updating**, since the update overwrites it.
- Only **real moves** are recorded: re-sending the same status (a double tap) writes nothing, which a test checks.

### 10. Datacenter IPs: fetching on the phone instead

**Problem:** extraction works from a home connection, but hosted servers use **datacenter IP addresses**, which Amazon treats with much more suspicion than home or mobile ones.

**Planned solution: split fetching from parsing.** The iPhone downloads the page over its own connection (which looks like a normal shopper), and the server only reads it with the same parsers.

**Validated:** a three-step test Shortcut downloaded an Amazon page on both Wi-Fi and mobile data. Both came back as the full desktop product page with no bot-check, and the existing extractor read the title, price (₹289), MRP (₹699) and image from it without any changes. The server side is being built on the `feature/phone-fetch` branch.

### Known limits

- **Month boundary:** times are stored in UTC, which is 5½ hours behind India. A purchase between midnight and 5:30 am on the 1st counts toward the previous month. To be fixed at deployment.

## Store support

| Store | Method | Status |
|---|---|---|
| Amazon.in (incl. `amzn.in` short links) | Chrome-like fetch + selectors / embedded price data | ✅ |
| Fastrack | JSON-LD (`schema.org/Product`) | ✅ |
| Savana (incl. share links) | JS redirect follow + embedded app data | ✅ |
| Shopify stores (Come Again, Littlebox, …) | `/products/<handle>.js`, JSON-LD fallback | ✅ single products · ⏳ carts |
| Myntra, Ajio, Meesho | Not tested yet | ⏳ |

## Getting started (Windows)

Requires Python 3.10+.

```powershell
git clone https://github.com/Shreishta04/OnTrack.git
cd OnTrack
python -m venv .venv
.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
cd backend
pip install -r requirements.txt
Copy-Item .env.example .env         # then set ONTRACK_API_KEY in .env
```

Generate an API key:
```powershell
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

Run the tests, then the server (from the `backend` folder):
```powershell
pytest -q
uvicorn main:app --reload
```
Open http://127.0.0.1:8000/docs to try every endpoint in the browser.

Try the extractor on its own:
```powershell
python extractor.py https://amzn.in/d/xxxxxx
python extractor.py -f links.txt --debug     # --debug saves each fetched page to debug/
```

## API overview

All endpoints except `/health` require the `X-API-Key` header.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/summary` | Budget, discounted total, spent this month, remaining, savings vs MRP, what fits, all items |
| `PUT` | `/budget` | Set the monthly budget |
| `GET` | `/items?status=` | List items: `planned`, `later`, `purchased` or `all` (default) |
| `GET` | `/items/{id}` | One item with its links |
| `GET` | `/items/{id}/history` | Every price check for the item's links, oldest first |
| `POST` | `/items/from-link` | Save an item from a product link |
| `POST` | `/items` | Save a manual item (name + price) |
| `POST` | `/items/{id}/links` | Add another store's link to an item |
| `PATCH` | `/items/{id}` | Edit name, status, priority, manual price, note, purchased price |
| `DELETE` | `/items/{id}` · `/links/{id}` | Remove an item or a link |
| `POST` | `/refresh?force=` | Re-check prices (skips recently checked links and bought items) |
| `POST` | `/items/{id}/refresh` | Re-check one item |

## Project structure

```
OnTrack/
├── backend/
│   ├── main.py            FastAPI routes
│   ├── services.py        business logic
│   ├── db.py              SQLite schema
│   ├── extractor.py       product link → details
│   ├── tests/             offline tests (fake pages, fake extractor), 32 passing
│   ├── requirements.txt
│   └── .env.example       settings template (real .env is git-ignored)
└── frontend/              (coming next)
```

## Roadmap

- [x] Price extractor for Amazon, Fastrack, Savana, Shopify
- [x] Backend API with budget, multi-link items, price history, on-demand refresh
- [x] Lists (planned / later / purchased) with move history, purchases and spent-this-month budget
- [x] Validate phone-side fetching (datacenter IP problem)
- [ ] 🚧 `POST /items/from-html` so the phone can send pages it fetched itself (`feature/phone-fetch`)
- [ ] 🚧 iOS Shortcut: "Add to OnTrack" from the share sheet (`feature/phone-fetch`)
- [ ] iOS Shortcut: "Refresh prices" through the phone (could run daily with an iOS Automation)
- [ ] React + TypeScript PWA frontend
- [ ] Deploy: frontend (Vercel), backend (always-on host), Postgres; fix the UTC month boundary
- [ ] Myntra / Ajio / Meesho support
- [ ] Shopify cart import (Come Again charm bracelets)

## Development log

**2026-10-05**
- Researched existing apps; chose a Python backend, React PWA and iOS Shortcut
- Built the extractor; solved Amazon/Fastrack bot detection with `curl_cffi`, plus Savana's JavaScript redirects and embedded JSON
- Set up venv, git and GitHub on Windows (two GitHub accounts on one machine)
- Built the FastAPI backend with SQLite, an items/links/price-history model and 24 passing tests
- Identified the datacenter-IP risk; designed phone-side fetching as the fix
- Replaced the `planned` true/false flag with a `status` field (planned / later / purchased) so items can move between lists; added a `status_changes` table for history
- Recorded every real move between lists, in the same transaction as the change
- Marking an item as bought now saves its purchase price and date (editable afterwards); undo clears them
- Summary subtracts what was spent this month; refresh skips bought items
- Added `GET /items?status=` for the app's tabs and `GET /items/{id}/history` for price charts
- Found a duplicate-detection bug by using the API (`?_encoding=UTF8`); replaced the Amazon block-list with an ASIN allow-list
- Validated phone-side fetching on Wi-Fi and mobile data; the existing extractor read the phone's page unchanged. 32 tests passing
- Started the `feature/phone-fetch` branch for the server side of phone fetching