import type { Quest } from '../types/quest'
import { storeQuestForShare } from '../api'

// Share links are short server-stored URLs (/q/<shortId>): the backend keeps
// the quest in SQLite, counts views, and gives crawlers real OG previews.
// The original mechanism — the full quest deflate-compressed into a #q=
// fragment — remains as the fallback when the store API is unreachable, and
// old fragment links keep decoding forever.

const FRAGMENT_PREFIX = '#q='

function bytesToBase64Url(bytes: Uint8Array): string {
  let binary = ''
  const chunk = 0x8000
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk))
  }
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function base64UrlToBytes(text: string): Uint8Array {
  const base64 = text.replace(/-/g, '+').replace(/_/g, '/')
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  return bytes
}

async function pipeBytes(
  bytes: Uint8Array,
  transform: CompressionStream | DecompressionStream,
): Promise<Uint8Array> {
  const stream = new Blob([bytes as BlobPart]).stream().pipeThrough(transform)
  return new Uint8Array(await new Response(stream).arrayBuffer())
}

/** Encode a quest as a URL fragment payload. */
export async function encodeQuestForUrl(quest: Quest): Promise<string> {
  const json = new TextEncoder().encode(JSON.stringify(quest))
  if (typeof CompressionStream === 'undefined') {
    return `j${bytesToBase64Url(json)}`
  }
  const packed = await pipeBytes(json, new CompressionStream('deflate-raw'))
  return `d${bytesToBase64Url(packed)}`
}

/** Decode a fragment payload produced by encodeQuestForUrl. Null when invalid. */
export async function decodeQuestFromUrl(payload: string): Promise<Quest | null> {
  try {
    const kind = payload[0]
    const bytes = base64UrlToBytes(payload.slice(1))
    let json: Uint8Array
    if (kind === 'd') {
      if (typeof DecompressionStream === 'undefined') return null
      json = await pipeBytes(bytes, new DecompressionStream('deflate-raw'))
    } else if (kind === 'j') {
      json = bytes
    } else {
      return null
    }
    const quest = JSON.parse(new TextDecoder().decode(json)) as Quest
    if (typeof quest.id !== 'string' || !Array.isArray(quest.stops)) return null
    return quest
  } catch {
    return null
  }
}

/** Read a shared quest out of the current URL, if one is embedded. */
export async function readQuestFromLocationHash(): Promise<Quest | null> {
  const hash = window.location.hash
  if (!hash.startsWith(FRAGMENT_PREFIX)) return null
  return decodeQuestFromUrl(hash.slice(FRAGMENT_PREFIX.length))
}

const OCCASION_SHARE_LABELS: Record<string, string> = {
  date: 'Date night',
  friends: 'Friends hangout',
  solo: 'Solo time',
  family: 'Family outing',
}

function shareDescription(quest: Quest): string {
  const hours = quest.total_duration_minutes / 60
  const duration = Number.isInteger(hours) ? `${hours}h` : `${hours.toFixed(1)}h`
  const occasion = OCCASION_SHARE_LABELS[quest.occasion] ?? 'Quest'
  return `${occasion} · ${quest.stops.length} stops · ${duration}`
}

/** Legacy share URL: the full quest in the #q= fragment (client-only), with
 * st/sd query params for link-preview crawlers (fragments never reach the
 * server, so api/quest-og.js reads these to render per-quest og tags). */
export async function makeFragmentShareUrl(quest: Quest): Promise<string> {
  const payload = await encodeQuestForUrl(quest)
  const meta = new URLSearchParams({
    st: quest.title.slice(0, 90),
    sd: shareDescription(quest),
  })
  return `${window.location.origin}/quest/${quest.id}?${meta}${FRAGMENT_PREFIX}${payload}`
}

/** Build a share URL for the quest on the current origin.
 *
 * Prefers a short server-stored link (repeat calls with the same content are
 * deduped server-side, so this is safe to call per share tap). Falls back to
 * the self-contained fragment URL when the API is unreachable — a share must
 * never fail because the backend is down. */
export async function makeQuestShareUrl(quest: Quest): Promise<string> {
  try {
    const shortId = await storeQuestForShare(quest)
    return `${window.location.origin}/q/${shortId}`
  } catch {
    return makeFragmentShareUrl(quest)
  }
}
