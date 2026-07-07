import type { Quest } from '../types/quest'

// Quests only exist in the creator's browser (localStorage), so a bare
// /quest/:id URL is dead for anyone else. Share links therefore carry the
// full quest, deflate-compressed and base64url-encoded, in the #q= fragment.
// The fragment never reaches the server and survives copy/paste intact.

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

/** Build a share URL for the quest on the current origin. */
export async function makeQuestShareUrl(quest: Quest): Promise<string> {
  const payload = await encodeQuestForUrl(quest)
  return `${window.location.origin}/quest/${quest.id}${FRAGMENT_PREFIX}${payload}`
}
