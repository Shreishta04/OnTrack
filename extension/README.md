# OnTrack browser extension

Adds the product you're looking at to your OnTrack wish list, from Chrome or Edge. It sends the page **your browser already loaded** to the OnTrack server, the same way the iPhone Shortcut does, so the server never has to visit the store itself (and Amazon's bot-check never sees it). For the full story, see the [main README](../README.md).

Plain JavaScript, no build step: edit a file, then reload the extension.

## Install (once)

1. Open `chrome://extensions` (Edge: `edge://extensions`) and turn on **Developer mode**.
2. Click **Load unpacked** and pick this `extension` folder (the one that contains `manifest.json`).
3. Pin it: the puzzle-piece icon in the toolbar → 📌 next to OnTrack.
4. Click the OnTrack icon. The first time it asks for:

| Setting | Deployed | Local development |
|---|---|---|
| Server | `https://ontrack-production-8f1d.up.railway.app` | `http://localhost:8000` (where uvicorn runs) |
| API key | a **device key**: web app → Account → Devices → New key (e.g. "Laptop extension"), shown once | the same, from the local web app |
| App address | `https://on-track-eta.vercel.app` | `http://localhost:5173` (opened by "Open OnTrack ↗") |

The sliders button in the popup changes them later. A server other than `localhost` / `127.0.0.1` asks for permission once, when you save it; it then appears under the extension's **Site access** in `chrome://extensions`. When switching, clear each field completely (Ctrl+A, Delete) before pasting: the popup saves whatever is in the box, and a leftover `73` from `:5173` once made the app address `…vercel.app73`.

## Use

| You're on… | The popup offers | What it does |
|---|---|---|
| a product page | **Add to OnTrack** | Sends the page to `POST /items/from-html`, then shows price, "Fits budget" and what's left |
| a product already saved | **Update price** | Sends the page to `POST /links/{link_id}/from-html` (the `409` reply names the link) |
| a page with no price (a category, a search) | **Remove it** | The item was saved as *Needs a price*; this deletes it |

## How the code is organised

```
extension/
├── manifest.json   name, icons, permissions
├── popup.html      the window that opens from the toolbar icon
├── popup.css       the web app's colours, light and dark
├── popup.js        reads the page, talks to the server, shows the result; settings
└── icons/          16, 32, 48 and 128 px
```

**Permissions, and why:**
- `activeTab` + `scripting`: read the **current tab only**, and only when you click the icon (`document.documentElement.outerHTML`, the page as you see it).
- `storage`: remember server, device key and app address.
- `host_permissions` for `localhost` / `127.0.0.1`: talk to the laptop's server. Extensions with host permissions aren't held to CORS, so the server's CORS list doesn't need the extension.

**Conventions:**
- The page is sent as a **file** (`Blob`), never a text field: form fields are capped at 1 MB and Amazon pages are bigger.
- Anything that came from the server is put on screen with `textContent`, never `innerHTML`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "Manifest file is missing or unreadable" | The folder you picked doesn't contain `manifest.json` directly (often unzipped one level too deep) | Pick the folder with `manifest.json` in it |
| "Can't reach the server…" | uvicorn isn't running, or the server setting is wrong | Start uvicorn; check the sliders → Server |
| "The API key was rejected" | The device key was removed in Account, mistyped, or the database was replaced | Make a new key in Account → Devices and paste it in settings |
| A change to the code doesn't show | Chrome still runs the old version | ↻ on the extension's card in `chrome://extensions` |
| "Open a product page first" | The tab is a browser page (`chrome://…`, new tab) | Open a store page, then click the icon |
