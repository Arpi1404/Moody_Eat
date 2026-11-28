// The Call and Website links on a stop. The numbers and addresses come from
// Google by way of a quest that may have been stored by anyone, so each is
// checked here before it goes into a link, whatever the server did.

// Digits, spaces, "+", "-" and round brackets. Nothing else: no "#", "*", ","
// or ";", which a phone can take as codes or pauses.
const PHONE_CHARS = /^[0-9 +()-]+$/
// No real number is outside these (E.164 allows 15 digits).
const PHONE_MIN_DIGITS = 6
const PHONE_MAX_DIGITS = 15
const PHONE_MAX_CHARS = 30

/** A tel: link for the number, or null when it is not plainly one. */
export function phoneLink(phone: unknown): string | null {
  if (typeof phone !== 'string') return null
  const text = phone.trim()
  if (text.length > PHONE_MAX_CHARS || !PHONE_CHARS.test(text)) return null
  const international = text.startsWith('+')
  // A "+" is only ever the first character.
  if (text.lastIndexOf('+') > 0) return null
  // "+44 (0)20 …": the bracketed 0 is dialled only from inside the country,
  // never after a country code.
  const dialled = international ? text.replace('(0)', '') : text
  const digits = dialled.replace(/[^0-9]/g, '')
  if (digits.length < PHONE_MIN_DIGITS || digits.length > PHONE_MAX_DIGITS) {
    return null
  }
  return `tel:${international ? '+' : ''}${digits}`
}

const WEBSITE_MAX_CHARS = 500

// Addresses that are not the place's own site, named so that the button says
// what it opens. A domain here also covers its subdomains.
const KNOWN_SITES: [label: string, domains: string[]][] = [
  ['Instagram', ['instagram.com']],
  ['Facebook', ['facebook.com', 'fb.com']],
  ['WhatsApp', ['wa.me', 'whatsapp.com']],
  ['Zomato', ['zomato.com']],
  ['Swiggy', ['swiggy.com']],
  ['EazyDiner', ['eazydiner.com']],
  ['magicpin', ['magicpin.in']],
  ['OpenTable', ['opentable.com']],
  ['Tripadvisor', ['tripadvisor.com', 'tripadvisor.in', 'tripadvisor.co.uk']],
  ['Linktree', ['linktr.ee']],
]

export interface WebsiteLink {
  href: string
  /** "Website", or the name of the service the address belongs to. */
  label: string
}

/** The link for a place's website, or null unless it is an http(s) address. */
export function websiteLink(website: unknown): WebsiteLink | null {
  if (typeof website !== 'string') return null
  const text = website.trim()
  // The scheme has to be written out, and nothing may be hiding in the middle:
  // the URL parser would quietly drop a tab or a newline.
  if (
    text.length > WEBSITE_MAX_CHARS ||
    !/^https?:\/\/[^\s<>"'\\]+$/i.test(text)
  ) {
    return null
  }
  let url: URL
  try {
    url = new URL(text)
  } catch {
    return null
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return null
  // "https://instagram.com@elsewhere.example" goes elsewhere.
  if (url.username || url.password) return null
  const host = url.hostname.toLowerCase().replace(/\.$/, '')
  const known = KNOWN_SITES.find(([, domains]) =>
    domains.some((domain) => host === domain || host.endsWith(`.${domain}`)),
  )
  return { href: url.href, label: known ? known[0] : 'Website' }
}
