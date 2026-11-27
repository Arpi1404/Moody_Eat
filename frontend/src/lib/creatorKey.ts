// A creator's manage key. There are no accounts: whoever holds the key can
// change the page, so it is treated like a password. It never goes to
// analytics, and the only place it is sent is our API, as a request header.
//
// It arrives after the "#" of the manage link, which browsers do not send to
// any server. The inline script in index.html moves it into storage and off
// the address bar before any other script (analytics included) can see it.
// captureKeyFromAddress is the same step for a link pasted into a tab that is
// already open, which loads no new page. Change one, change both.

const KEY = 'moodyeat:creator_key'
// A key just taken from a link, not yet accepted by the server. Kept apart so
// that opening an old, replaced link cannot overwrite one that works.
const NEW_KEY = 'moodyeat:creator_key_new'

declare global {
  interface Window {
    /** Set by index.html when storage is unavailable. */
    __moodyeatNewKey?: string
  }
}

function read(name: string): string | null {
  try {
    return localStorage.getItem(name)
  } catch {
    return null
  }
}

function remove(name: string): void {
  try {
    localStorage.removeItem(name)
  } catch {
    // Nothing was stored.
  }
}

/** The key this browser has used successfully, if any. */
export function storedKey(): string | null {
  return read(KEY)
}

export function newKey(): string | null {
  return read(NEW_KEY) ?? window.__moodyeatNewKey ?? null
}

export function dropNewKey(): void {
  remove(NEW_KEY)
  delete window.__moodyeatNewKey
}

/** The server accepted this key: remember it. */
export function keepKey(key: string): void {
  try {
    localStorage.setItem(KEY, key)
  } catch {
    // Private mode: it works until the tab is closed.
    window.__moodyeatNewKey = key
    return
  }
  dropNewKey()
}

export function forgetKeys(): void {
  remove(KEY)
  dropNewKey()
}

/** Take a key out of the address bar. True when there was one. */
export function captureKeyFromAddress(): boolean {
  const match = /^#k=([^&]+)/.exec(window.location.hash)
  if (!match) return false
  const key = match[1]
  try {
    localStorage.setItem(NEW_KEY, key)
  } catch {
    window.__moodyeatNewKey = key
  }
  window.history.replaceState(window.history.state, '', window.location.pathname)
  return true
}
