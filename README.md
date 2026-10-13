# OnTrack

> A budget-aware wishlist for Indian online shopping. Share or paste a product link from any store, and OnTrack pulls the product name and price automatically, totals everything you plan to buy, and shows what's left of your monthly budget.

[![Tests](https://github.com/Shreishta04/OnTrack/actions/workflows/tests.yml/badge.svg)](https://github.com/Shreishta04/OnTrack/actions/workflows/tests.yml)

**Status:** 🟢 Live at **https://on-track-eta.vercel.app** (invite-only). Price extractor ✅ · Backend API ✅ · iPhone Shortcuts ✅ · Web app ✅ (laptop + phone) · Browser extension ✅ (Chrome / Edge) · Postgres ✅ · Deployed ✅ (Vercel + Railway + Neon) · Accounts ✅ (own list, budget, currency and time zone per person)

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

**Accounts**
- **Invite-only:** I make a one-time invite link in the app (valid 7 days) and send it myself; nobody can sign up without one. The very first account uses the server's `ONTRACK_API_KEY` as its invite, so nobody can grab the owner account after a deploy
- **Everyone has their own list and budget:** items, links, prices and purchases belong to one person. Asking for someone else's item answers *not found*, for every route
- **Own currency, country and time zone:** chosen at sign-up (guessed from the device) and changeable in Account. Prices show as `₹1,23,456` in India and `$120.50` in the US; "spent this month" follows each person's own calendar. No currency conversion: prices are shown as the store gave them
- **The same product on two lists:** duplicate checks are per person, so two people can save the same lipstick, but one person still can't save it twice
- **A key per device:** each Shortcut and the browser extension gets its own key from **Account → Devices**, shown once and removable if a phone is lost, without touching anything else
- **Email + password**, hashed with scrypt; a wrong email and a wrong password get the same answer; logins are rate-limited
- **Forgot the password?** I make a one-time reset link (valid 2 days) in **Account → People**. Using it signs out old logins but keeps device keys, so the Shortcuts don't break. Changing a password signs out every other login

**Saving items**
- **Share from the iPhone → item saved** with name, current price, MRP and image, via an iOS Shortcut in the Share Sheet
- **Paste a link** (laptop / API) → same result, with the server fetching the page itself
- **One item, several stores:** e.g. the same watch on Amazon and Fastrack. Only the **cheapest** link counts toward the budget, so items are never counted twice
- **Duplicate detection:** the same product shared twice, even via a short link or with different tracking junk, is rejected. Amazon, Savana and Flipkart links are reduced to just the part that identifies the product
- **Browser extension (laptop):** on any product page, click the OnTrack icon in Chrome or Edge → **Add to OnTrack**. It sends the page your browser already shows, so Amazon works from the laptop too, with no bot-check. On a product that's already saved it offers **Update price**; if a page has no price (a category page), it says so and offers **Remove it**
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
- **Paste a link** to add an item from the laptop, with a note that Amazon works best shared from the iPhone (or added with the browser extension)
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
Chrome / Edge ──► OnTrack extension                                 │
                         reads the page already open in the tab,    │
                         uploads it the same way ───────────────────┤
                                                                    │
React web app (laptop / phone browser) ── JSON ──────────────────┤  HTTP + JSON
                                                                    ▼
                                                 FastAPI backend (Python)
                                                  ├── main.py       HTTP layer: routes, validation, error → status code
                                                  ├── auth.py       Accounts: sign-up by invite, logins, device keys, resets
                                                  ├── services.py   Business rules: lists, budget, cheapest link, refresh (always for one user)
                                                  ├── db.py         Tables and connections (SQLite or Postgres)
                                                  └── extractor.py  Page → name, price, MRP, image
                                                                    │
                                                                    ▼
                                  SQLite (my laptop)  or  Postgres (deployed), picked by DATABASE_URL
```

The layers are kept separate on purpose. `services.py` doesn't know about HTTP, so its rules can be tested directly and reused (for example by a future bot). All SQL lives in `db.py` and `services.py`, so moving from SQLite to Postgres was a contained change: `services.py` and `main.py` didn't change at all (Challenge 25).

**Fetching is separate from parsing.** The extractor never downloads anything itself; it calls whatever *fetcher* it is given. On the laptop that's a Chrome-like downloader. For pages the phone (or the browser extension) already has, it's a fetcher that simply hands back the uploaded page and refuses to go online for anything else. The same parsers run either way, which is what made phone-side fetching, and later the browser extension, small changes: the extension needed only one backend addition.

### Frontend

The web app is a React + TypeScript single page, built with Vite. Each part of the screen is a **component** in its own file (`BudgetCard`, `Tabs`, `ItemRow`, `AddLink`, `AuthScreen`, `AccountSheet`, …). Three decisions shape it:

- **The server is the single source of truth.** After any button press the app calls the API and then reloads `/summary`, instead of recalculating budgets in the browser. The backend already computes spent-this-month, what fits and purchase prices (and is tested), so the screen can never drift from the database.
- **One place talks to the server.** `api.ts` adds this browser's login token, reads the JSON and turns failures into plain sentences ("Can't reach the server…"). Components only call functions like `getSummary()` or `patchItem()`. A `401` anywhere means the login has ended: `api.ts` forgets the token and the app goes back to the sign-in screen, clearing the list from view.
- **Money follows the person.** `money.tsx` gives every component the user's currency symbol and digit grouping through a React *context* (a value every component can read without passing it down by hand), so `<Price>` shows `₹` or `$` without each component knowing.

### Data model

```
users             one person: email, password hash, budget, currency, country, time zone, owner or not
  ├── tokens      a login (web app) or a device key (Shortcut, extension); only a SHA-256 hash is kept
  ├── invites     one-time sign-up links, and password-reset links (for_user_id set)
  └── items       a thing I want to buy ("Smartwatch")
        │           status: planned / later / purchased, plus purchase price and date
        ├── links   where it's sold (Amazon ₹1,999 · Fastrack ₹2,499); also carries user_id
        │     └── price_history   one row per successful price check
        └── status_changes        one row per move between lists (from → to, when)
settings          key/value; only the budget from before Accounts, read once
```

Deleting an item removes its links, price history and status history with it (`ON DELETE CASCADE`). Links carry `user_id` as well as their item, so the database itself enforces "unique per person": a unique index on `(user_id, url)`.

## Tech stack and why

| Part | Choice | Why |
|---|---|---|
| Backend language | **Python** | Best scraping ecosystem (`curl_cffi`, BeautifulSoup) and fast iteration. Considered Java (too heavy for a small API) and Node.js (its browser-impersonation libraries are less mature, and that turned out to be the hardest part of the project) |
| API framework | **FastAPI** | Small amount of code, automatic validation with Pydantic, free interactive docs at `/docs` |
| Fetching | **curl_cffi** (laptop/server) · **the iPhone itself** (Amazon) | See "Challenges" below |
| Parsing | **BeautifulSoup + lxml**, regex for embedded JSON | Standard, robust HTML parsing |
| Uploads | **python-multipart** | Lets FastAPI read the page the phone uploads as a file |
| Database | **SQLite** locally, **Postgres** when hosted (one setting, `DATABASE_URL`) | SQLite needs no setup locally; hosted servers don't keep local files, so production needs a separate database. Switching early was considered during the "server freezes" bug and rejected: the real cause was in my code (Challenge 16) |
| Postgres driver | **psycopg 3** | The standard Python driver for Postgres. Only loaded when `DATABASE_URL` is set, so the laptop never needs it |
| Automated tests | **GitHub Actions** | Runs every test on SQLite **and** a real Postgres 16 on every push, plus the frontend build and lint, on Linux. My work laptop can't run Postgres (Challenge 26), so this is where the Postgres half is checked |
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

### 24. The browser extension: the laptop gets the phone's trick

**Problem:** pasting an Amazon link on the laptop makes the server download the page, and Amazon sometimes answers with a bot-check (Challenge 11).

**Solution:** a Chrome/Edge extension that sends the page **the browser already loaded**, as I see it, to the same `/items/from-html` route the iPhone uses. The server never contacts Amazon. It even helps other stores: the browser has already filled in prices that load with JavaScript.

**Decisions:**
- **Plain JavaScript, no build step:** four small files plus icons. TypeScript and Vite would add setup for little gain here.
- **Least permissions:** `activeTab` + `scripting` let it read only the current tab, only when I click the icon; it never sees other tabs or my browsing. It may talk to `localhost` and `127.0.0.1` out of the box; any other server needs a one-time "allow" when it's saved in the settings.
- **No CORS change needed:** extensions with host permissions aren't held to the browser's cross-site rule, so the server's CORS list stays as it is. I confirmed it in a test with the list untouched.
- **The page goes as a file** (a `Blob` in the form), for the same 1 MB form-field reason as the Shortcut.
- **"Already saved" became useful:** the `409` reply now includes `link_id` (one backend change, with a test), so the popup offers **Update price**, which gives me Amazon price refreshes from the laptop.
- **Server data is shown with `textContent`, never `innerHTML`,** so an odd product name can't inject code into the popup.

**Problems found while building it:**
- **Settings never appeared on a non-product page.** The popup checked "is this a product page?" before "is it set up?", so a first-time user opening it on a new tab got stuck. Found by running it in a headless Chromium; the settings check now comes first.
- **Tested before I saw it:** the real extension ran in headless Chromium against the real backend and a tiny fake store: add, already saved → update price (₹1,200 → ₹999), no-price page → remove.
- **Unzipped one level too deep:** Windows' *Extract All* made `extension/extension/manifest.json`, which Chrome couldn't load, and I'd already committed it. Fixed with a second commit that moves the files up; git recorded it as renames.

### 25. One codebase, two databases

**Goal:** the same code runs on SQLite (my laptop) or Postgres (once deployed), picked by one setting, `DATABASE_URL`. If it isn't set, everything works exactly as before, so if the deployment ever goes wrong, removing it takes me back to SQLite.

**What was different between the two:**
- **New ids.** The code read a new row's id with `cursor.lastrowid`, which Postgres doesn't have. **Fix:** `INSERT … RETURNING id`, which both databases understand.
- **Placeholders.** SQLite writes `WHERE id = ?`; psycopg (the Postgres driver) writes `%s`. **Fix:** a small wrapper in `db.py`, `PgConnection`, that looks like the SQLite connection to the rest of the code and translates on the way through. `services.py` and `main.py` didn't change.
- **A hidden trap:** the rename rule uses `LIKE 'http%'`. To psycopg, a lone `%` means "a value goes here", so that query would crash on Postgres. **Fix:** the wrapper writes a real `%` as `%%` first, then turns `?` into `%s`. A test failed on Postgres when I removed this on purpose, so it's guarded.
- **Counting ids.** SQLite's `AUTOINCREMENT` is `GENERATED BY DEFAULT AS IDENTITY` on Postgres. The Postgres tables are made from the **same** schema with that one phrase swapped, so there's one copy of every table, not two.

**Tests run on both.** Every API test runs twice, `[sqlite]` and `[postgres]`. Without a test database (`TEST_DATABASE_URL`) the Postgres half is skipped, so the tests still work on any laptop. Two tests needed a decision: the "database locked" test guards a **SQLite-only** problem (Postgres locks single rows, not the whole file), so it's skipped on Postgres; the "moves are recorded" test opened the SQLite file directly, so it now goes through `db.connect()` and runs on both.

**Moving my data.** `copy_to_postgres.py` copies `ontrack.db` into an empty Postgres, **keeping every id**, so links still point at the right items and the Shortcuts' link ids stay the same. Its test caught two bugs:
- After inserting rows *with* ids, Postgres doesn't move its id counter, so the first new item was given id 1, which already existed (*"Key (id)=(1) already exists"*). **Fix:** set each counter after copying.
- My first fix set the counter to the highest id, but SQLite **never reuses** a deleted item's id, so my copy handed out an id SQLite never would. **Fix:** copy SQLite's own counters (kept in a hidden table, `sqlite_sequence`).

It all runs in one transaction (saved together or not at all), refuses to copy into a database that already has items, and checks that every table has the same number of rows on both sides.

**Slips worth remembering:**
- Replacing `lastrowid`, I left the old insert above the new one, so every item was saved **twice**. Two tests that count items caught it straight away (`assert 2 == 1`).
- I committed Step 1 while on `main` instead of the feature branch. Nothing had been pushed, so I moved it: `git switch feature/postgres`, `git merge --ff-only main`, then `git branch -f main origin/main`. **Habit:** read the first line of `git status` (*On branch …*) before committing.

### 26. My work laptop can't run Postgres

**Symptom:** after adding psycopg, the tests crashed before running: *"DLL load failed… An Application Control policy has blocked this file."* Installing PostgreSQL itself then failed with *"The database cluster initialisation failed"*.

**Cause:** the laptop has Windows **Smart App Control**, which only lets files run if they're signed by a known publisher. The installers are signed, but some of the smaller files they bring along aren't, so Windows blocked them. It can't be relaxed for one app, turning it off is permanent, and on a work laptop it isn't my call anyway.

**Fix (working around the laptop, not through it):**
- **The tests:** psycopg is only imported where Postgres is actually used, so on my laptop the Postgres tests are **skipped**, not crashed. **GitHub Actions** runs all of them on every push, on Linux, with a real Postgres 16 next to them.
- **Moving my data:** `copy_to_postgres.py --sql-out ontrack_copy.sql` writes the whole copy as a plain `.sql` file, which needs nothing but Python. At deploy time I paste it into Neon's SQL Editor in the browser. It keeps every safety check of the direct copy, wrapped in one `DO` block that Postgres runs all-or-nothing. In SQL, text sits inside single quotes, so a name like *Levi's* would end it early; the script writes a quote twice (`'Levi''s'`), and a test checks that names with quotes, `%`, `?`, emoji and line breaks arrive exactly as typed. The file holds my whole list, so it's in `.gitignore`.

**A slip:** the first workflow file reached GitHub **empty** (created in VS Code but never filled), and the run failed instantly. `git diff --stat` before committing shows how many lines each file changed; 0 lines on a file I meant to fill is the giveaway.

### 27. Before going public: hardening

Until now the server only listened inside my home Wi-Fi. On Railway, anyone on the internet can reach it. The API key still protects every endpoint, but four things had to change first, each with tests that fail without the fix.

**1. Only public websites (SSRF).** The server downloads whatever link it's given, so someone could hand it an *internal* address: the host's private network, or `169.254.169.254`, where cloud servers keep their secrets. This is called SSRF (server-side request forgery). Before every download the server now checks that the link is `http`/`https`, on a normal web port (80 or 443), and that its name points **only** at public addresses. Three tricks needed extra care:
- **The same address written differently:** `http://2852039166/` *is* `169.254.169.254`. The name is looked up, not just read, so the real address is what gets checked.
- **Redirects:** curl used to follow them by itself, so a public page could bounce the server to an internal one. Redirects are now followed by my own code, and every hop is checked *before* anything is downloaded from it.
- **DNS rebinding:** a name can point at a public address while it's checked and at a private one a moment later, when curl connects. The checked address is **pinned**: curl connects to exactly that address instead of looking the name up again.

Adding such a link answers **400** (*"OnTrack won't open this link: … points to a private or internal address."*) and saves nothing.

**2. Upload size limit.** The phone and the extension upload whole store pages (Amazon: ~1.7 MB). Anything over **5 MB** gets **413**. FastAPI reads an upload *before* checking the API key, so the limit sits in front of everything: an outsider without the key can't send a giant file either. It checks the size the sender announces (`Content-Length`) **and** counts the bytes that actually arrive, for uploads that don't announce a size (*chunked*). My first version raised an error when the count went over, and FastAPI caught it and answered a confusing **400 "error parsing the body"**. Testing against a real server found it; the limit now answers 413 itself and tells the app the sender has gone away.

**3. Rate limiting.** At most **60 requests a minute** from one address, and **10** for the heavy ones that make the server download store pages (add from link, ↻ Refresh). Over the limit: **429** with `Retry-After`. It's a *sliding window* (the last 60 seconds, not "this minute on the clock"), so a burst can't straddle two minutes to get double. A leaked key or a Shortcut stuck in a loop can't burn the hosting credit or get the server blocked by stores. It's kept in memory, which is fine for one server process.

**4. "This month" in India time.** Times are stored in UTC, which is 5½ hours behind India, so a purchase at 00:30 on 1 November counted toward **October**. Times are still *stored* in UTC (one unambiguous clock), but spent-this-month now follows `ONTRACK_TIMEZONE` (default `Asia/Kolkata`). A misspelt zone stops the server at startup instead of quietly making every month wrong. Windows doesn't include the time zone database Python needs, so `tzdata` is in `requirements.txt`.

All four limits are settings (`ONTRACK_MAX_UPLOAD_MB`, `ONTRACK_RATE_LIMIT`, `ONTRACK_RATE_LIMIT_HEAVY`, `ONTRACK_TIMEZONE`), so they can change without touching code.

**A slip worth remembering:** one update reached me as the *previous* version of two files; the tests said `68 passed` instead of the expected `70`, and `git status` said "nothing to commit". The expected test count and `git diff --stat` are how I check a change really landed.

### 28. A security sweep before deploying

Before putting OnTrack on the internet I read the whole project the way an attacker would, and tested each suspicion instead of guessing. Already fine: no secret ever in git history, no known vulnerable packages (`pip-audit`, `npm audit`), SQL always uses placeholders, the key is compared in constant time, the extension only reads the current tab on click and shows server data with `textContent`. Found and fixed:

1. **A page could freeze the server (ReDoS).** The pattern that reads a page's canonical tag (`<link[^>]+rel=…[^>]+href=…`) took **22 seconds on a 21 KB page** built to trip it, and practically forever on 5 MB: a regular expression that tries an exploding number of ways to match. Limiting each part's length wasn't enough (still a minute), because it restarted at every one of 250,000 tags. **Fix:** no clever pattern; scan tag by tag, cut each tag out (at most 2,000 characters) and read only that piece, never re-reading a character. Hostile 5 MB pages now take 0.15 s. The old code froze on the new test, which is the proof.
2. **The rate limit could be dodged (and I had suggested the setting).** The planned Railway command trusted `X-Forwarded-For` completely (`--forwarded-allow-ips="*"`), and uvicorn then believes the *first* address in it, which the sender writes. An experiment showed a client could pose as a new address on every request. **Fix:** only the **last** entry counts, the one Railway's proxy writes (`ONTRACK_TRUST_PROXY=on`), plus a cap for everyone together (30 page downloads a minute), so even a trick I haven't thought of can't burn the credit.
3. **A page could plant a `javascript:` link.** The server trusted a page's canonical tag as the item's address; a hostile page could make it `javascript:…`, which would run code in the app (where the API key is kept) if clicked. React 19 happened to block it, but only React. **Fix:** only `http(s)` links and images are saved.
4. **A weak key was accepted**, including the example `change-me`. **Fix:** the server refuses to start with a key under 24 characters.
5. **Smaller ones:** `/docs` can be hidden (`ONTRACK_DOCS=off`); names and notes have length limits (the free database is 1 GB); the phone's refresh uploads (each 5 MB page takes seconds of CPU) got their own limit.

**Deploy files:** `frontend/vercel.json` adds browser security headers. The main one is a *Content Security Policy*: the deployed page may only run its own scripts and only talk to `https` addresses, so even if something slipped past React, injected code couldn't load scripts from elsewhere or talk to plain-`http` servers. Tested in a headless browser: the app renders, and a plain-`http` server is refused. `backend/railway.json` holds the start command and health check, so Railway's settings live in git.

### 29. Deploying: three settings and a surprise plan

Getting OnTrack online took three services (Vercel for the web app, Railway for the server, Neon for the database) and four small problems, each from a setting that worked differently than I assumed.

**1. Railway looked in the wrong folder.**
- *Symptom:* the first build failed; Railway couldn't work out what kind of app it was.
- *Cause:* Railway builds from the **top** of the repo by default, but the server lives in `backend/` (that's where `main.py` and `requirements.txt` are). From the top folder it sees only folders, nothing it recognises as a Python app.
- *Fix:* service settings → **Root Directory** = `/backend`.

**2. Railway didn't find `railway.json`.**
- *Symptom:* with the root fixed, the start command and health check from `backend/railway.json` were still ignored.
- *Cause:* the config-file path does **not** follow the Root Directory. It's always counted from the top of the repo.
- *Fix:* **Config File** = `/backend/railway.json`.

**3. One slash broke CORS.**
- *Symptom:* the deployed web app couldn't load anything; the browser blocked every request to the server.
- *Cause:* CORS compares the page's *origin* (scheme + address, never a trailing slash) with `ONTRACK_CORS_ORIGINS` letter for letter. `https://on-track-eta.vercel.app/` with a slash is not the same text as `https://on-track-eta.vercel.app`, so nothing matched.
- *Fix:* `ONTRACK_CORS_ORIGINS=https://on-track-eta.vercel.app`, no slash.

**4. "Free plan" turned out to be a trial first.**
- *Symptom:* the account said **Trial: $5, 30 days** instead of the free plan with $1 a month I'd planned around.
- *Cause:* new Railway accounts start on a 30-day trial with one $5 credit and drop to the free plan afterwards (around 10 November for me).
- *Fix:* nothing to fix, just to plan for: no upgrade and no card. I check **Usage** for a week, and when the trial ends I check the server still runs (Redeploy if it was paused). Real usage after a day of testing: **$0.0045**, because Serverless mode lets the server sleep between requests.

**Testing the live version** the same day, from the phone on mobile data with the laptop off, found real things too (listed under *Found while using it*): Savana blocks Railway, Tira isn't readable yet, and leftover text in the extension's settings fields (`…vercel.app73`) that it saved without checking.

### 30. Three small lies the live version told

Testing the deployed app turned up three places where OnTrack said one thing and did another. None was dramatic, but each sent me down the wrong path for a while.

**1. "OnTrack will try again on the next refresh" (it waited an hour).**
- *Symptom:* a Savana item without a price stayed stuck after ↻, and the note said "Checked 2", which didn't include it.
- *Cause:* ↻ skips links checked in the last hour, and a **failed** check counts as a check. Amazon's phone list already made an exception for links with no price; the server's ↻ didn't.
- *Fix:* one rule for both: a link is due if it was checked over an hour ago **or still has no price**. A test adds a refused link, lets the store "work again" minutes later, and checks that ↻ fills it in. It failed on the old code.

**2. "Probably loads its price with JavaScript" (it didn't).**
- *Symptom:* Tira, added with the extension, said the price probably loads with JavaScript, while the price was right there on my screen.
- *Cause:* that's the reader's guess when it finds a name but no price, and it's fair for a page the **server** downloaded (the server never runs JavaScript). But the extension sends the **finished** page, after its JavaScript ran.
- *Fix:* for a page from the phone or the extension, the reason is now *"Got the name but no price. This isn't a single product page, or OnTrack can't read this store's prices yet."* Pages the server downloaded keep the old wording. The real Tira fix (a reader for its pages) is still to do.

**3. The logs said nothing useful.**
- *Symptom:* to find out why Savana failed, I searched Railway's logs for "savana" and found nothing.
- *Cause:* the server only logged `started POST /items`, never which store it fetched or why it failed. The reason was only visible by tapping the row in the app.
- *Fix:* one line for every store page:
  ```
  store    link=21  host=in.savana.com  via=server  result=blocked  reason="Store returned HTTP 471 (blocked or not found)"  took=1.2s
  ```
  `via` says **who downloaded the page**: `upload` (the phone or the extension) or `server`. When an upload has no price and the server tries itself, both tries are logged, which is exactly the Savana story in two lines. What's deliberately **not** in a log line: the full link (with Accounts, links would show what people shop for; `link=` finds it in the database), the page, request headers, and so never the API key. Web addresses inside error messages (curl likes to repeat the link) become `<link>`. A test makes requests with the right key, a wrong key and a secret-looking product link, and fails if any of them appears in the logs.

### 31. Accounts: one list became many

Before inviting anyone, every item, link and the budget had to belong to someone, and the iPhone Shortcuts and the extension had to keep working on the day it went live. The decisions and the problems, in order:

**1. A cookie wouldn't survive Safari.**
- *Problem:* the usual way to stay logged in is a cookie, but the web app (Vercel) and the server (Railway) are different sites, and Safari blocks cookies between different sites.
- *Decision:* logging in gives the browser a **token** that it sends in the same `X-API-Key` header the Shortcuts already use. One mechanism for everything: the Shortcuts and the extension just get their own token (a *device key*). Only a SHA-256 hash of each token is stored, so a database leak doesn't leak working keys. A fast hash is fine there because tokens are 32 random bytes; passwords are different (people pick guessable ones), so they get **scrypt**, which is slow and memory-hungry on purpose.

**2. Who creates the first account?**
- *Problem:* invite-only needs someone to send the first invite, and an open "first sign-up becomes the owner" would let a stranger grab the account in the minutes after a deploy.
- *Decision:* the first account's invite code is the server's `ONTRACK_API_KEY`, which only I know. That account becomes the owner and is given everything already in the database (items and links had no owner yet) plus the old budget. The old key also keeps working as the owner, so the Shortcuts and extension didn't break on deploy day; each gets its own device key afterwards.

**3. "Unique link" had to become "unique per person", and SQLite can't drop a rule.**
- *Symptom (planned for):* `links.url` was `UNIQUE` for the whole table, so a second person couldn't save the same lipstick.
- *Cause:* Postgres can drop that rule with one `ALTER TABLE`. SQLite can't remove a rule from an existing table at all.
- *Fix:* `db.migrate()` runs at every start and does nothing if already done. On Postgres it looks the rule up (rather than trusting its usual name, `links_url_key`) and drops it. On SQLite it follows SQLite's own recipe: create the new table, copy the rows **with their ids**, drop the old one, rename the new one, with foreign keys switched off for the moment so dropping the old table doesn't delete the price history. Then a unique index on `(user_id, url)` replaces the old rule. A test builds a database with the **old** tables and data, upgrades it twice, and checks every price check survived, two people can share a link, one person still can't save it twice, and deleting still cascades.

**4. Not giving anything away.**
- *Someone else's item answers 404, not 403:* "forbidden" would confirm that item 12 exists. Every route that takes an item or link number is tested from a second account.
- *A wrong email and a wrong password get the same answer and take the same time:* checking a dummy hash when the email doesn't exist stops anyone timing the reply to learn who has an account.
- *Logins and sign-ups get their own rate limit* (10 a minute per address), on top of the general one.

### Known limits

- **No currency conversion:** prices are shown in each person's currency as the store gave them. A US account that saves an amazon.in link sees the rupee number with a `$`. Stores do say their currency (`priceCurrency`); warning about a mismatch is a later step.
- **The owner key is a master key:** `ONTRACK_API_KEY` still acts as my account. Once every Shortcut and the extension use device keys, it can be changed to a new random value that's only used as the first invite.
- **Logins don't expire** until you log out, change the password, or a reset is used. Device keys can be removed in Account.
- **No emails:** invite and reset links are copied and sent by hand. Fine for a handful of people.
- **Rate limits live in memory:** they reset when the server restarts, and they'd need a shared store if OnTrack ever ran on several servers at once.
- **Two taps to refresh everything:** *Refresh OnTrack* for Amazon, ↻ for other stores. Planned: the Shortcut calls `/refresh` at the end, so one tap covers both.
- **Amazon links pasted into the web app** are fetched by the server and may be blocked (it's hit-and-miss). Use the browser extension on the laptop, or share the same link from the phone, and the item is filled in.
- **The extension is loaded by hand** (Developer mode → Load unpacked), not from the Chrome Web Store, so it shows a small "unpacked" badge, and after editing its files it needs a reload in `chrome://extensions`.
- **"Over budget" follows list order:** items are added up in list order, so after one expensive item, even a cheap one shows *Over budget*. To be redesigned.
- **Flipkart sizes and colours count as one item** (they share one product code). Lipstick shades on Flipkart may merge too.
- **A link that never gets a price** (for example a removed product, or a store that blocks the server) is tried again on **every** ↻, since links without a price skip the one-hour wait. Cheap, and the rate limits cap it, but worth knowing; delete the item or add it by hand.
- **Phone, development mode:** the first load on the phone can take a while, because Vite's dev server sends the app as many small files. A production build doesn't have this.
- **Postgres isn't tested on my laptop:** Smart App Control blocks it (Challenge 26), so locally the Postgres half of the tests is skipped. GitHub Actions runs it on every push; check the badge at the top before merging.
- **The first request after a quiet spell is slow:** Railway's Serverless mode puts the server to sleep when nobody uses it (that's why it costs almost nothing). The next request wakes it, which takes a few seconds and can answer one **502**; tapping again works.
- **Some stores block the cloud server:** stores can refuse requests from data centres. Amazon always did (the phone or the extension fetches it instead); since deploying, Savana does too (*error 471*). Flipkart, Littlebox and Fastrack-style stores still work from Railway.
- **Local development still uses the laptop's IP address:** when I run the server on the laptop for development, the Shortcuts and the phone need the laptop's Wi-Fi address, as before. The deployed setup has one fixed address.

### Found while using it, to fix later

Small things I noticed while testing that don't block anything yet:

- **Long amounts overflow the budget card.** A budget in crores (₹1,23,88,844 while testing) pushes the big number and the totals past the card's edge. Planned fix: smaller font for long amounts (tried and working in a test build; parked to keep this branch small).
- **"WISH LIST" wraps onto two lines** on the phone, while the other tabs fit on one.
- **Filling in a stuck link answers `201 Created`** although nothing new is created. Nothing reads the code today.
- **Test client warning** (`StarletteDeprecationWarning`, wants `httpx2`): harmless for now.

Found while testing the deployed version (12 Oct):

- **Savana is blocked from Railway** (*error 471*, a store-specific code). The phone's page reaches the server, but when it has no price the server tries the page itself as a backup, and that's what gets blocked. Next step: test whether the phone's own page has the price; if it does, Savana becomes phone-only like Amazon.
- **Tira can't be read yet.** The extension sends the finished page (price included), but OnTrack doesn't know where Tira puts the price. Tira's short links (`trbt.ly`) are redirect pages too. Needs a small Tira reader.
- **The add box's message never goes away**; it should clear on new input, with a ✕. Rows without a price could have a **Try again** button.
- **A blocked page is named after its link** (`https://in.savana.com/details/…`); "Savana item" until it fills in would read better.
- **The extension saves settings without checking them** (a leftover `73` made `on-track-eta.vercel.app73`). It should check the address, ideally by calling `/health`, before saving. On a non-product page, it could say so before saving anything.

## Store support

| Store | Method | Status |
|---|---|---|
| Amazon.in (incl. `amzn.in` short links) | Page from the iPhone or the browser extension (server fetch as a hit-and-miss fallback) · selectors / embedded price data | ✅ laptop (extension) · ✅ iPhone |
| Fastrack | JSON-LD (`schema.org/Product`) | ✅ laptop · ⏳ iPhone not tested |
| Savana (incl. share links) | JS redirect follow + embedded app data | ✅ local server · ❌ **deployed: Railway gets error 471**, phone route being tested |
| Shopify stores (Come Again, Littlebox, …) | `/products/<handle>.js`, JSON-LD fallback | ✅ single products (laptop and iPhone) · ⏳ carts |
| Flipkart (incl. app links) | Generic page data, links cleaned to `/p/itm…` | ✅ laptop (paste, extension) · ✅ iPhone (Share Sheet, clipboard) · ✅ deployed (Railway fetches it) · ⏳ MRP not read yet |
| Tira (incl. `trbt.ly` short links) | Name read, price not found | ❌ needs its own reader |
| Myntra, Ajio, Meesho | Not tested yet | ⏳ |

## Deployed

| Part | Where | Address |
|---|---|---|
| Web app | Vercel (project `on-track`) | https://on-track-eta.vercel.app |
| Server | Railway (service `OnTrack`, Southeast Asia, Serverless on) | https://ontrack-production-8f1d.up.railway.app |
| Database | Neon (Postgres, AWS Singapore, free 1 GB, direct connection) | only inside Railway's `DATABASE_URL` |

The server address isn't a secret (the web app has to know it), but every request needs a login or device key, and the rate limits cap what a stranger could do without one.

**How it's wired**

```
iPhone (Shortcuts, Safari)  ─┐
Laptop (browser, extension)  ├──► Railway: FastAPI server ──► Neon: Postgres
Web app from Vercel ─────────┘        (needs X-API-Key)
```

The web app is only files (HTML, JavaScript, CSS) that Vercel serves; the browser then talks to Railway directly. That's why the server's CORS setting names the Vercel address.

**Railway settings** (service → Settings and Variables)
- Root Directory `/backend`, Config File `/backend/railway.json` (start command and `/health` check live in that file, in git)
- Variables: `ONTRACK_API_KEY` (a production key, different from my laptop's), `DATABASE_URL` (Neon's connection string), `ONTRACK_TRUST_PROXY=on`, `ONTRACK_DOCS=off`, `ONTRACK_CORS_ORIGINS=https://on-track-eta.vercel.app` (no trailing slash, Challenge 29)

**Vercel settings**
- Root Directory `frontend`; Vite is detected by itself
- Environment variable `VITE_API_URL=https://ontrack-production-8f1d.up.railway.app`. **Never a key:** Vite copies `VITE_` values into the files anyone can download. Each browser gets its own login token when you log in.
- `frontend/vercel.json` adds the security headers (Challenge 28)

**Pointing the phone and the extension at it**
- Safari → the web app → log in → Share → **Add to Home Screen**
- **Account → Devices → New key** once per device (e.g. "iPhone Shortcuts", "Laptop extension"); each key is shown once
- **Add to OnTrack** Shortcut: step 5's URL → `https://ontrack-production-8f1d.up.railway.app/items/from-html`, header `X-API-Key` = the iPhone's device key
- **Refresh OnTrack** Shortcut: **both** URLs → `…/refresh/phone-list` and `…/links/<link_id>/from-html`, with the device key in both
- Extension → sliders: server and app as above, the laptop's device key in *API key*. Chrome asks once for permission to reach the server. Clear each field completely (Ctrl+A) before pasting

**Redeploying**
- **Web app:** Vercel rebuilds it automatically when I merge into `main`.
- **Server:** Railway deploys **by hand** (I'm the only one changing code, and a mistaken merge shouldn't go live by itself): Railway → service → Settings → Source → update, then Deployments → wait for the new entry to be **Active** → check `/health`. "Redeploy" on an old entry rebuilds the **old** code. For a change to both (like Accounts), deploy Railway straight after merging, since Vercel goes first.
- **A setting changed** (Railway variable or Vercel environment variable): Railway applies it with a redeploy (it may ask me to click **Deploy**); on Vercel, redeploy the latest deployment so the new value is baked in.
- **Is it alive?** `https://ontrack-production-8f1d.up.railway.app/health` → `{"ok":true}`. If something fails, Railway → the service → **Deployments → View logs**.
- **Reading the logs:** search for `store` to see every store page (`result=ok`, `no-price`, `blocked`, `network` or `refused`, with the reason), or for `link=21` to follow one product. `via=upload` means the phone or the extension downloaded the page; `via=server` means the server did.

**Costs**
- Vercel and Neon: free plans. Railway: a 30-day trial with $5 of credit, then the free plan with $1 a month. Usage on day one: **$0.0045**. I check **Usage** for a week, and no upgrade or card without deciding first.

**Moving the data across (once):** `copy_to_postgres.py --sql-out ontrack_copy.sql`, pasted into Neon's SQL Editor (my laptop can't connect to Postgres, Challenge 26). 15 items, 14 links, 39 price checks and 20 moves arrived with their ids; the copy file was deleted afterwards.

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

On a laptop without Postgres, `pytest` says something like *49 passed, 37 skipped*: the skipped ones are the Postgres half, which GitHub Actions runs on every push.

### Settings

All optional except `ONTRACK_API_KEY`; put them in `backend/.env` locally or in the host's settings when deployed. Nothing new is needed for Accounts.

| Setting | Default | What it does |
|---|---|---|
| `ONTRACK_API_KEY` | (required) | The owner key: the invite code for the first account, and it acts as the owner's account in `X-API-Key` |
| `ONTRACK_CORS_ORIGINS` | `http://localhost:5173` | Web addresses allowed to call the API from a browser (comma-separated; never `*`) |
| `DATABASE_URL` | unset (SQLite) | Postgres address; see below |
| `ONTRACK_DB` | `ontrack.db` | SQLite file, when `DATABASE_URL` isn't set |
| `ONTRACK_TIMEZONE` | `Asia/Kolkata` | Fallback calendar for "spent this month" (each person has their own time zone) |
| `ONTRACK_MAX_UPLOAD_MB` | `5` | Largest upload accepted (413 above it) |
| `ONTRACK_RATE_LIMIT` | `60` | Requests per minute from one address (429 above it) |
| `ONTRACK_RATE_LIMIT_HEAVY` | `10` | Per minute for requests that download store pages |
| `ONTRACK_RATE_LIMIT_HEAVY_TOTAL` | `30` | Page downloads per minute from **all** addresses together |
| `ONTRACK_RATE_LIMIT_UPLOADS` | `30` | Refresh uploads (`/links/{id}/from-html`) per minute |
| `ONTRACK_RATE_LIMIT_LOGIN` | `10` | Log-in, sign-up and reset attempts per minute from one address |
| `ONTRACK_TRUST_PROXY` | `off` | `on` behind Railway's proxy: the real address is the **last** `X-Forwarded-For` entry |
| `ONTRACK_DOCS` | `on` | `off` on the deployed server hides `/docs` |

The key must be at least 24 characters (`python -c "import secrets; print(secrets.token_urlsafe(32))"`); the server won't start otherwise. Don't start uvicorn with `--forwarded-allow-ips="*"`: it lets clients fake their address (Challenge 28).

### Using Postgres instead of SQLite

Set `DATABASE_URL` (in `backend/.env` or the host's settings) and the app uses Postgres; the tables are created on first start. Leave it unset for SQLite.

```
DATABASE_URL=postgresql://user:password@host/dbname
```

To run the Postgres tests too, point `TEST_DATABASE_URL` at an **empty** database (its tables are wiped before each test):
```powershell
$env:TEST_DATABASE_URL = "postgresql://user:password@localhost/ontrack_test"
pytest -q
```

To move an existing `ontrack.db` into an empty Postgres:
```powershell
python copy_to_postgres.py "postgresql://user:password@host/dbname"     # if this computer can connect
python copy_to_postgres.py --sql-out ontrack_copy.sql                   # otherwise: paste the file into the database's SQL editor
```
Both keep every id and check row counts; both refuse if the database already has items. `ontrack_copy.sql` contains the whole list: it's git-ignored, and worth deleting after use.

### The web app

Requires Node.js 18+ (LTS). In a second terminal, from the top `OnTrack` folder:

```powershell
cd frontend
npm install
```

Create `frontend/.env.local` (git-ignored) so the app knows where the server is during development:

```
VITE_API_URL=http://127.0.0.1:8000
```

(An old `VITE_API_KEY` line can be deleted: the app doesn't read it any more.) Then, with the backend running:

```powershell
npm run dev
```

Open **http://localhost:5173** (`localhost`, not `127.0.0.1`, because CORS only allows `localhost`). The first time on a database without accounts, tap **Have an invite? Create your account** and use `ONTRACK_API_KEY` from `backend/.env` as the invite code: that account becomes the owner and gets everything already saved. After that, log in with email and password.

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

On the laptop, an Amazon price can also be refreshed with the browser extension: open the product, click the icon → **Update price**.

### Using the browser extension (Chrome or Edge)

1. Open `chrome://extensions` (or `edge://extensions`), turn on **Developer mode**, click **Load unpacked** and pick the `extension` folder.
2. Pin it: the puzzle-piece icon in the toolbar → 📌 next to OnTrack.
3. Click the OnTrack icon. The first time, it asks for the **server** (`http://localhost:8000`), the **API key** (a device key from the web app's **Account → Devices → New key**) and the **app address** (`http://localhost:5173`). The sliders button changes them later.
4. On a product page: **Add to OnTrack**. On a product already saved: **Update price**.

After editing any file in `extension/`, click ↻ on its card in `chrome://extensions`.

## API overview

All endpoints except `/health` and `/auth/signup|login|reset` need a login token or device key in the `X-API-Key` header (missing or wrong: **401**). Everything acts on that person's own list. Besides the usual codes, the server can answer **400** (a link to a private or internal address, a used invite, a weak password), **403** (owner-only), **413** (upload over the size limit) and **429** (too many requests; `Retry-After` says how long to wait).

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/auth/signup` | Create an account: `invite`, `email`, `password` (10+), `name`, `currency`, `country`, `timezone`. Answers `{user, token}` |
| `POST` | `/auth/login` · `/auth/reset` | Log in with email + password, or set a new password with a reset `code`. Answers `{user, token}` |
| `POST` | `/auth/logout` | End this login |
| `GET` · `PATCH` | `/me` | Your profile; change name, currency, country, time zone |
| `POST` | `/me/password` | Change password (`current`, `new`); other logins are signed out |
| `GET` · `POST` · `DELETE` | `/tokens` · `/tokens/{id}` | Your logins and device keys; make a device key (shown once); remove one |
| `GET` · `POST` · `DELETE` | `/invites` · `/invites/{id}` | Owner: list, make (7 days, one use) or cancel invites |
| `GET` | `/users` | Owner: everyone with an account |
| `POST` | `/users/{id}/reset` | Owner: a one-time password-reset code (2 days) |
| `GET` | `/summary` | Budget, discounted total, spent this month, remaining, savings vs MRP, what fits, all items |
| `PUT` | `/budget` | Set the monthly budget |
| `GET` | `/items?status=` | List items: `planned`, `later`, `purchased` or `all` (default) |
| `GET` | `/items/{id}` | One item with its links |
| `GET` | `/items/{id}/history` | Every price check for the item's links, oldest first |
| `POST` | `/items/from-link` | Save an item from a link (the server fetches the page). A link already saved **without** a price is filled in instead of rejected |
| `POST` | `/items/from-html` | Save an item from a page the phone or the browser extension already has (form: `url` + `html` file); non-Amazon pages without a price fall back to a server fetch. A duplicate answers `409` with `item_id` and `link_id` |
| `POST` | `/items` | Add by hand: name + price, optional `url` (saved without contacting the store; Refresh can fill in the store's price later) |
| `POST` | `/items/{id}/links` | Add another store's link to an item |
| `PATCH` | `/items/{id}` | Edit name, status, priority, manual price, note, purchased price |
| `DELETE` | `/items/{id}` · `/links/{id}` | Remove an item or a link |
| `POST` | `/refresh?force=` | Re-check prices: skips bought items, links checked in the last hour (unless they still have no price), and phone-only stores (Amazon). Returns `checked`, `skipped_recent`, `phone_only`, `changed`, `failed` |
| `POST` | `/items/{id}/refresh` | Re-check one item |
| `GET` | `/refresh/phone-list?force=` | Amazon links the phone should re-download: not bought, and either not checked in the last hour or still without a price |
| `POST` | `/links/{id}/from-html` | Upload a fresh page for one link (phone refresh, or the extension's **Update price**); records the new price |

## Project structure

```
OnTrack/
├── .github/workflows/
│   └── tests.yml          GitHub Actions: tests on SQLite + Postgres, frontend build + lint
├── backend/
│   ├── main.py            FastAPI routes
│   ├── auth.py            accounts: invites, passwords, tokens, resets
│   ├── services.py        business logic
│   ├── db.py              schema and upgrades of old databases; SQLite or Postgres (DATABASE_URL)
│   ├── extractor.py       page → product details
│   ├── copy_to_postgres.py  copies ontrack.db into Postgres (or writes a .sql file)
│   ├── railway.json       Railway: start command and health check
│   ├── tests/             offline tests (fake pages, fake extractor, fake DNS): 171, most run on SQLite and Postgres
│   ├── requirements.txt
│   └── .env.example       settings template (real .env is git-ignored)
└── frontend/
    ├── index.html             the single HTML page (fonts, theme colour)
    ├── .env.local             dev server address (git-ignored)
    ├── vercel.json            security headers for the deployed web app
    └── src/
        ├── main.tsx           entry point: draws <App /> into the page
        ├── App.tsx            sign-in screen or the list; loads /summary, owns the tab, handles button presses
        ├── api.ts             every request to the backend, with this browser's login token
        ├── money.tsx          the person's currency symbol and digit grouping, for every <Price>
        ├── places.ts          countries, currencies, time zones; first guesses from the device
        ├── types.ts           shapes of the data the backend sends
        ├── format.ts          store names, short dates, plain-words errors and tips
        ├── index.css          design tokens (light + dark), layout, components
        ├── hooks/
        │   └── useTheme.ts    light / dark / follow the device
        └── components/
            ├── BudgetCard.tsx     budget, bar, totals, in-card budget editing
            ├── Price.tsx          every amount, drawn the same way, in the person's currency
            ├── AddLink.tsx        paste-a-link box
            ├── AddByHand.tsx      name, optional link, price
            ├── Tabs.tsx           Wish list · Later · Bought · All
            ├── ItemList.tsx       the rows for the current tab
            ├── ItemRow.tsx        one expandable row: details, why it's stuck, actions
            ├── Thumb.tsx          product photo or a letter
            ├── AuthScreen.tsx     log in, sign up with an invite, new password from a reset link
            ├── AccountSheet.tsx   profile, device keys, people and invites (owner), password, log out
            └── Icons.tsx          refresh, moon, sun, sliders, close
└── extension/                 Chrome / Edge extension (plain JavaScript, no build step)
    ├── manifest.json          name, permissions (current tab only, on click), icons
    ├── popup.html             the window that opens from the toolbar icon
    ├── popup.css              the app's colours, light and dark
    ├── popup.js               reads the page, sends it, shows the result; settings
    └── icons/                 the toolbar icon in 4 sizes
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
- [x] Browser extension: "Add to OnTrack" on the laptop, sending the page you're viewing to `/items/from-html`; Update price for saved items; Remove for pages without a price
- [ ] Installable PWA (home-screen icon, app name, offline shell)
- [x] Postgres support: one setting (`DATABASE_URL`) picks SQLite or Postgres; tests run on both; a script copies my data across, keeping ids
- [x] GitHub Actions: every push runs the tests on SQLite and Postgres, and builds and lints the frontend
- [x] Hardening before going public: block private/internal addresses (SSRF), upload size limit, rate limiting, month boundary in India time
- [x] Security sweep before deploying: fixed a ReDoS, an unspoofable rate limit, http(s)-only links, strong key, docs switch, length limits; browser security headers for Vercel
- [x] Deploy: web app on Vercel, backend on Railway (trial, then free plan with $1 of credit a month), database on Neon; point the Shortcuts and the extension at it
- [x] Test the deployed version: phone on mobile data with the laptop off, laptop browser, extension, security spot checks
- [x] Live fixes: ↻ retries items without a price, a clearer "no price" reason for pages from the phone or extension, one log line per store page (no links, never the key)
- [ ] UI fixes found while testing it: add-box message, Try again on stuck rows, extension checks its settings (clearing the list on a rejected login came with Accounts; the key is no longer typed into the web app)
- [ ] Savana on the deployed version (blocked from Railway; parked for now)
- [ ] Tira support (tirabeauty.com and `trbt.ly` links)
- [ ] Myntra / Ajio / Meesho support
- [ ] Shopify cart import (Come Again charm bracelets)
- [ ] Rethink "Over budget" (each item on its own, or in priority order?)
- [ ] Flipkart MRP (the struck-through price)
- [x] Accounts: invite-only sign-up, email + password, own list and budget, device keys for the Shortcuts and extension, reset links, my existing list moved into my account
- [x] Per-person currency, country and time zone
- [ ] Warn when a store's currency isn't the person's (no conversion yet)

- [ ] Budget periods: choose weekly, monthly or yearly; see past periods with their budget and what I spent

**Parked ideas**
- Native Android app with Flutter (installs as an APK on Android; an iPhone build would need a Mac, so the iPhone gets the PWA)

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
- `feature/browser-extension`: agreed the popup's look in a mockup (six states), then built a Manifest V3 extension in plain JavaScript; the `409` reply now carries `link_id` for **Update price**. Ran the real extension in headless Chromium against the backend and a fake store before handing it over, which caught a settings-ordering bug. 49 tests passing
- Tried it on real pages: Amazon added from the laptop with no bot-check, plus Flipkart and Littlebox; Update price and Remove work. Fixed a folder that Windows had unzipped one level too deep

**2026-10-09**
- `feature/postgres`: portable SQL (`RETURNING id`, `DOUBLE PRECISION`), then a `DATABASE_URL` switch with a small wrapper so `services.py` didn't change; found the `%` placeholder trap in `LIKE 'http%'`. Every API test now runs on SQLite and Postgres
- Recovered a commit made on `main` by mistake (fast-forward onto the feature branch, reset `main`)
- Wrote `copy_to_postgres.py`; its test caught the id counter not moving after a copy, and then ids of deleted items being reused
- Found that my work laptop's Smart App Control blocks psycopg and a local Postgres install; added `--sql-out` (paste the copy into Neon's SQL Editor) and GitHub Actions, which runs all 85 tests with a real Postgres on every push. First green run
- Chose Railway's free plan for the backend after measuring the server: about 58 MB of RAM and 2 ms of CPU per `/summary`, roughly $0.60–0.70 of the $1 monthly credit even if always on, with the database on Neon

**2026-10-11**
- Merged `feature/postgres` (PR #8) after the first green GitHub Actions run
- `feature/hardening`, one tested commit per step: SSRF block (public addresses only, every redirect checked, the checked address pinned against DNS rebinding); 5 MB upload limit in front of everything, found and fixed a chunked upload answering 400 instead of 413 by testing a real server; rate limiting (60/min, 10/min for page downloads, sliding window, 429 + `Retry-After`); "spent this month" follows `ONTRACK_TIMEZONE` (default `Asia/Kolkata`). 113 tests
- Decided that currency and country become per-person settings with Accounts, which also unlocks a trial for someone in the US
- Security sweep: found a ReDoS in the canonical-tag pattern (22 s on 21 KB; now 0.15 s on 5 MB), a way to dodge the rate limit through `X-Forwarded-For` (from a setting I'd planned to use), and pages planting `javascript:` links. Fixed those, plus a minimum key length, a switch for `/docs`, length limits and a refresh-upload limit. Added Vercel security headers and Railway's start settings to git. 123 tests
- Deployed: a Neon database in Singapore (my data copied in through the SQL Editor), the server on Railway and the web app on Vercel. Fixed Railway's root folder and config path, a trailing slash in the CORS setting, and found the account starts on a trial (Challenge 29). Production key, `ONTRACK_TRUST_PROXY=on`, `ONTRACK_DOCS=off`, no key in Vercel. The app loaded with my real list

**2026-10-12**
- Tested the deployed version end to end. Server: health, hidden docs, missing key refused, rate limit not fooled by fake `X-Forwarded-For` addresses (10 × 200, then 429), wrong key refused in the app
- Phone on mobile data with the laptop off: app from the home screen, Amazon share, Flipkart pasted (Railway can read it), Littlebox, Refresh OnTrack, ↻, add by hand, bought/undo/later/delete, budget. A stuck item added again filled the same row, no duplicate
- Laptop: the extension adds, updates prices and removes non-product pages on the live server; same list as the phone; the Alexa link is clean in Neon; the SSRF block refuses `169.254.169.254`; Railway usage half a cent
- Found: Savana blocks Railway (error 471), Tira's price isn't read, ↻ waits an hour on items without a price, and a list of small UI fixes (see *Found while using it*)
- `feature/live-fixes`: ↻ now retries items without a price instead of waiting an hour; pages from the phone or extension no longer blame JavaScript; every store page gets one log line (store, who downloaded it, result, reason, time), with a test that the key and full links never appear (Challenge 30). Savana parked. 131 tests

**2026-10-13**
- `feature/accounts`: invite-only accounts with email + password (scrypt). Logins and device keys are tokens in the same `X-API-Key` header (Safari blocks cookies between Vercel and Railway), stored only as hashes. The first account uses `ONTRACK_API_KEY` as its invite and is given the existing list and budget; the old key keeps working as the owner until the Shortcuts have device keys
- Every query in `services.py` now takes the user; someone else's item answers 404 on every route. Duplicate links are per person (a unique index on `user_id` + `url`); old databases are upgraded at start-up, with SQLite's table-rebuild recipe since it can't drop a rule
- Per-person currency, country and time zone: guessed from the device at sign-up, changeable in Account; prices show `₹1,23,456` or `$120.50`, and "this month" follows each person's calendar
- Web app: a sign-in screen (log in, sign up from an invite link, new password from a reset link) and an Account sheet (profile, device keys, people and invites, password, log out), in the same linen-and-cocoa design. A rejected login now clears the list and returns to sign-in
- 40 new tests (all fail on the old code), 171 in total on SQLite and Postgres 16; ran the whole flow in headless Chromium: owner sign-up, device key, invite, a US friend's own dollar list in dark mode

