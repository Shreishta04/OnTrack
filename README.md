# OnTrack

> A budget-aware wishlist for Indian online shopping. Share or paste a product link from any store, and OnTrack pulls the product name and price automatically, totals everything you plan to buy, and shows what's left of your monthly budget.

**Status:** 🚧 In development. Price extractor ✅ · Backend API ✅ · iPhone Shortcuts ✅ (local network) · Web app ✅ (local, laptop + phone) · Browser extension ⏳ · Deployment ⏳

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
- **Duplicate detection:** the same product shared twice, even via a short link or with different tracking junk, is rejected. Amazon, Savana and Flipkart links are reduced to just the part that identifies the product
- **Stuck links get rescued:** if a store blocked the first try, adding the same link again (for example from the phone) fills in the existing item's name, price and photo instead of saying "already saved"
- **Add by hand:** a name, a price and an optional link, for anything a store won't let us read or that isn't sold online. The link is saved **without contacting the store**; with one, Refresh later brings in the store's price and photo (the store's price replaces mine, which is kept as a backup, and my name stays). Without one, my price stays as typed. Rows show *typed by you* so typed prices are never mistaken for store prices

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
- **Paste a link** to add an item from the laptop, with a note that Amazon works best shared from the iPhone
- **When a store won't give a price,** the row says **why** in plain words (*"Amazon showed a bot-check page…"*, *"The store took too long to answer."* instead of raw `curl` errors) and **what to do**: for Amazon, tap *Refresh OnTrack* on the iPhone or share it from there, and the name, photo and price fill in by themselves
- **Placeholder letters:** items without a photo show their first letter; an item still named after its link shows the **store's** letter (A for Amazon) instead of "H" from *https*
- **Refresh button (↻)** in the header: the server re-checks every store except Amazon (the iPhone does Amazon), the icon spins while it works, and a short note says what happened (*"Checked 4 · 1 price dropped · Amazon refreshes from your iPhone"*, or *"All prices were checked in the last hour"*)
- **Stays current by itself:** coming back to the app (from Shortcuts, another app or another tab) reloads the list, so prices the iPhone refreshed show up without a manual reload
- **Light and dark mode:** follows the device until you tap the moon/sun button, then remembers your choice
- **Works on laptop and phone:** two columns on a laptop, one on a phone, with no separate phone code

**Prices**
- **Refresh on demand:** re-check prices when asked. Bought items are skipped. Amazon prices are refreshed **through the iPhone** (a "Refresh OnTrack" Shortcut), every other store by the server (the app's ↻ button). The server **never** fetches Amazon: the stores it must leave to the phone are kept in one list (`PHONE_ONLY_STORES`), so adding another store that blocks servers is a one-word change. Amazon links that still have **no price** are always included, so a blocked item is fixed on the next tap, and an item still named after its URL gets its real name
- **Never hangs:** adding a link gives up after **25 seconds in total**, and the database is never locked while a store page downloads, so the rest of the app keeps working
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
| Database | **SQLite** now → **Postgres** when hosted | SQLite needs no setup locally; hosted servers don't keep local files, so production needs a separate database. Switching early was considered during the "server freezes" bug and rejected: the real cause was in my code (Challenge 16) |
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
- **Designed a graceful failure:** the row would show the backend's actual error and a box to type the price (stored as `manual_price`, which the budget already uses), and the paste box would warn that Amazon works best through the phone. While testing on the phone on 7 Oct, the price box was missing. `git log` showed why: that work had **never been committed**, and it wasn't in my working folder either. It will be rebuilt. **Lesson:** check `git status` and `git log` before calling a step done.
- **Planned:** a browser extension, so the laptop gets the same "fetch as the user" path as the phone.

### 12. Files that worked on Windows but would break when deployed

Windows treats `Api.ts` and `api.ts` as the same file, while Linux (where deployment builds run) does not. Twice a file was saved with the wrong capitals (`Api.ts`, `Usetheme.ts`), and everything still worked locally. **Fix:** rename with `git mv` in two steps (`Usetheme.ts → useTheme_tmp.ts → useTheme.ts`), because both Windows and git can miss a change that is only in capitals. **Convention adopted:** component files are PascalCase (`ItemRow.tsx`), everything else lowercase (`api.ts`).

### 13. Saved changes that never reached the browser

Vite watches every file and updates the page on save. Once, Windows had a file locked at the moment Vite started watching it (`EBUSY: resource busy or locked`), so Vite silently stopped watching that file and the browser kept showing the old version. **Fix:** restart `npm run dev`. Lesson: if a saved change doesn't appear and the terminal shows no `hmr update` line for that file, restart the dev server.

### 14. `localhost` is not `127.0.0.1` to a browser

The backend's CORS setting allows `http://localhost:5173`. Opening the app as `http://127.0.0.1:5173` makes the browser treat it as a different website and block every request, which the app can only report as "Can't reach the server". **Rule:** open the app at `localhost`, and add any other address (such as the laptop's Wi-Fi IP, for testing on the phone) to `ONTRACK_CORS_ORIGINS`.

### 15. Testing on the phone: "Safari can't open the page"

**Symptom:** the web app opened on the laptop at `http://192.168.1.59:5173`, but the iPhone on the same Wi-Fi said the server stopped responding.

**Cause:** two things in a row. Vite was started with plain `npm run dev`, which only accepts connections from the laptop itself (its output even says `Network: use --host to expose`). After fixing that, **Windows Firewall** silently dropped the phone's requests, because the Wi-Fi was not marked as a private network. "Stopped responding" (no answer at all, rather than a refusal) is the typical sign of a firewall.

**Fix:** `npm run dev -- --host` (the lone `--` passes `--host` through npm to Vite), set the Wi-Fi's network profile to **Private**, and add one firewall rule for ports 5173 and 8000 on private networks only. The phone's address also had to be added to `ONTRACK_CORS_ORIGINS`.

### 16. The server kept "freezing"

**Symptom:** sometimes everything stopped: "Adding…" spun forever, the Shortcuts timed out, and the uvicorn terminal showed nothing at all. Restarting fixed it until the next time. My first idea was to switch from SQLite to Postgres.

**What I did first:** reproduced it. I ran the backend against a fake store that accepts the connection and never answers, and used the app at the same time:

| During a slow add | Result |
|---|---|
| Reading (`/summary`) | instant |
| Editing the budget | waited 5 s, then `500` ("database is locked") |
| A second add | waited 5 s, then `500` |

**Causes (three, stacked):**
1. **The database was locked during downloads.** Adding a link saved an empty item first and *then* downloaded the store page. SQLite allows many readers but only one writer, and the write lock was held for the whole download (20 s, up to ~80 s with redirects). Every other change queued behind it and failed.
2. **No overall time limit.** Each download had a 20 s limit, but one add can need several downloads (the page, up to 3 redirect hops, Shopify's `.js` lookup).
3. **Uvicorn only logs a request when it finishes**, so a stuck request was invisible and the terminal looked dead. On Windows, `Ctrl+C` with `--reload` can also leave an old server holding port 8000, so new requests go to the stuck one. `netstat -ano | findstr :8000` shows that (more than one `LISTENING` line).

**Fixes:**
1. **Download first, then write.** Fetching only *reads* the database; the item and link are written afterwards in milliseconds. A test makes a second connection try to write *while* the fake store is still "downloading", with `timeout=0`, and fails if the database is locked.
2. **A 25-second budget for each add,** shared by all its downloads: each download only gets the time that's left. Tested with a fake clock, so the test runs instantly.
3. **A log line when each request starts**, plus a `slow … took X s` line for anything over 2 s.

**Why not Postgres?** Postgres locks rows instead of the whole database, so this particular clash would have disappeared, but the requests would still hang for a minute, and holding a transaction open during a network call is a bad habit with any database. Postgres stays planned for deployment.

### 17. A blocked item could never be rescued

**Symptom:** Amazon blocked the laptop's paste, so the item had no name or price. Sharing the same product from the phone, which would have worked, said "already saved". Running *Refresh OnTrack* skipped it too, and when a later refresh finally found the price, the item was still named `https://www.amazon.in/dp/…`.

**Cause:** three rules that are each sensible, but together locked the item out:
- the duplicate check refused *any* known link, even one without a price;
- the refresh list skipped links checked in the last hour, and a **failed** check counted as a check;
- the item's name was only set when it was first created.

**Fix:** a known link **without** a price is filled in instead of refused; the phone's refresh list always includes Amazon links with no price; and every successful check renames an item that is still named after its URL (names I typed myself never start with `http`, so they're left alone). Each rule has a test that replays what happened.

### 18. Flipkart duplicates

**Symptom:** the same sneakers, shared three different ways, became separate items.

**Cause:** Flipkart had no cleaning rule, so the extras after `?` (`pid`, `lid`, `marketplace`, tracking) differed by route, and the duplicate check saw different links.

**Fix:** another allow-list. Flipkart links are reduced to `https://www.flipkart.com/<name>/p/itm…`, including app links from `dl.flipkart.com`. **Decision:** `pid` changes per size or colour, and I chose to treat sizes and colours of one product as one item. (Existing duplicates aren't merged automatically, so I deleted the extra row by hand.)

### 19. A fresh install couldn't run the tests

Setting up the backend from scratch (`pip install -r requirements.txt`) crashed before any test ran: *Form data requires "python-multipart"*. My own venv had it installed by hand, so I never noticed. **Fix:** added it to `requirements.txt`. A deployment server would have hit the same crash.

### 20. Typing a price wasn't enough

**Symptom:** the plan was a "type the price" box inside each stuck row. Looking at the mockup, I realised that when Amazon blocks us we get **only the link**: no name, no photo, no price. A typed price on a row called `https://www.amazon.in/dp/…` is half a fix.

**What I chose instead:**
- Stuck rows **explain themselves**: the real reason, and the fix that actually works. After the backend fixes, a blocked Amazon row is a placeholder the phone completes with one tap.
- A separate **Add by hand** card (name, price, optional link) for whatever the phone can't fix, or things that aren't sold online at all.

**Decisions:** the link is optional (the budget is about everything I plan to buy, not only online shopping); when a store price arrives it replaces my typed one (on a wish list the store's current price is the truth); the price is required.

### 21. A short link added by hand would have become a duplicate

**Symptom:** testing Add by hand with an Alexa link copied from the Amazon app, the saved link was `https://amzn.in/d/0ahlEBRm`, Amazon's **short** link.

**Cause:** adding by hand never contacts the store (on purpose), so nothing ever followed the short link to the real `amazon.in/dp/…` page. Sharing the same Echo Dot later would arrive as `/dp/…`, not match, and be saved twice.

**Fix:** whenever a check successfully reads a page, the link's address is updated to the page's real, cleaned address (from its canonical tag), unless another link already has it. Refresh fixed the Alexa link by itself. A test replays it: short link → phone refresh → `/dp/` address → sharing again says "already saved".

**A slip worth remembering:** while pasting this change I replaced three lines instead of adding after them, and deleted the line that saves price history. Three existing tests about history failed straight away, which is exactly what they're for. Habit since: `git diff` before every commit, and look at every `-` line.

### 22. Should the refresh button include Amazon?

**The question:** `POST /refresh` checked every store, Amazon included. From the laptop, Amazon sometimes answers with a bot-check. The last price is kept, but that failed check counted as "checked" for an hour, so the phone's *Refresh OnTrack* would skip the item.

**Decision:** the server skips Amazon; the phone does Amazon. That is exactly how it has to work once deployed (a cloud server's datacenter address gets bot-checked much more), so I did it now. Instead of writing "Amazon" into the refresh code, the server keeps a list of **phone-only stores** in one place; the server refresh, the phone's refresh list and the "never fall back to the server" rule all read it. If Flipkart or Myntra start blocking the deployed server, they go on the list and everything follows.

**Thinking ahead:** for other people, Amazon is the gap. Android has no Shortcuts, and even iPhone users would need to install two. The realistic answer for a multi-user OnTrack is Amazon's official Product Advertising API (needs an approved Associates account); a native Android app or the browser extension would be extras.

### 23. The phone at the office: `127.0.0.1` means "this device"

**Symptom:** at the office the page opened on the phone, but the app said *"Can't reach the server at http://127.0.0.1:8000"*, even though `http://<laptop IP>:8000/health` worked in Safari.

**Cause:** two things. The app saves its server setting in the browser **per address**: at home I'd opened `192.168.1.59:5173`, at the office it was `192.168.29.37:5173`, which Safari treats as a different site with empty settings. So the app fell back to its development default, `127.0.0.1:8000`, and `127.0.0.1` always means *this device*: on the phone, the phone itself. Separately, the office address had to be added to the CORS list (`/health` worked because typing an address isn't a cross-site request; the app calling port 8000 from port 5173 is).

**Fix:** set Settings → server to `http://<laptop IP>:8000` on the phone, and list both the home and office addresses in `ONTRACK_CORS_ORIGINS`. **Lesson:** port 5173 is the app (Vite), port 8000 is the data (uvicorn); the server setting always points at 8000.

### Known limits

- **Month boundary:** times are stored in UTC, which is 5½ hours behind India. A purchase between midnight and 5:30 am on the 1st counts toward the previous month. To be fixed at deployment.
- **Two taps to refresh everything:** *Refresh OnTrack* for Amazon, ↻ for other stores. Planned: the Shortcut calls `/refresh` at the end, so one tap covers both.
- **Amazon links pasted into the web app** are fetched by the server and may be blocked (it's hit-and-miss). Share the same link from the phone and the item is filled in. The browser extension will fix this on the laptop.
- **"Over budget" follows list order:** items are added up in list order, so after one expensive item, even a cheap one shows *Over budget*. To be redesigned.
- **Flipkart sizes and colours count as one item** (they share one product code). Lipstick shades on Flipkart may merge too.
- **A link that never gets a price** (for example a removed product) is downloaded on every Refresh. Cheap, but worth knowing; delete the item.
- **Phone, development mode:** the first load on the phone can take a while, because Vite's dev server sends the app as many small files. A production build doesn't have this.
- **Local IP address:** while running on the laptop, the Shortcuts and the phone's server setting point at the laptop's Wi-Fi address, which is different at home and at the office (and the app's saved settings don't carry over between addresses). Tailscale would give one fixed address now; deployment fixes it for good.

### Found while using it, to fix later

Small things I noticed while testing that don't block anything yet:

- **Long amounts overflow the budget card.** A budget in crores (₹1,23,88,844 while testing) pushes the big number and the totals past the card's edge. Planned fix: smaller font for long amounts (tried and working in a test build; parked to keep this branch small).
- **"WISH LIST" wraps onto two lines** on the phone, while the other tabs fit on one.
- **Filling in a stuck link answers `201 Created`** although nothing new is created. Nothing reads the code today.
- **Test client warning** (`StarletteDeprecationWarning`, wants `httpx2`): harmless for now.

## Store support

| Store | Method | Status |
|---|---|---|
| Amazon.in (incl. `amzn.in` short links) | Chrome-like fetch, or page fetched by the iPhone · selectors / embedded price data | ✅ (laptop and iPhone) |
| Fastrack | JSON-LD (`schema.org/Product`) | ✅ laptop · ⏳ iPhone not tested |
| Savana (incl. share links) | JS redirect follow + embedded app data | ✅ laptop · ✅ iPhone (Copy Link, server fallback) |
| Shopify stores (Come Again, Littlebox, …) | `/products/<handle>.js`, JSON-LD fallback | ✅ single products (laptop and iPhone) · ⏳ carts |
| Flipkart (incl. app links) | Generic page data, links cleaned to `/p/itm…` | ✅ laptop paste · ✅ iPhone (Share Sheet, clipboard) · ⏳ MRP not read yet |
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

Run the tests, then the server. Always from the `backend` folder, where `main.py` lives (from the top folder, uvicorn says *Could not import module "main"*):
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
4. **First time on a network:** in Windows, set the Wi-Fi's network profile to **Private**, and allow the two ports once (PowerShell as Administrator):
   ```powershell
   New-NetFirewallRule -DisplayName "OnTrack dev" -Direction Inbound -Protocol TCP -LocalPort 5173,8000 -Action Allow -Profile Private
   ```
5. **To use the web app on the phone too:** start it with `npm run dev -- --host`, add `http://<IP>:5173` to `ONTRACK_CORS_ORIGINS` in `backend/.env` (restart uvicorn), open `http://<IP>:5173` on the phone, and set Settings → server to `http://<IP>:8000`.
6. **If the server goes silent:** run `netstat -ano | findstr :8000` *before* restarting. More than one `LISTENING` line means an old server is still running: stop it with `taskkill /PID <number> /F`. Stop uvicorn with the terminal's trash icon rather than `Ctrl+C`.

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
| Every other store | the server | the app's ↻ button (`POST /refresh`) |

## API overview

All endpoints except `/health` require the `X-API-Key` header.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/summary` | Budget, discounted total, spent this month, remaining, savings vs MRP, what fits, all items |
| `PUT` | `/budget` | Set the monthly budget |
| `GET` | `/items?status=` | List items: `planned`, `later`, `purchased` or `all` (default) |
| `GET` | `/items/{id}` | One item with its links |
| `GET` | `/items/{id}/history` | Every price check for the item's links, oldest first |
| `POST` | `/items/from-link` | Save an item from a link (the server fetches the page). A link already saved **without** a price is filled in instead of rejected |
| `POST` | `/items/from-html` | Save an item from a page the phone already fetched (form: `url` + `html` file); non-Amazon pages without a price fall back to a server fetch |
| `POST` | `/items` | Add by hand: name + price, optional `url` (saved without contacting the store; Refresh can fill in the store's price later) |
| `POST` | `/items/{id}/links` | Add another store's link to an item |
| `PATCH` | `/items/{id}` | Edit name, status, priority, manual price, note, purchased price |
| `DELETE` | `/items/{id}` · `/links/{id}` | Remove an item or a link |
| `POST` | `/refresh?force=` | Re-check prices: skips bought items, links checked in the last hour, and phone-only stores (Amazon). Returns `checked`, `skipped_recent`, `phone_only`, `changed`, `failed` |
| `POST` | `/items/{id}/refresh` | Re-check one item |
| `GET` | `/refresh/phone-list?force=` | Amazon links the phone should re-download: not bought, and either not checked in the last hour or still without a price |
| `POST` | `/links/{id}/from-html` | Upload a page the phone downloaded for one link; records the new price |

## Project structure

```
OnTrack/
├── backend/
│   ├── main.py            FastAPI routes
│   ├── services.py        business logic
│   ├── db.py              SQLite schema
│   ├── extractor.py       page → product details
│   ├── tests/             offline tests (fake pages, fake extractor), 48 passing
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
        ├── format.ts          store names, short dates, plain-words errors and tips
        ├── index.css          design tokens (light + dark), layout, components
        ├── hooks/
        │   └── useTheme.ts    light / dark / follow the device
        └── components/
            ├── BudgetCard.tsx     budget, bar, totals, in-card budget editing
            ├── Price.tsx          every ₹ amount, drawn the same way
            ├── AddLink.tsx        paste-a-link box
            ├── AddByHand.tsx      name, optional link, price
            ├── Tabs.tsx           Wish list · Later · Bought · All
            ├── ItemList.tsx       the rows for the current tab
            ├── ItemRow.tsx        one expandable row: details, why it's stuck, actions
            ├── Thumb.tsx          product photo or a letter
            ├── SettingsSheet.tsx  API key and server address
            └── Icons.tsx          refresh, moon, sun, sliders, close
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
- [x] Backend fixes from phone testing: no database lock during downloads, 25 s limit per add, request-start logging, stuck links rescued (share again or Refresh), Flipkart duplicates
- [x] Stuck rows explain why and how to fix them; Add by hand (name, price, optional link); typed prices labelled; store letters; short links corrected after a check
- [x] Refresh button in the header (↻), and reload when the app's tab comes back into view; the server never fetches phone-only stores (Amazon)
- [ ] Undo message after Delete and moves (two-tap Delete and "Undo purchase" cover the main cases for now)
- [ ] Browser extension: "Add to OnTrack" on the laptop, sending the page you're viewing to `/items/from-html`
- [ ] Installable PWA (home-screen icon, app name, offline shell)
- [ ] Deploy: frontend (Vercel), backend (always-on host), Postgres; fix the UTC month boundary; `/refresh` skips Amazon; refresh non-Amazon prices when the app opens
- [ ] Myntra / Ajio / Meesho support
- [ ] Shopify cart import (Come Again charm bracelets)
- [ ] Rethink "Over budget" (each item on its own, or in priority order?)
- [ ] Flipkart MRP (the struck-through price)
- [ ] Accounts, so several people can use one deployed OnTrack (each with their own list and budget)

**Parked ideas**
- Native Android app with Flutter (installs as an APK on Android; an iPhone build would need a Mac, so the iPhone gets the PWA)
- Tailscale, so the phone reaches the laptop at one fixed address on any network

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
- Hit Amazon's bot-check from the laptop; researched how price-comparison sites get data; designed a graceful failure (real error, type the price by hand, Amazon hint) and planned a browser extension as the laptop version of the phone path
- Tested the web app on the iPhone: fixed Vite's `--host`, the Windows Firewall (Private profile + one rule) and CORS. Budget, tabs, rows, actions, theme and phone layout all work
- Found that the price-box work had never been committed; `feature/frontend` was merged as PR #3 without it
- Investigated "the server freezes": reproduced it with a fake store that never answers, found the database write lock held during downloads, and decided against switching to Postgres for this
- New branch `feature/backend-fixes`, one tested commit per step: fetch before writing, a 25 s limit per add, request-start logging, Amazon links without a price always in the phone's refresh list, re-adding a stuck link fills it in, `python-multipart` in requirements, Flipkart link cleaning, and real names for URL-named items after any check. 44 tests passing
- Phone round on the real app: Refresh rescued the stuck Amazon item, the sneakers' third share said "already saved", every request now logs when it starts
- Planned the "Needs a price" fallback with a mockup built from the app's real stylesheet; realised a price box alone doesn't help when Amazon hides everything, and changed the plan
- `feature/add-by-hand`: `POST /items` takes an optional link (saved without contacting the store), an Add by hand card, stuck rows that explain why and what to do, "typed by you" labels, store letters instead of "H", and short links corrected after a check. 47 tests passing
- Phone round: Add by hand with and without a link, the number keyboard, duplicates refused; Refresh renamed the long-stuck Amazon row to its real product and replaced my typed Alexa price with Amazon's. Refresh also caught real price changes (Apple Watch ₹40,990 → ₹35,509)

**2026-10-08**
- Decided the refresh button leaves Amazon to the iPhone, and thought through what that means after deployment and for other people (Android, the official Amazon API)
- `feature/refresh-button`: a `PHONE_ONLY_STORES` list that `/refresh` skips (with a test that the fake store is never asked for Amazon), a ↻ button with a spinning icon and a short note, and reloading when the app comes back into view. Checked the phone header with the real fonts so the tagline stays on one line. 48 tests passing
- Phone round from the office: hit the per-address settings and CORS (Challenge 23); then ↻ worked on laptop and phone, and after *Refresh OnTrack* the list updated by itself on switching back to Safari