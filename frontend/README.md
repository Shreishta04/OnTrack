# OnTrack web app

The browser app for OnTrack: a sign-in screen, then your own budget card, wish list in tabs, and buttons to buy, park or delete items, in your own currency. It talks to the FastAPI backend in `../backend`. For the full story (why the project exists, the backend, the iPhone Shortcuts), see the [main README](../README.md).

Built with **React + TypeScript**, bundled with **Vite**, styled with plain CSS.

## Run it

Requires Node.js 18+ (LTS) and the backend running (`uvicorn main:app --reload` in `../backend`).

```powershell
npm install        # first time only: downloads React, Vite, TypeScript into node_modules
npm run dev        # starts the app at http://localhost:5173
```

Open **http://localhost:5173**. Use `localhost`, not `127.0.0.1`: the backend's CORS setting only allows `localhost`.

**First time on a database:** tap *Have an invite? Create your account* and use `ONTRACK_API_KEY` from `backend/.env` as the invite code. That first account is the owner and gets everything already saved. Others join from an invite link made in **Settings → People and invites**.

### Deployed version

The live app is at **https://on-track-eta.vercel.app**, built by Vercel from this folder on every merge into `main`. Vercel only needs one environment variable, `VITE_API_URL` (the Railway server's address); no key is ever put in Vercel, because `VITE_` values end up in files anyone can download. Each browser gets its own token when you log in. `vercel.json` here adds the security headers. Details in the main README's *Deployed* section.

### On the phone (same Wi-Fi)

```powershell
npm run dev -- --host       # also listens on the Wi-Fi address; prints a "Network:" URL
```

The lone `--` passes `--host` through npm to Vite. Then:

1. Add the phone's view of the app to the backend's CORS list in `backend/.env`, and restart uvicorn (started with `--host 0.0.0.0`):
   ```
   ONTRACK_CORS_ORIGINS=http://localhost:5173,http://<laptop IP>:5173
   ```
2. On the phone, open the **Network** URL (`http://<laptop IP>:5173`) and, on the sign-in screen, open **Server** and set it to `http://<laptop IP>:8000` (later: **Settings → Server address**, at the bottom). Port **5173** is the app (Vite); port **8000** is the data (uvicorn), so the server setting always ends in `:8000`. Settings are saved per address, so a new network (new IP) means entering it again.
3. First time on a network: Windows must treat the Wi-Fi as **Private**, and allow ports 5173 and 8000 (see the main README, "Using the iPhone Shortcut with the local server").

The first load on the phone can be slow in development, because Vite sends the app as many small files. A production build (`npm run build`) doesn't have this.

### Development settings: `.env.local`

Create `frontend/.env.local` (git-ignored, never committed):

```
VITE_API_URL=http://127.0.0.1:8000
```

Only variables starting with `VITE_` reach the code. Vite copies them **into the built app**, so never put a key here. A server address saved in the app (sign-in screen → *Server*, or **Settings**) is stored in the browser and takes priority over `.env.local`. An old `VITE_API_KEY` line isn't read any more and can go.

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Development server with instant reload on save |
| `npm run build` | Type-checks everything, then builds the production files into `dist/` |
| `npm run preview` | Serves the built `dist/` locally, to check a build |
| `npm run lint` | Oxlint: finds likely mistakes without running the code |

`npm run build` is also the best final check before a commit: it fails on type errors and on unused variables, the same as a deployment would.

## How the code is organised

```
src/
├── main.tsx           entry point: draws <App /> into index.html's #root; starts the service worker (built app only)
├── App.tsx            sign-in screen or the list; loads /summary, owns the current tab, handles button presses
├── api.ts             every request to the backend (login token, JSON, friendly errors); log in / sign up / log out
├── money.tsx          the person's currency: symbol and digit grouping, shared through a React context
├── places.ts          countries, currencies, time zones, and first guesses from the device
├── types.ts           TypeScript shapes of the data the backend sends
├── alerts.ts          "Turn on" alerts for this phone: asks permission, gets the phone's Firebase token (Firebase's code loads only then), sends it to the server
├── report.ts          problems the app runs into go to the server's app.log; friendly() turns any error into a sentence for the screen
├── device.ts          which device (iPhone / Android / computer), installed or not, Android's install offer, the Connect link
├── format.ts          store names ("Amazon", "Victoria's Secret"), "Amazon item" for unnamed items, short dates ("5 Oct"), plain-words errors and tips, period dates (the server's reset rule, copied)
├── sort.ts            the four sort orders (newest, oldest, price both ways), remembered on this device
├── tabs.ts            the four tabs, left to right (shared by the tabs, swiping and the slide direction)
├── index.css          design tokens (light + dark), layout and component styles
├── hooks/
│   ├── useTheme.ts    light / dark / follow the device, remembered in the browser
│   ├── usePhone.ts    phone-sized screen (the + button layout)? opened from the home screen?
│   ├── useNewVersion.ts  is a newer build live? (shows the Update line)
│   ├── useSwipe.ts    a flick left or right on the list changes tab (ignores edge swipes, scrolling, slow drags)
│   ├── useNav.ts      which page (list, /settings or /analytics) and which sheet is open, kept in history so Back works
│   └── useEdgeBack.ts the iPhone home-screen app's swipe-from-the-left-edge Back (Settings, Analytics)
└── components/
    ├── BudgetCard.tsx     the espresso card: what's left, the ring (spent / planned / left), the totals; tap to edit
    ├── BudgetEditor.tsx   the budget form: amount, Every / Just this period, the 1–31 reset-day calendar and a preview of the dates
    ├── BudgetSheet.tsx    the sheet that opens when you tap the budget card or "Set it" on the reminder bar
    ├── BudgetSetup.tsx    "Set up your budget": shown after logging in while the budget or reset day is missing
    ├── AnalyticsPage.tsx  /analytics: this period, six periods as bars against the budget, past periods, spend by store
    ├── Price.tsx          every amount, drawn the same way, in the person's currency
    ├── SetupPage.tsx      /setup: Set up this phone (different steps per device)
    ├── CrashScreen.tsx    if a screen crashes: "Something went wrong · Reload OnTrack" (reported, with a ref) instead of a blank page
    ├── TrashPage.tsx      /trash: Recently deleted (Restore, days left, Empty now)
    ├── UndoBar.tsx        the bar after Delete, a move or Mark bought: what happened + Undo, for 6 seconds
    ├── AddLink.tsx        paste-a-link box (the server downloads the page; on an iPhone, sharing with the Shortcut is better)
    ├── AddByHand.tsx      name, optional link and price, for anything a store won't let us read
    ├── AddSheet.tsx       the phone's add sheet: both add forms, behind the + button
    ├── SelectionBar.tsx   ticked items on any tab: live total, left / over (Wish list, Later), the right buttons per tab, "are you sure?" for 5+ bought, Delete on every tab (always asks)
    ├── ListTools.tsx      the row above the list: Select all / Clear all, and the sort menu
    ├── Tabs.tsx           Wish list · Later · Bought · All, with a pill that measures and follows the active tab
    ├── ItemList.tsx       the rows for the current tab, or an empty message; on Bought, a heading per budget period with its total
    ├── ItemRow.tsx        one expandable row: details, why it's stuck, a price box when it needs one, Edit (name, note, price), actions
    ├── Thumb.tsx          product photo, or the name's first letter
    ├── AuthScreen.tsx     log in · sign up with an invite · new password from a reset link
    ├── SettingsPage.tsx   /settings: profile, appearance, notifications (Turn on, four switches, Send a test), budget and reset day, region, password, device keys, people (owner: invites, reset links, Remove / Give access back), log out
    └── Icons.tsx          small line icons (search, gear, back, refresh, sun, moon, close, chevron, …)
```

**Signing in:** `App` shows `AuthScreen` when this browser has no login token, or when the address has `?invite=…` or `?reset=…` (the links made in Settings). After signing in, the code is removed from the address bar so a reload doesn't reuse it. Any `401` later (logged out elsewhere, password changed) makes `api.ts` forget the token and fire a `ontrack:signed-out` event, and `App` goes back to the sign-in screen, clearing the list from view.

**How data flows:** `App` loads `/summary` once and keeps it in state. It passes the data **down** to components as props, and components report button presses back **up** through functions (`onAction`, `onAdded`, `onBudgetSaved`). After every change, `App` reloads `/summary`, so the server stays the single source of truth for budgets, totals and what fits. It also reloads when the page becomes visible again (`visibilitychange`), so changes made elsewhere, like the iPhone's Refresh OnTrack, show up without a manual reload.

**Budget periods:** `/summary` has a `period` (dates, days left, this period's budget, the default and the reset day). It's optional in `types.ts`, because for a minute after merging, Vercel's new app can talk to Railway's old server. Without it there's no setup screen, reminder bar or chart icon; with it, `App` shows `BudgetSetup` until the budget and reset day are set or *Skip for now* is pressed (remembered in `localStorage` until the next login), then a reminder bar until both are set. The editor's preview uses `nextResetAfter()`, a copy of the server's rule, so it shows the same dates the server will save.

**Editing goes through the row's actions:** a row action is a move (`'later'`), `'delete'`, or `{ edit: {...} }` (Edit and the price box), so `App.handleAction` is the one place that talks to the server for a row. Only the fields that changed are sent.

**Sorting and ticking happen in the browser:** `/summary` already holds every item, so `sortItems()` reorders a copy for the current tab, and ticks are just a set of ids in `App`'s state (a "what if"). Only the bar's buttons talk to the server: one `PATCH /items/{id}` per item, skipping items already on the target list, then one reload.

## Pages and the Back button

There are five pages, `/` (the list), `/settings`, `/analytics`, `/setup` and `/trash`, plus things that open on top: the add sheet, the budget sheet and the search bar. `useNav` keeps all of them in the browser's history:

- Opening a page or a sheet adds one history entry (`history.pushState`); closing it (✕, Save, Escape) goes back one entry, exactly what the phone's Back does. So the phone's Back button or swipe closes a sheet, and returns from Settings or Analytics to the list.
- The pushes happen in click handlers, never in effects: React's development mode runs effects twice, which would push two entries.
- Opened straight on `/settings` or `/analytics` (a refresh, a bookmark), there's no entry to go back to, so Back swaps the entry for the list instead of leaving the app.
- `vercel.json` sends every address to `index.html`, so `/settings` and `/analytics` load on a refresh; Vite's dev server and `npm run preview` already do this.
- iPhone's home-screen app has no back swipe, so `SettingsPage` and `AnalyticsPage` add a left-edge swipe (`useEdgeBack`) when `navigator.standalone` is true (never in Safari, which has its own).

## Phone app (PWA)

- `public/manifest.webmanifest`: name, icons, `display: standalone` (full screen from the home screen), and `share_target`, which puts the installed app in Android's share menu (shares arrive as `/?title=&text=&url=`, read in `App.tsx`).
- `public/sw.js`: the service worker. The page from its saved copy first (a fresh one fetched in the background), `/assets/…` from its saved copy, everything else (including the server, fonts) untouched. Registered only in the built app, so `npm run dev` never serves stale files. To try it locally: `npm run build` then `npm run preview` (http://localhost:4173, add it to `ONTRACK_CORS_ORIGINS`).
- Notifications: `sw.js` also has a `push` handler (the server's message, through Firebase, becomes a notification; every push shows one, or iPhones stop delivering) and `notificationclick` (focus OnTrack, or open it). `alerts.ts` hands Firebase **our** service worker, so there's no separate `firebase-messaging-sw.js`. On an iPhone this only works in the Home Screen app (iOS 16.4+), and permission is asked straight from the *Turn on* tap. The Firebase setup (public) comes from the server's `GET /notifications`, so a new Firebase project needs no rebuild.
- The offline list is saved by `api.ts` (`save` / `saved`), not the service worker, and deleted on log out.
- Phone layout below 860px wide (`usePhone`), the same width at which the two columns stack.
- `index.css` uses `env(safe-area-inset-…)` with `viewport-fit=cover`, so nothing hides under the notch or home bar. Text boxes are 16px: smaller makes iPhone Safari zoom on every tap.
- New versions: `useNewVersion` compares the running `/assets/index-….js` name with the one Vercel serves, when the app comes back into view and every 15 minutes, and App shows "A new version of OnTrack is ready · Update". Without it, an installed app (only paused in the background) kept the old page until swiped away.
- Offline: the offline line is a button (Try again), and the app retries every 20 seconds while offline.

## Conventions

- **File names:** components are PascalCase (`ItemRow.tsx`); everything else is lowercase (`api.ts`). Imports must match the exact capitals: Windows ignores them, but deployment builds run on Linux, which doesn't.
- **Colours:** never written in components. Every colour is a CSS variable in `index.css` (`--accent`, `--warn`, …), defined once for light and once for dark.
- **Money:** always shown with `<Price amount={…} />`, which draws the person's currency sign small and the digits tabular. For a sign elsewhere (a label, an input), use `useMoney().symbol`. Rupees and yen are whole numbers; other currencies keep their cents when there are some.
- **Forms:** every form handler starts with `e.preventDefault()`, so the browser doesn't reload the page.
- **Typed amounts:** forms accept what people actually type ("1,500", "₹1299", "$12.50"): keep only digits and the dot, then check with `Number.isFinite`.
- **Errors shown to people:** never raw text. The server's answers are plain sentences (an `ApiError`, sometimes ending in a ref code); show any caught error with `friendly('Where', err)` from `report.ts`, which also reports anything that isn't the server's sentence to `app.log`. `problemText()` in `format.ts` turns stored link errors into a sentence.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "Can't reach the server…" | uvicorn isn't running, or the app was opened at `127.0.0.1:5173` | Start uvicorn; open `localhost:5173` |
| Back on the sign-in screen unexpectedly | This login ended (logged out, password changed or reset, or the database was replaced) | Log in again |
| "For the first account, the invite code is the server's ONTRACK_API_KEY" | No accounts yet on this database | Use the key from `backend/.env` (or Railway) as the invite code |
| A saved change doesn't appear | Windows locked the file and Vite stopped watching it (`EBUSY` in the terminal) | Restart `npm run dev`, then Ctrl+Shift+R |
| Red underline on an import that exists | VS Code's TypeScript checker is out of date | Ctrl+Shift+P → *TypeScript: Restart TS Server* |
| `npm` says it can't find `package.json` | Run from the wrong folder | `cd frontend` first |
| Phone: "Safari can't open the page… stopped responding" | Vite started without `--host`, or Windows Firewall blocking | `npm run dev -- --host`; Wi-Fi set to *Private*; firewall rule for ports 5173 and 8000 |
| Phone: page opens but "Can't reach the server" | Phone's address missing from `ONTRACK_CORS_ORIGINS`, uvicorn not restarted, or wrong server address | Fix `backend/.env`, restart uvicorn, set the server (sign-in screen → *Server*) to `http://<laptop IP>:8000` |
| Phone: "Can't reach the server at http://127.0.0.1:8000" | New network, so new address: Safari has no saved settings for it and the app used its laptop-only default (`127.0.0.1` means *this device*) | Set the server to `http://<laptop IP>:8000` |
| Phone: first load takes ages, then everything arrives at once | Development mode sends many small files over Wi-Fi | Wait for the first load, or check a production build (`npm run build` then `npm run preview -- --host`) |