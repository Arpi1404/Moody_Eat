// Google's formatted address, cut down to what tells two places apart.

/** The address without its country and postcode line:
 * "…, Indiranagar, Bengaluru, Karnataka 560038, India" ends at "Bengaluru". */
function addressParts(address: string): string[] {
  const parts = address
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
  if (parts.length > 2) parts.pop()
  if (parts.length > 2 && /\b\d{5,6}\b/.test(parts[parts.length - 1])) {
    parts.pop()
  }
  return parts
}

/** One short line per address, in order: the last three parts (street or
 * neighbourhood, then city). Where two would read the same, say two branches
 * of a chain in one neighbourhood, those keep their street details too. */
export function shortAddresses(addresses: string[]): string[] {
  const parts = addresses.map(addressParts)
  const short = parts.map((p) => p.slice(-3).join(', '))
  return short.map((line, i) =>
    short.indexOf(line) === short.lastIndexOf(line) ? line : parts[i].join(', '),
  )
}
