// Creator pages: the public list behind /by/<handle> and the creator's own
// view of it. See backend/creator_routes.py.

import { getApiBase } from '../api'

export const CREATOR_NAME_MAX = 40
export const CREATOR_BIO_MAX = 140

export type CreatorQuest = {
  short_id: string
  title: string
  /** Who made the quest; a page may list other people's. */
  made_by?: string | null
  /** Only words someone typed; null for automatic text. */
  intro?: string | null
  stops: { name: string; note?: string | null }[]
}

export type MyQuest = CreatorQuest & {
  /** Times the share link has been opened. Only the owner sees this. */
  opens: number
  /** False once the quest has been taken down. */
  available: boolean
}

type CreatorProfile = {
  handle: string
  display_name: string
  bio: string
  instagram: string
}

export type PublicCreatorPage = CreatorProfile & { quests: CreatorQuest[] }

export type MyCreatorPage = CreatorProfile & {
  page_views: number
  max_quests: number
  quests: MyQuest[]
}

export type CreatorFailure =
  | 'bad_key'
  /** A key that was checked, found wrong, and one wrong key too many. */
  | 'too_many'
  /** Too many requests in a minute. Says nothing about the key. */
  | 'busy'
  | 'creator_not_found'
  /** The server turned the request down and said why, in plain words. */
  | 'refused'
  /** Offline, a server error, or a backend without creator pages. */
  | 'unavailable'

const MESSAGES: Record<Exclude<CreatorFailure, 'refused'>, string> = {
  bad_key:
    "This manage link doesn't work. It may have been replaced with a new one.",
  too_many: "Too many tries with a link that doesn't work. Wait a few minutes.",
  busy: "That's a lot of requests at once. Wait a minute, then try again.",
  creator_not_found: 'There is no creator page here.',
  unavailable: "Creator pages aren't available right now. Try again later.",
}

export class CreatorError extends Error {
  readonly reason: CreatorFailure

  constructor(reason: CreatorFailure, message?: string) {
    super(message ?? MESSAGES[reason as Exclude<CreatorFailure, 'refused'>])
    this.reason = reason
  }
}

/** Whether the server checked the key and turned it down. It answers
 * 'too_many' only to a key that is wrong, so that key is as dead as any. */
export function isDeadKey(err: unknown): boolean {
  return (
    err instanceof CreatorError &&
    (err.reason === 'bad_key' || err.reason === 'too_many')
  )
}

const REFUSALS = new Set([
  'quest_not_found',
  'page_full',
  'bad_name',
  'bad_bio',
  'bad_instagram',
])

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; key?: string } = {},
): Promise<T> {
  const headers: Record<string, string> = {}
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (options.key) headers.Authorization = `Bearer ${options.key}`
  let res: Response
  try {
    res = await fetch(`${getApiBase()}${path}`, {
      method: options.method,
      headers,
      body:
        options.body === undefined ? undefined : JSON.stringify(options.body),
    })
  } catch {
    throw new CreatorError('unavailable')
  }
  if (res.ok) {
    return (await res.json().catch(() => {
      throw new CreatorError('unavailable')
    })) as T
  }
  throw failureFrom(res.status, await res.json().catch(() => null))
}

/** What a reply that is not a success means. */
export function failureFrom(status: number, body: unknown): CreatorError {
  const detail = (
    body as { detail?: { code?: string; message?: string } } | null
  )?.detail
  const code = detail?.code
  if (status === 401) return new CreatorError('bad_key')
  if (status === 429) {
    return new CreatorError(code === 'too_many' ? 'too_many' : 'busy')
  }
  // A backend without these routes answers 404 too, so go by the code.
  if (code === 'creator_not_found') return new CreatorError('creator_not_found')
  if (code && REFUSALS.has(code) && detail?.message) {
    return new CreatorError('refused', detail.message)
  }
  return new CreatorError('unavailable')
}

export function fetchCreatorPage(handle: string): Promise<PublicCreatorPage> {
  return request(`/api/creators/${encodeURIComponent(handle)}`)
}

export function fetchMyPage(key: string): Promise<MyCreatorPage> {
  return request('/api/creator/me', { key })
}

export function updateMyPage(
  key: string,
  changes: { display_name?: string; bio?: string; instagram?: string },
): Promise<MyCreatorPage> {
  return request('/api/creator/me', { method: 'PATCH', body: changes, key })
}

export function addMyQuest(
  key: string,
  shortId: string,
): Promise<{ added: boolean; page: MyCreatorPage }> {
  return request('/api/creator/me/quests', {
    method: 'POST',
    body: { short_id: shortId },
    key,
  })
}

export function removeMyQuest(
  key: string,
  shortId: string,
): Promise<MyCreatorPage> {
  return request(`/api/creator/me/quests/${encodeURIComponent(shortId)}`, {
    method: 'DELETE',
    key,
  })
}

/** The quest id in a pasted share link ("…/q/abcd2345") or a bare id. */
export function shareLinkId(text: string): string | null {
  const trimmed = text.trim().split('#')[0].split('?')[0].replace(/\/+$/, '')
  const fromLink = /\/q\/([a-z0-9]{4,16})$/.exec(trimmed)
  if (fromLink) return fromLink[1]
  return /^[a-z0-9]{8}$/.test(trimmed) ? trimmed : null
}
