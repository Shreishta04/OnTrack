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

**First time on a database:** tap *Have an invite? Create your account* and use `ONTRACK_API_KEY` from `backend/.env` as the invite code. That first account is the owner and gets everything already saved. Others join from an invite link made in **Account → People**.

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
2. On the phone, open the **Network** URL (`http://<laptop IP>:5173`) and, on the sign-in screen, open **Server** and set it to `http://<laptop IP>:8000` (later: **Account → Server address**). Port **5173** is the app (Vite); port **8000** is the data (uvicorn), so the server setting always ends in `:8000`. Settings are saved per address, so a new network (new IP) means entering it again.
3. First time on a network: Windows must treat the Wi-Fi as **Private**, and allow ports 5173 and 8000 (see the main README, "Using the iPhone Shortcut with the local server").

The first load on the phone can be slow in development, because Vite sends the app as many small files. A production build (`npm run build`) doesn't have this.

### Development settings: `.env.local`

Create `frontend/.env.local` (git-ignored, never committed):

```
VITE_API_URL=http://127.0.0.1:8000
```

Only variables starting with `VITE_` reach the code. Vite copies them **into the built app**, so never put a key here. A server address saved in the app (sign-in screen → *Server*, or **Account**) is stored in the browser and takes priority over `.env.local`. An old `VITE_API_KEY` line isn't read any more and can go.

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
├── format.ts          store names ("Amazon"), short dates ("5 Oct"), plain-words errors and tips
├── index.css          design tokens (light + dark), layout and component styles
├── hooks/
│   ├── useTheme.ts    light / dark / follow the device, remembered in the browser
│   └── usePhone.ts    phone-sized screen (the + button layout)? opened from the home screen?
└── components/
    ├── BudgetCard.tsx     big "left" number, bar, totals, in-card budget editing
    ├── Price.tsx          every amount, drawn the same way, in the person's currency
    ├── AddLink.tsx        paste-a-link box
    ├── AddByHand.tsx      name, optional link and price, for anything a store won't let us read
    ├── AddSheet.tsx       the phone's add sheet: both add forms, behind the + button
    ├── SelectionBar.tsx   ticked items: live total, left / over, Mark bought · Move to Later · Park the rest · Back to wish list
    ├── Tabs.tsx           Wish list · Later · Bought · All, sliding underline
    ├── ItemList.tsx       the rows for the current tab, or an empty message
    ├── ItemRow.tsx        one expandable row: details, why it's stuck, actions
    ├── Thumb.tsx          product photo, or the name's first letter
    ├── AuthScreen.tsx     log in · sign up with an invite · new password from a reset link
    ├── AccountSheet.tsx   profile (currency, country, time zone), device keys, people + invites (owner), password, log out
    └── Icons.tsx          small line icons (refresh, moon, sun, sliders, close)
```

**Signing in:** `App` shows `AuthScreen` when this browser has no login token, or when the address has `?invite=…` or `?reset=…` (the links made in Account). After signing in, the code is removed from the address bar so a reload doesn't reuse it. Any `401` later (logged out elsewhere, password changed) makes `api.ts` forget the token and fire a `ontrack:signed-out` event, and `App` goes back to the sign-in screen, clearing the list from view.

**How data flows:** `App` loads `/summary` once and keeps it in state. It passes the data **down** to components as props, and components report button presses back **up** through functions (`onAction`, `onAdded`, `onBudgetSaved`). After every change, `App` reloads `/summary`, so the server stays the single source of truth for budgets, totals and what fits. It also reloads when the page becomes visible again (`visibilitychange`), so changes made elsewhere, like the iPhone's Refresh OnTrack, show up without a manual reload.

## Phone app (PWA)

- `public/manifest.webmanifest`: name, icons, `display: standalone` (full screen from the home screen), and `share_target`, which puts the installed app in Android's share menu (shares arrive as `/?title=&text=&url=`, read in `App.tsx`).
- `public/sw.js`: the service worker. The page network-first, `/assets/…` from its saved copy, everything else (including the server, fonts) untouched. Registered only in the built app, so `npm run dev` never serves stale files. To try it locally: `npm run build` then `npm run preview` (http://localhost:4173, add it to `ONTRACK_CORS_ORIGINS`).
- The offline list is saved by `api.ts` (`save` / `saved`), not the service worker, and deleted on log out.
- Phone layout below 860px wide (`usePhone`), the same width at which the two columns stack.
- `index.css` uses `env(safe-area-inset-…)` with `viewport-fit=cover`, so nothing hides under the notch or home bar. Text boxes are 16px: smaller makes iPhone Safari zoom on every tap.
- If an installed app seems stuck on an old version: close it fully and open it again while online (the page is fetched fresh each time; the old files are dropped).

## Conventions

- **File names:** components are PascalCase (`ItemRow.tsx`); everything else is lowercase (`api.ts`). Imports must match the exact capitals: Windows ignores them, but deployment builds run on Linux, which doesn't.
- **Colours:** never written in components. Every colour is a CSS variable in `index.css` (`--accent`, `--warn`, …), defined once for light and once for dark.
- **Money:** always shown with `<Price amount={…} />`, which draws the person's currency sign small and the digits tabular. For a sign elsewhere (a label, an input), use `useMoney().symbol`. Rupees and yen are whole numbers; other currencies keep their cents when there are some.
- **Forms:** every form handler starts with `e.preventDefault()`, so the browser doesn't reload the page.
- **Typed amounts:** forms accept what people actually type ("1,500", "₹1299", "$12.50"): keep only digits and the dot, then check with `Number.isFinite`.
- **Errors shown to people:** never raw library text. `problemText()` in `format.ts` turns stored errors into a sentence, and `api.ts` does the same for request errors.

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