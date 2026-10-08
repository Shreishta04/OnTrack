// OnTrack browser extension: the popup that opens when you click the icon.
//
// It reads the page in the current tab (exactly as you see it) and sends it
// to the OnTrack server, the same way the iPhone Shortcut does. The server
// never has to visit the store itself, so Amazon's bot-check never sees it.

const $ = (id) => document.getElementById(id)

const DEFAULTS = { server: 'http://localhost:8000', apiKey: '', app: 'http://localhost:5173' }
let settings = { ...DEFAULTS }
let tab = null // the browser tab we're adding from

// ------------------------------------------------------------- small helpers

// "40990" → "₹40,990", drawn like the web app (small ₹, tabular digits).
function priceNode(amount) {
  const span = document.createElement('span')
  span.className = 'num'
  const cur = document.createElement('span')
  cur.className = 'cur'
  cur.textContent = '₹'
  span.append(cur, Math.round(amount).toLocaleString('en-IN'))
  return span
}

function setNote(text, warn = false) {
  $('note').hidden = !text
  $('note').textContent = text || ''
  $('note').classList.toggle('is-warn', warn)
}

// Build a line from text and nodes, e.g. ['Saved · ', priceNode(999)].
function setMeta(parts) {
  $('meta').replaceChildren(...parts)
}

function showCard(name, image, store) {
  $('name').textContent = name
  const thumb = $('thumb')
  thumb.replaceChildren()
  if (image) {
    const img = document.createElement('img')
    img.src = image
    img.alt = ''
    img.referrerPolicy = 'no-referrer'
    img.onerror = () => (thumb.textContent = (store || name).charAt(0).toUpperCase())
    thumb.append(img)
  } else {
    thumb.textContent = (store || name).charAt(0).toUpperCase()
  }
}

// One button, or two. Each is {label, onClick}; null hides it.
function setButtons(primary, secondary = null) {
  for (const [el, spec] of [[$('primary'), primary], [$('secondary'), secondary]]) {
    el.hidden = !spec
    el.disabled = false
    if (spec) {
      el.textContent = spec.label
      el.onclick = spec.onClick
    }
  }
}

function busy(label) {
  $('primary').disabled = true
  $('primary').textContent = label
  $('secondary').hidden = true
}

// ------------------------------------------------------------- talking to the server

// Every request: add the key, read the JSON, turn failures into sentences.
// Returns {status, body} so callers can treat 409 ("already saved") as normal.
async function api(path, options = {}) {
  let response
  try {
    response = await fetch(settings.server + path, {
      ...options,
      headers: { 'X-API-Key': settings.apiKey, ...options.headers },
    })
  } catch {
    throw new Error(`Can't reach the server at ${settings.server}. Is uvicorn running?`)
  }
  if (response.status === 401) throw new Error('The API key was rejected. Check it in Settings.')
  if (response.status === 204) return { status: 204, body: null }
  const body = await response.json().catch(() => null)
  if (!response.ok && response.status !== 409) {
    throw new Error((body && typeof body.detail === 'string' && body.detail) || `Request failed (${response.status})`)
  }
  return { status: response.status, body }
}

// The page exactly as the browser shows it now (prices that load late included).
async function readPage() {
  const [result] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => ({ url: location.href, html: document.documentElement.outerHTML }),
  })
  return result.result
}

// Send the page as a FILE, like the Shortcut: form fields are capped at 1 MB,
// and an Amazon page is often bigger.
function pageForm(page, withUrl) {
  const form = new FormData()
  if (withUrl) form.append('url', page.url)
  form.append('html', new Blob([page.html], { type: 'text/html' }), 'page.html')
  return form
}

// ------------------------------------------------------------- what the buttons do

async function add() {
  busy('Adding…')
  setNote('')
  try {
    const page = await readPage()
    const { status, body } = await api('/items/from-html', { method: 'POST', body: pageForm(page, true) })
    if (status === 409) return showAlreadySaved(body.item_id, body.link_id, page)
    await showAdded(body)
  } catch (err) {
    setNote(err.message, true)
    setButtons({ label: 'Try again', onClick: add })
  }
}

async function showAdded(item) {
  const store = new URL(tab.url).hostname.replace(/^www\./, '')
  showCard(item.name, item.image, store)

  if (item.needs_price) {
    const reason = item.links.find((l) => l.last_error)?.last_error
    setMeta([store])
    setNote(`Saved, but no price found${reason ? `: ${reason}` : '.'} Open the exact product and try again, or remove it.`, true)
    setButtons({ label: 'Remove it', onClick: () => remove(item.id) }, { label: 'Open OnTrack ↗', onClick: openApp })
    return
  }

  // The budget note needs /summary (it knows what fits and what's left).
  setMeta([priceNode(item.price)])
  try {
    const { body: summary } = await api('/summary')
    const row = summary.items.find((i) => i.id === item.id)
    if (row && row.fits_budget != null) {
      const badge = document.createElement('span')
      badge.className = row.fits_budget ? 'good' : 'warn'
      badge.textContent = row.fits_budget ? 'Fits budget' : 'Over budget'
      setMeta([priceNode(item.price), ' · ', badge])
    }
    if (summary.remaining != null) {
      const left = summary.remaining >= 0
        ? `₹${Math.round(summary.remaining).toLocaleString('en-IN')} left after it`
        : `₹${Math.round(-summary.remaining).toLocaleString('en-IN')} over budget`
      setNote(`Added to your wish list · ${left}`)
    } else {
      setNote('Added to your wish list.')
    }
  } catch {
    setNote('Added to your wish list.')
  }
  setButtons({ label: 'Open OnTrack ↗', onClick: openApp })
  $('primary').className = 'btn btn-secondary'
}

async function showAlreadySaved(itemId, linkId, page) {
  try {
    const { body: item } = await api(`/items/${itemId}`)
    showCard(item.name, item.image, new URL(tab.url).hostname)
    setMeta(item.price != null ? ['Saved · ', priceNode(item.price)] : ['Saved · no price yet'])
  } catch {
    // The card keeps the tab's title; that's fine.
  }
  setNote('Already on your list. Update its price from this page?')
  setButtons({ label: 'Update price', onClick: () => updatePrice(linkId, page) }, { label: 'Open OnTrack ↗', onClick: openApp })
}

async function updatePrice(linkId, page) {
  busy('Updating…')
  try {
    const { body: r } = await api(`/links/${linkId}/from-html`, { method: 'POST', body: pageForm(page, false) })
    if (!r.ok) {
      setNote(`Couldn't read a price from this page: ${r.error}`, true)
    } else if (r.old_price != null && r.new_price !== r.old_price) {
      const old = Math.round(r.old_price).toLocaleString('en-IN')
      const now = Math.round(r.new_price).toLocaleString('en-IN')
      setNote(`Price updated: ₹${old} → ₹${now}${r.new_price < r.old_price ? ' 🎉' : ''}`)
    } else {
      setNote(`Checked: still ₹${Math.round(r.new_price).toLocaleString('en-IN')}.`)
    }
    if (r.ok) setMeta(['Saved · ', priceNode(r.new_price)])
  } catch (err) {
    setNote(err.message, true)
  }
  setButtons({ label: 'Open OnTrack ↗', onClick: openApp })
  $('primary').className = 'btn btn-secondary'
}

async function remove(itemId) {
  busy('Removing…')
  try {
    await api(`/items/${itemId}`, { method: 'DELETE' })
    setNote('Removed.')
    setButtons(null)
  } catch (err) {
    setNote(err.message, true)
    setButtons({ label: 'Remove it', onClick: () => remove(itemId) })
  }
}

function openApp() {
  chrome.tabs.create({ url: settings.app || DEFAULTS.app })
  window.close()
}

// ------------------------------------------------------------- settings

function showSettings(show) {
  $('settings').hidden = !show
  $('main').hidden = show
  if (show) {
    $('server').value = settings.server
    $('api-key').value = settings.apiKey
    $('app').value = settings.app
  }
}

$('settings-btn').onclick = () => showSettings($('settings').hidden)

$('settings').onsubmit = async (e) => {
  e.preventDefault() // stop the popup reloading, which forms do by default
  const server = $('server').value.trim().replace(/\/+$/, '')
  const app = ($('app').value.trim() || DEFAULTS.app).replace(/\/+$/, '')

  // localhost and 127.0.0.1 are allowed in manifest.json; any other server
  // (a Wi-Fi address, later the deployed one) needs your OK once.
  const origin = new URL(server).origin + '/*'
  const granted = await chrome.permissions.request({ origins: [origin] }).catch(() => false)
  if (!granted && !/^http:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/.test(server)) {
    $('settings-note').textContent = 'OnTrack needs permission to talk to that server.'
    $('settings-note').classList.add('is-warn')
    return
  }

  settings = { server, apiKey: $('api-key').value.trim(), app }
  await chrome.storage.local.set(settings)
  showSettings(false)
  init()
}

// ------------------------------------------------------------- opening the popup

function start() {
  showCard(tab.title || 'This page', null, new URL(tab.url).hostname.replace(/^www\./, ''))
  setMeta([new URL(tab.url).hostname.replace(/^www\./, '')])
  setNote('')
  $('primary').className = 'btn btn-primary'
  setButtons({ label: 'Add to OnTrack', onClick: add })
}

async function init() {
  const saved = await chrome.storage.local.get(DEFAULTS)
  settings = { ...DEFAULTS, ...saved }

  // Normally the tab you're looking at. (?tab=<id> is only for automated tests.)
  const testTab = new URLSearchParams(location.search).get('tab')
  ;[tab] = testTab
    ? [await chrome.tabs.get(Number(testTab))]
    : await chrome.tabs.query({ active: true, currentWindow: true })

  if (!settings.apiKey) return showSettings(true) // first time: settings, whatever the page
  if (!tab || !/^https?:/.test(tab.url || '')) {
    showCard('Open a product page first', null, '?')
    setMeta(['Then click the OnTrack icon again.'])
    setButtons(null)
    return
  }
  start()
}

init()
