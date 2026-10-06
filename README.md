# OnTrack

> A budget-aware wishlist for Indian online shopping. Share or paste a product link from any store, and OnTrack pulls the product name and price automatically, totals everything you plan to buy, and shows what's left of your monthly budget.

**Status:** 🚧 In development. Price extractor ✅ · Backend API ✅ · iPhone Shortcuts ✅ (local network) · Web app ✅ (local) · Browser extension ⏳ · Deployment ⏳

---

## The problem

On a tight monthly budget, the list of things I want to buy keeps growing while my salary runs out. The items are scattered across Amazon, Myntra, Savana, small Shopify brands and more. I tracked them in my phone's Notes app, which meant:

- copying links by hand,
- typing every product name and price by hand,
- adding everything up by hand, and redoing it whenever a price changed,
- comparing the same product across stores by hand.

**Goal:** share a link, and everything else is automatic.

## Does this already exist?

Before building, I checked existing apps. They fall into two groups that don't overlap:

| Type | Examples | What they do | What's missing |
|---|---|---|---|
| Universal wishlists | Moonsift, WishUpon, Chestr, Sortd | Paste a link from any store, auto-fetch name and price, price-drop alerts | No budget: nothing to measure the list against |
| Budget shopping lists | Various "wish list / budget" apps | Set a budget, total the items | Prices are typed in by hand; no link extraction |

Most universal wishlists are also built for US/UK stores, so coverage of Indian shops is patchy. **The gap OnTrack fills:** automatic extraction from Indian stores, combined with a monthly budget.

## Features

**Saving items**
- **Share from the iPhone → item saved** with name, current price, MRP and image, via an iOS Shortcut in the Share Sheet
- **Paste a link** (laptop / API) → same result, with the server fetching the page itself
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

**Web app**
- **Budget card:** one big number, "Left after wish list" (or "Over budget" in clay), a bar showing spent / planned / left, and the three totals underneath. **Edit budget** opens a small form right inside the card
- **Tabs:** Wish list · Later · Bought · All, with counts. A single underline glides between them and the list fades in
- **Expandable rows:** product photo (or the name's first letter when there isn't one), name, store, a status badge (Fits budget / Over budget / Needs a price / Parked / Bought), price with MRP struck through. Tap **+** for details: price now, lowest seen, date saved, how much it has dropped, a link to the store, and the actions
- **Actions in every row:** Mark bought, Move to Later / Back to wish list, Undo purchase, Delete (two taps). Each one calls the API and reloads, so the budget card and counts always match the server
- **Paste a link** to add an item from the laptop, with a hint that Amazon works best through the phone
- **When a store won't give a price,** the row shows the real reason (for example *"Amazon showed a bot-check page"*) and a box to type the price by hand
- **Light and dark mode:** follows the device until you tap the moon/sun button, then remembers your choice
- **Works on laptop and phone:** two columns on a laptop, one on a phone, with no separate phone code

**Prices**
- **Refresh on demand:** re-check prices when asked. Bought items are skipped. Amazon prices are refreshed **through the iPhone** (a "Refresh OnTrack" Shortcut), every other store by the server
- **Price history** per item: every check, oldest first, ready for a chart ("↓ ₹40 since you saved it", lowest price seen)
- **Graceful failures:** if a store blocks a check, the last known price is kept and the reason is shown

## Architecture

```
iPhone Share Sheet ──► "Add to OnTrack" Shortcut
                         1. downloads the product page on the phone's own connection
                         2. uploads link + page (multipart form) ──┐
                                                                    │
React web app (laptop / phone browser) ── JSON ──────────────────┤  HTTP + JSON
                                                                    ▼
                                                 FastAPI backend (Python)
                                                  ├── main.py       HTTP layer: routes, validation, auth, error → status code
                                                  ├── services.py   Business rules: lists, budget, cheapest link, refresh
                                                  ├── db.py         Database tables and connections
                                                  └── extractor.py  Page → name, price, MRP, image
                                                                    │
                                                                    ▼
                                                   SQLite (local) → Postgres (when hosted)
```

The layers are kept separate on purpose. `services.py` doesn't know about HTTP, so its rules can be tested directly and reused (for example by a future bot). All SQL lives in `db.py` and `services.py`, so moving from SQLite to Postgres is a contained change.

**Fetching is separate from parsing.** The extractor never downloads anything itself; it calls whatever *fetcher* it is given. On the laptop that's a Chrome-like downloader. For pages the phone already downloaded, it's a fetcher that simply hands back the uploaded page and refuses to go online for anything else. The same parsers run either way, which is what made phone-side fetching a small change.

### Frontend

The web app is a React + TypeScript single page, built with Vite. Each part of the screen is a **component** in its own file (`BudgetCard`, `Tabs`, `ItemRow`, `AddLink`, `SettingsSheet`, …). Two decisions shape it:

- **The server is the single source of truth.** After any button press the app calls the API and then reloads `/summary`, instead of recalculating budgets in the browser. The backend already computes spent-this-month, what fits and purchase prices (and is tested), so the screen can never drift from the database.
- **One place talks to the server.** `api.ts` adds the API key, reads the JSON and turns failures into plain sentences ("Can't reach the server…", "The API key was rejected…"). Components only call functions like `getSummary()` or `patchItem()`.

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
| Fetching | **curl_cffi** (laptop/server) · **the iPhone itself** (Amazon) | See "Challenges" below |
| Parsing | **BeautifulSoup + lxml**, regex for embedded JSON | Standard, robust HTML parsing |
| Uploads | **python-multipart** | Lets FastAPI read the page the phone uploads as a file |
| Database | **SQLite** now → **Postgres** when hosted | SQLite needs no setup locally; hosted servers don't keep local files, so production needs a separate database |
| Frontend | **React + TypeScript**, built with **Vite** | Browsers only run JavaScript; React is the most widely used UI library, and TypeScript catches mistakes (a misspelled field, a missing prop) while typing. Vite creates the project in one command and reloads the page instantly on save |
| Styling | **Plain CSS with variables** (design tokens) | Every colour is a variable defined once for light and once for dark, so dark mode needs no component changes. No CSS framework, so the look stays deliberate and the code stays readable |
| Linting | **Oxlint** | Vite's default; fast, no setup |
| App type | **PWA** (Progressive Web App), planned | One codebase that runs in any browser and installs on the iPhone home screen. No App Store needed |
| Saving from other apps | **iOS Shortcut** | iOS doesn't let PWAs appear in the share sheet, but a Shortcut can, and it can call the API |

## Design

The look was agreed in a clickable mockup before any React was written, so colours, spacing and wording could change cheaply.

- **Inspiration:** calm, editorial websites: warm neutrals, a serif for headings, tiny spaced-out uppercase labels, thin dividers with **+** to expand, rounded pill buttons, lots of empty space.
- **Palette "Linen & Espresso":** linen background, warm-white cards, espresso text, cocoa accent, sand lines. Colour only carries meaning: **sage** means good news (fits budget, price dropped), **clay** means attention (over budget, errors). The dark version ("Espresso at night") is a warm brown-black, with each colour lightened just enough to stay readable.
- **Type:** Cormorant Garamond (serif) for the title, headings and empty states; DM Sans for everything else. Numbers use DM Sans with **tabular figures**, so prices line up in a column. The **₹** is drawn smaller and softer than the digits, so "₹557" reads as an amount rather than one long shape.
- **Motion:** the tab underline glides, lists fade in, rows open smoothly, buttons press slightly. Everything turns off for people who ask their device for reduced motion.
- **Decisions from using it:**
  - No duplicate controls: the theme lives only in the header and the budget only on its card. Settings keeps just the API key and server address.
  - Delete needs two taps.
  - The budget label reads "Left after wish list", not "Left this month", because it subtracts what you *plan* to buy.
  - A "below MRP" savings line was tried and removed for being confusing.

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

**The same problem on Savana:** a link saved through Google came back as `/details/1789982?vid=7&shem=aimgspe%2C`. `shem` is Google tracking, but what was `vid`? Before writing any code, I copied the link for the same T-shirt in two colours: `vid=6` (blue) and `vid=2` (pink). So `vid` is the **colour**, and dropping it would make two different colours look like one item, the opposite bug. **Fix:** another allow-list. Savana links are reduced to `https://www.savana.com/details/<id>?vid=<colour>`, and a test checks that two colours stay two different links. Share links (`sharein.savana.com`) are left alone so the tested redirect-following still runs; they get cleaned once the redirect lands on the real page.

### 8. Refreshing prices without getting blocked

Re-checking every price each time the app opens would look like a bot and risks CAPTCHAs. **Decision:** refresh only when the user taps a button. Even then, links checked in the last hour are skipped (unless forced), at most 3 are fetched at once, requests are spaced out with random pauses, and **bought items are never re-checked**. "Later" items still are, because a price drop is exactly what might move one back to the wish list.

### 9. Moving between lists without losing history

A single `status` column only knows where an item is *now*. Once something moved from planned to later, the fact that it was ever planned was gone. **Fix:** a `status_changes` table that records every move. Decisions made along the way:
- The history row is written **in the same transaction** as the change it describes, so a rolled-back change never leaves a history row behind.
- The **old status is read before updating**, since the update overwrites it.
- Only **real moves** are recorded: re-sending the same status (a double tap) writes nothing, which a test checks.

### 10. Datacenter IPs: fetching on the phone instead

**Problem:** extraction works from a home connection, but hosted servers use **datacenter IP addresses**, which Amazon treats with much more suspicion than home or mobile ones.

**Solution: split fetching from parsing.** The iPhone downloads the page over its own connection (which looks like a normal shopper), and the server only reads it with the same parsers.

**Validation first:** a three-step test Shortcut downloaded an Amazon page on both Wi-Fi and mobile data. Both came back as the full desktop product page with no bot-check, and the existing extractor read the title, price (₹289), MRP (₹699) and image from it without any changes.

**Problems found while building it:**
- **Shortcuts turned the page into plain text.** Sending the page inside a JSON text field made iOS convert the HTML into readable text and drop every tag: the server received 16,116 characters starting with "Skip to • Main content" instead of ~1.7 million characters of HTML. A temporary debug line on the server confirmed this. **Fix:** upload the page as a **file** (multipart form), which iOS passes through byte for byte.
- **The Amazon app shares the link twice**, so the Shortcut received a list of two URLs and glued them together (`https://amzn.in/d/…https://amzn.in/d/…`). **Fix:** take only the first item from the list.
- **Short links.** The phone follows `amzn.in/d/…` to the real page, but the server only sees the short link. **Fix:** read the page's own `<link rel="canonical">` tag for its real address, which the ASIN rule then cleans.
- **No second downloads.** Some strategies normally fetch a second URL (Shopify's `.js` data). The phone-page fetcher answers any second request with a 404 instead of going online, so those strategies give up cleanly rather than crashing on HTML they expected to be JSON.
- **The phone couldn't reach the laptop.** The server listens only on `127.0.0.1` (this machine) by default. **Fix:** run with `--host 0.0.0.0` on home Wi-Fi, and set the Windows network profile to *Private* so the firewall allows it.

- **Google shares a message, not a link** (`Source: www.savana.com https://share.google/…`), so taking the first "link" saved Savana's homepage, and for Littlebox the text itself. **Fix:** extract every URL from what was shared and take the **last** one.
- **Some stores have their own share menu** (Savana's website), which doesn't list the Shortcut. **Fix:** Copy Link, then run the Shortcut; with nothing shared, it reads the clipboard.
- **Other stores' extra steps.** Savana share links redirect with JavaScript, which the phone can't run, and the phone-page fetcher refuses second downloads. **Fix:** if the phone's page gives no price **and the store isn't Amazon**, the server fetches the link itself. Only Amazon blocks servers, so this is safe, and Amazon never falls back.

- **Refreshing Amazon prices through the phone too.** Adding items was only half the problem: re-checking prices would still send the server to Amazon. **Fix:** a second Shortcut, *Refresh OnTrack*. It asks the server which Amazon links are due (`GET /refresh/phone-list`: Amazon only, not bought, not checked in the last hour), downloads each page on the phone in a loop, and uploads it to `POST /links/{id}/from-html`. The server reuses the same parsing and price-recording code as every other check, so price history and "lowest seen" just work. The one-hour cooldown rule was moved into a shared `_is_due()` helper, so the server's refresh and the phone's list can never disagree.
- **400 Bad Request on upload.** The first refresh run failed on every link. Reproducing it locally showed why: FastAPI accepts uploaded **files** of any size but caps plain form **fields** at 1 MB, and the Shortcut had sent the 1.7 MB page as a text field (`"Field exceeded maximum size of 1024KB"`). **Fix:** set the Shortcut's form field type to **File**.

**Result:** sharing a product from the Amazon app saved it with the exact variant's title, price (₹237), MRP (₹279), image and cleaned link, without the server ever contacting Amazon. Littlebox (₹699, read from the phone's page alone) and Savana (₹318, via Copy Link) work through the same Shortcut.

### 11. Amazon blocked the laptop too

**Symptom:** pasting an Amazon link into the web app saved an item named after its own URL, with no price.

**Cause:** the paste box uses `/items/from-link`, where the **server** fetches the page. After two days of testing and refreshing from the same network, Amazon started answering with a bot-check page.

**What I did:**
- **Researched how price-comparison sites cope.** Most use official affiliate data feeds (Amazon's Product Advertising API needs an approved Associates account), feeds that stores send them, or **browser extensions that read the page the shopper is already viewing**. The last is the same pattern as the phone path.
- **Ruled out** rotating proxies and CAPTCHA-solving services: they go against store terms and break whenever detection changes.
- **Made failure graceful:** the row shows the backend's actual error and offers a box to type the price (stored as `manual_price`, which the budget already used). The paste box warns that Amazon works best through the phone.
- **Planned:** a browser extension, so the laptop gets the same "fetch as the user" path as the phone.

### 12. Files that worked on Windows but would break when deployed

Windows treats `Api.ts` and `api.ts` as the same file, while Linux (where deployment builds run) does not. Twice a file was saved with the wrong capitals (`Api.ts`, `Usetheme.ts`), and everything still worked locally. **Fix:** rename with `git mv` in two steps (`Usetheme.ts → useTheme_tmp.ts → useTheme.ts`), because both Windows and git can miss a change that is only in capitals. **Convention adopted:** component files are PascalCase (`ItemRow.tsx`), everything else lowercase (`api.ts`).

### 13. Saved changes that never reached the browser

Vite watches every file and updates the page on save. Once, Windows had a file locked at the moment Vite started watching it (`EBUSY: resource busy or locked`), so Vite silently stopped watching that file and the browser kept showing the old version. **Fix:** restart `npm run dev`. Lesson: if a saved change doesn't appear and the terminal shows no `hmr update` line for that file, restart the dev server.

### 14. `localhost` is not `127.0.0.1` to a browser

The backend's CORS setting allows `http://localhost:5173`. Opening the app as `http://127.0.0.1:5173` makes the browser treat it as a different website and block every request, which the app can only report as "Can't reach the server". **Rule:** open the app at `localhost`, and add any other address (such as the laptop's Wi-Fi IP, for testing on the phone) to `ONTRACK_CORS_ORIGINS`.

### Known limits

- **Month boundary:** times are stored in UTC, which is 5½ hours behind India. A purchase between midnight and 5:30 am on the 1st counts toward the previous month. To be fixed at deployment.
- **The server's `/refresh` still includes Amazon links.** That's fine from a home connection, but once deployed it would send Amazon requests from a datacenter. Planned fix at deployment: `/refresh` skips Amazon, which the phone handles.
- **Two taps to refresh everything:** the Shortcut for Amazon, `/refresh` for other stores. Planned: the Shortcut calls `/refresh` at the end, so one tap covers both.
- **Amazon links pasted into the web app** are fetched by the server and may be blocked. Use the phone Shortcut, or type the price into the row. The browser extension will fix this on the laptop.
- **Local IP address:** while running on the laptop, the Shortcut points at the laptop's Wi-Fi address, which can change after a router restart. Deployment gives the server a fixed address.

## Store support

| Store | Method | Status |
|---|---|---|
| Amazon.in (incl. `amzn.in` short links) | Chrome-like fetch, or page fetched by the iPhone · selectors / embedded price data | ✅ (laptop and iPhone) |
| Fastrack | JSON-LD (`schema.org/Product`) | ✅ laptop · ⏳ iPhone not tested |
| Savana (incl. share links) | JS redirect follow + embedded app data | ✅ laptop · ✅ iPhone (Copy Link, server fallback) |
| Shopify stores (Come Again, Littlebox, …) | `/products/<handle>.js`, JSON-LD fallback | ✅ single products (laptop and iPhone) · ⏳ carts |
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

### The web app

Requires Node.js 18+ (LTS). In a second terminal, from the top `OnTrack` folder:

```powershell
cd frontend
npm install
```

Create `frontend/.env.local` (git-ignored) so the app knows where the server is during development:

```
VITE_API_URL=http://127.0.0.1:8000
VITE_API_KEY=<the same key as backend/.env>
```

Then, with the backend running:

```powershell
npm run dev
```

Open **http://localhost:5173** (`localhost`, not `127.0.0.1`, because CORS only allows `localhost`). `.env.local` is for development only: Vite copies its values into the built app, so a real deployment must not contain the key there. The app's Settings panel stores the key and server address in the browser instead.

Try the extractor on its own:
```powershell
python extractor.py https://amzn.in/d/xxxxxx
python extractor.py -f links.txt --debug     # --debug saves each fetched page to debug/
```

### Using the iPhone Shortcut with the local server

1. Start the server so other devices on the Wi-Fi can reach it: `uvicorn main:app --reload --host 0.0.0.0`
2. Find the laptop's address with `ipconfig` (**Wireless LAN adapter Wi-Fi → IPv4 Address**). Check it from the phone's Safari: `http://<IP>:8000/health` should show `{"ok":true}`.
3. Only do this on a trusted home network. The API key still protects every endpoint.

The **Add to OnTrack** Shortcut (shown in the Share Sheet, URLs only):

| # | Action | Setting |
|---|---|---|
| 1 | Receive URLs and Text from Share Sheet | If there's no input: **Get Clipboard** (for stores with their own share menu: Copy Link, then run the Shortcut) |
| 2 | Get URLs from Input | Pulls every link out of a shared message |
| 3 | Get Item from List | **Last** item (Google puts the real link last; Amazon's two copies are identical) |
| 4 | Get Contents of URL | Item from List → downloads the page on the phone |
| 5 | Get Contents of URL | `http://<IP>:8000/items/from-html` · POST · header `X-API-Key` · Form body: `url` (Text) = Item from List, `html` (File) = page from step 4 |
| 6 | Show Content | The server's reply, kept as full JSON for now so null values or errors are easy to spot |

The **Refresh OnTrack** Shortcut (run directly, or daily with an iOS Automation):

| # | Action | Setting |
|---|---|---|
| 1 | Get Contents of URL | `GET http://<IP>:8000/refresh/phone-list` · header `X-API-Key` (add `?force=true` to ignore the one-hour cooldown while testing) |
| 2 | Repeat with Each | item in the list from step 1 |
| 3 | ↳ Get Dictionary Value | `url` in Repeat Item |
| 4 | ↳ Get Dictionary Value | `link_id` in Repeat Item |
| 5 | ↳ Get Contents of URL | the `url` value → downloads the Amazon page on the phone |
| 6 | ↳ Get Contents of URL | `http://<IP>:8000/links/<link_id>/from-html` · POST · header `X-API-Key` · Form body: `html` (**File**, not Text) = page from step 5 |
| 7 | End Repeat | |
| 8 | Show Content | Repeat Results: one `{"link_id", "ok", "old_price", "new_price", "error"}` per link |

**Who refreshes what:**

| Store | Downloads the page when refreshing | Triggered by |
|---|---|---|
| Amazon | the iPhone | Refresh OnTrack Shortcut |
| Every other store | the server | `POST /refresh` (later: the app's Refresh button) |

## API overview

All endpoints except `/health` require the `X-API-Key` header.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/summary` | Budget, discounted total, spent this month, remaining, savings vs MRP, what fits, all items |
| `PUT` | `/budget` | Set the monthly budget |
| `GET` | `/items?status=` | List items: `planned`, `later`, `purchased` or `all` (default) |
| `GET` | `/items/{id}` | One item with its links |
| `GET` | `/items/{id}/history` | Every price check for the item's links, oldest first |
| `POST` | `/items/from-link` | Save an item from a link (the server fetches the page) |
| `POST` | `/items/from-html` | Save an item from a page the phone already fetched (form: `url` + `html` file); non-Amazon pages without a price fall back to a server fetch |
| `POST` | `/items` | Save a manual item (name + price) |
| `POST` | `/items/{id}/links` | Add another store's link to an item |
| `PATCH` | `/items/{id}` | Edit name, status, priority, manual price, note, purchased price |
| `DELETE` | `/items/{id}` · `/links/{id}` | Remove an item or a link |
| `POST` | `/refresh?force=` | Re-check prices (skips recently checked links and bought items) |
| `POST` | `/items/{id}/refresh` | Re-check one item |
| `GET` | `/refresh/phone-list?force=` | Amazon links the phone should re-download: not bought, not checked in the last hour |
| `POST` | `/links/{id}/from-html` | Upload a page the phone downloaded for one link; records the new price |

## Project structure

```
OnTrack/
├── backend/
│   ├── main.py            FastAPI routes
│   ├── services.py        business logic
│   ├── db.py              SQLite schema
│   ├── extractor.py       page → product details
│   ├── tests/             offline tests (fake pages, fake extractor), 37 passing
│   ├── requirements.txt
│   └── .env.example       settings template (real .env is git-ignored)
└── frontend/
    ├── index.html             the single HTML page (fonts, theme colour)
    ├── .env.local             dev server address + key (git-ignored)
    └── src/
        ├── main.tsx           entry point: draws <App /> into the page
        ├── App.tsx            loads /summary, owns the tab, handles button presses
        ├── api.ts             every request to the backend
        ├── types.ts           shapes of the data the backend sends
        ├── format.ts          store names and short dates
        ├── index.css          design tokens (light + dark), layout, components
        ├── hooks/
        │   └── useTheme.ts    light / dark / follow the device
        └── components/
            ├── BudgetCard.tsx     budget, bar, totals, in-card budget editing
            ├── Price.tsx          every ₹ amount, drawn the same way
            ├── AddLink.tsx        paste-a-link box
            ├── Tabs.tsx           Wish list · Later · Bought · All
            ├── ItemList.tsx       the rows for the current tab
            ├── ItemRow.tsx        one expandable row, its actions, the price box
            ├── Thumb.tsx          product photo or a letter
            ├── SettingsSheet.tsx  API key and server address
            └── Icons.tsx          moon, sun, sliders, close
```

## Roadmap

- [x] Price extractor for Amazon, Fastrack, Savana, Shopify
- [x] Backend API with budget, multi-link items, price history, on-demand refresh
- [x] Lists (planned / later / purchased) with move history, purchases and spent-this-month budget
- [x] Validate phone-side fetching (datacenter IP problem)
- [x] `POST /items/from-html` so the phone can send pages it fetched itself
- [x] iOS Shortcut: "Add to OnTrack" from the share sheet (local network)
- [x] Server fallback for non-Amazon stores when the phone's page isn't enough
- [x] Clean Savana links to `/details/<id>?vid=<colour>` for reliable duplicate detection
- [x] iOS Shortcut: "Refresh OnTrack" refreshes Amazon prices through the phone
- [ ] One-tap refresh: the Shortcut also triggers the server's `/refresh` for other stores
- [ ] Daily automatic refresh with an iOS Automation (after deployment, so it works on any network)
- [ ] Shortcut: replace the raw JSON reply with a short notification (later; raw JSON is useful while testing)
- [x] React + TypeScript web app: budget card, tabs, expandable rows with photos, row actions, paste-a-link, manual price fallback, settings, light/dark, laptop and phone layouts
- [ ] Undo message after Delete and moves (two-tap Delete and "Undo purchase" cover the main cases for now)
- [ ] Browser extension: "Add to OnTrack" on the laptop, sending the page you're viewing to `/items/from-html`
- [ ] Installable PWA (home-screen icon, app name, offline shell)
- [ ] Deploy: frontend (Vercel), backend (always-on host), Postgres; fix the UTC month boundary; `/refresh` skips Amazon
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
- Validated phone-side fetching on Wi-Fi and mobile data; the existing extractor read the phone's page unchanged
- Built `POST /items/from-html` on the `feature/phone-fetch` branch and the "Add to OnTrack" Shortcut; fixed the doubled share link, the HTML-to-text conversion (switched to a file upload) and short links (canonical tag). First product saved end to end from the Amazon app
- Added the server fallback for non-Amazon stores; fixed Google's share format in the Shortcut (all URLs → last one) and added a clipboard fallback. Amazon, Littlebox and Savana all saved from the iPhone. 35 tests passing

**2026-10-06**
- Found that Savana's `vid` is the colour by comparing two colours' links; reduced Savana links to product id + colour
- Built phone-side price refresh: `GET /refresh/phone-list`, `POST /links/{id}/from-html`, a shared cooldown helper, and the "Refresh OnTrack" Shortcut with a loop over due Amazon links
- Debugged a 400 on upload by reproducing it locally (1 MB form-field limit) and fixed the Shortcut to send a File
- Tested the Shortcuts from office Wi-Fi as well as home. 37 tests passing
- Started the frontend on `feature/frontend`: installed Node.js, chose the design (palette, type, motion, light/dark) and agreed it in a clickable mockup before writing React
- Built the app in small commits: Vite scaffold → design tokens and layout → API client and types → budget card → tabs and rows with product photos → row actions → settings and theme toggle
- Refined from use: in-card budget editing, removed duplicate controls, clearer labels, removed a confusing savings line
- Fixed file-name casing that only worked on Windows (`git mv` in two steps), and a Vite watcher that silently stopped watching a locked file

**2026-10-07**
- Added the paste-a-link box
- Hit Amazon's bot-check from the laptop; researched how price-comparison sites get data; made failures graceful (real error in the row, type the price by hand, Amazon hint); planned a browser extension as the laptop version of the phone path