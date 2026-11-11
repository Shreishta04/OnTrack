// Talking to the iPhone Shortcut from the web app.

// The iPhone Shortcut's name, exactly as it's called in the Shortcuts app.
export const SHORTCUT_NAME = 'Add to OnTrack'
export const IPHONE = /iPhone|iPad|iPod/.test(navigator.userAgent)

// Hand a link to the Shortcut. Pasting a link here makes OUR server download
// the store's page, from Singapore and without a browser, which many stores
// block or answer with another country's page. The Shortcut downloads it on
// the phone instead, the way a shopper sees it. (A web page can't download
// another site's page itself: browsers forbid it, a safety rule called CORS.)
export function shortcutLink(url: string): string {
  return `shortcuts://run-shortcut?name=${encodeURIComponent(SHORTCUT_NAME)}&input=text&text=${encodeURIComponent(url)}`
}
