# OnTrack web app

The browser app for OnTrack: a budget card, your wish list in tabs, and buttons to buy, park or delete items. It talks to the FastAPI backend in `../backend`. For the full story (why the project exists, the backend, the iPhone Shortcuts), see the [main README](../README.md).

Built with **React + TypeScript**, bundled with **Vite**, styled with plain CSS.

## Run it

Requires Node.js 18+ (LTS) and the backend running (`uvicorn main:app --reload` in `../backend`).

```powershell
npm install        # first time only: downloads React, Vite, TypeScript into node_modules
npm run dev        # starts the app at http://localhost:5173
```

Open **http://localhost:5173**. Use `localhost`, not `127.0.0.1`: the backend's CORS setting only allows `localhost`.

### On the phone (same Wi-Fi)

```powershell
npm run dev -- --host       # also listens on the Wi-Fi address; prints a "Network:" URL
```

The lone `--` passes `--host` through npm to Vite. Then:

1. Add the phone's view of the app to the backend's CORS list in `backend/.env`, and restart uvicorn (started with `--host 0.0.0.0`):
   ```
   ONTRACK_CORS_ORIGINS=http://localhost:5173,http://<laptop IP>:5173
   ```
2. On the phone, open the **Network** URL (`http://<laptop IP>:5173`) and set **Settings → server** to `http://<laptop IP>:8000`.
3. First time on a network: Windows must treat the Wi-Fi as **Private**, and allow ports 5173 and 8000 (see the main README, "Using the iPhone Shortcut with the local server").

The first load on the phone can be slow in development, because Vite sends the app as many small files. A production build (`npm run build`) doesn't have this.

### Development settings: `.env.local`

Create `frontend/.env.local` (git-ignored, never committed):

```
VITE_API_URL=http://127.0.0.1:8000
VITE_API_KEY=<the same key as backend/.env>
```

Only variables starting with `VITE_` reach the code. Vite copies them **into the built app**, so this file is for development only, never for a deployment. Anything saved in the app's **Settings** panel (API key, server address) is stored in the browser and takes priority over `.env.local`.

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
├── main.tsx           entry point: draws <App /> into index.html's #root
├── App.tsx            loads /summary, owns the current tab, handles button presses
├── api.ts             every request to the backend (key, JSON, friendly errors)
├── types.ts           TypeScript shapes of the data the backend sends
├── format.ts          store names ("Amazon") and short dates ("5 Oct")
├── index.css          design tokens (light + dark), layout and component styles
├── hooks/
│   └── useTheme.ts    light / dark / follow the device, remembered in the browser
└── components/
    ├── BudgetCard.tsx     big "left" number, bar, totals, in-card budget editing
    ├── Price.tsx          every ₹ amount, drawn the same way
    ├── AddLink.tsx        paste-a-link box
    ├── Tabs.tsx           Wish list · Later · Bought · All, sliding underline
    ├── ItemList.tsx       the rows for the current tab, or an empty message
    ├── ItemRow.tsx        one expandable row: details and actions
    ├── Thumb.tsx          product photo, or the name's first letter
    ├── SettingsSheet.tsx  API key and server address
    └── Icons.tsx          small line icons
```

**How data flows:** `App` loads `/summary` once and keeps it in state. It passes the data **down** to components as props, and components report button presses back **up** through functions (`onAction`, `onAdded`, `onBudgetSaved`). After every change, `App` reloads `/summary`, so the server stays the single source of truth for budgets, totals and what fits.

## Conventions

- **File names:** components are PascalCase (`ItemRow.tsx`); everything else is lowercase (`api.ts`). Imports must match the exact capitals: Windows ignores them, but deployment builds run on Linux, which doesn't.
- **Colours:** never written in components. Every colour is a CSS variable in `index.css` (`--accent`, `--warn`, …), defined once for light and once for dark.
- **Money:** always shown with `<Price amount={…} />`, which draws the small ₹ and tabular digits.
- **Forms:** every form handler starts with `e.preventDefault()`, so the browser doesn't reload the page.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "Can't reach the server…" | uvicorn isn't running, or the app was opened at `127.0.0.1:5173` | Start uvicorn; open `localhost:5173` |
| "The API key was rejected" | Key in `.env.local` or Settings doesn't match `backend/.env` | Fix the key, restart `npm run dev` |
| A saved change doesn't appear | Windows locked the file and Vite stopped watching it (`EBUSY` in the terminal) | Restart `npm run dev`, then Ctrl+Shift+R |
| Red underline on an import that exists | VS Code's TypeScript checker is out of date | Ctrl+Shift+P → *TypeScript: Restart TS Server* |
| `npm` says it can't find `package.json` | Run from the wrong folder | `cd frontend` first |
| Phone: "Safari can't open the page… stopped responding" | Vite started without `--host`, or Windows Firewall blocking | `npm run dev -- --host`; Wi-Fi set to *Private*; firewall rule for ports 5173 and 8000 |
| Phone: page opens but "Can't reach the server" | Phone's address missing from `ONTRACK_CORS_ORIGINS`, uvicorn not restarted, or wrong server in Settings | Fix `backend/.env`, restart uvicorn, set Settings → server to `http://<laptop IP>:8000` |
| Phone: first load takes ages, then everything arrives at once | Development mode sends many small files over Wi-Fi | Wait for the first load, or check a production build (`npm run build` then `npm run preview -- --host`) |