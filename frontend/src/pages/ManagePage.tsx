// The creator's own view, /manage, opened with the private manage link. The
// key is read from storage (see lib/creatorKey.ts) and never shown on screen,
// so a screenshot of this page gives nothing away.

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { LoadingState } from '../components/states'
import { track } from '../lib/analytics'
import { CONTACT_URL } from '../lib/contact'
import {
  addMyQuest,
  CREATOR_BIO_MAX,
  CREATOR_NAME_MAX,
  CreatorError,
  fetchMyPage,
  isDeadKey,
  removeMyQuest,
  shareLinkId,
  updateMyPage,
  type CreatorFailure,
  type MyCreatorPage,
} from '../lib/creatorApi'
import {
  captureKeyFromAddress,
  dropNewKey,
  forgetKeys,
  keepKey,
  newKey,
  storedKey,
} from '../lib/creatorKey'
import {
  isOtherPage,
  keyHandle,
  mustAskBeforeSwitching,
  type StoredKeyCheck,
} from '../lib/creatorKeySwitch'
import { tidyText } from '../lib/creatorText'
import '../App.css'

type View =
  | { status: 'loading' }
  | { status: 'signed_out' }
  | { status: 'failed'; reason: CreatorFailure; message: string }
  | { status: 'ready'; page: MyCreatorPage; key: string; notice?: string }
  // A link for another page than the one this browser manages: nothing is
  // changed until the person says which to keep.
  | {
      status: 'choose'
      page: MyCreatorPage
      key: string
      currentHandle: string
      /** Missing when the current page could not be loaded just now. */
      currentName?: string
    }

function failure(err: unknown): View {
  const known =
    err instanceof CreatorError ? err : new CreatorError('unavailable')
  return { status: 'failed', reason: known.reason, message: known.message }
}

/** Open the page with the newest key this browser has been given, falling
 * back to the one it used before if the new one turns out to be dead. */
async function openMyPage(): Promise<View> {
  // Normally index.html has done this already; a link opened any other way
  // must not stay in the address bar either.
  captureKeyFromAddress()
  const fresh = newKey()
  if (fresh) {
    try {
      const page = await fetchMyPage(fresh)
      const choice = await askBeforeSwitching(page, fresh)
      if (choice) return choice
      keepKey(fresh)
      return { status: 'ready', page, key: fresh }
    } catch (err) {
      // Anything but a dead key: keep it, so trying again can use it.
      if (!isDeadKey(err)) return failure(err)
      dropNewKey()
      const before = storedKey()
      if (!before || before === fresh) {
        if (before === fresh) forgetKeys()
        return failure(err)
      }
    }
  }
  const key = storedKey()
  if (!key) return { status: 'signed_out' }
  try {
    const page = await fetchMyPage(key)
    return {
      status: 'ready',
      page,
      key,
      notice: fresh
        ? "That link doesn't work any more. This is the page this browser had already opened."
        : undefined,
    }
  } catch (err) {
    if (isDeadKey(err)) forgetKeys()
    return failure(err)
  }
}

/** The question to ask before an accepted key replaces the one this browser
 * holds for another page, or null when there is nothing to ask. */
async function askBeforeSwitching(
  page: MyCreatorPage,
  fresh: string,
): Promise<View | null> {
  const current = storedKey()
  if (current === null || !isOtherPage(current, fresh)) return null
  let check: StoredKeyCheck = 'works'
  let currentName: string | undefined
  try {
    currentName = (await fetchMyPage(current)).display_name
  } catch (err) {
    check = isDeadKey(err) ? 'dead' : 'unknown'
  }
  if (!mustAskBeforeSwitching(current, fresh, check)) return null
  return {
    status: 'choose',
    page,
    key: fresh,
    currentHandle: keyHandle(current),
    currentName,
  }
}

function LostLink() {
  return (
    <>
      Lost your link, or shared it by mistake?{' '}
      <a href={CONTACT_URL} target="_blank" rel="noopener noreferrer">
        Message us on Instagram
      </a>{' '}
      and we'll send a new one. The old one stops working.
    </>
  )
}

function PublicLink({ page }: { page: MyCreatorPage }) {
  const url = `${window.location.origin}/by/${page.handle}`
  const [copied, setCopied] = useState<'yes' | 'failed' | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url)
      setCopied('yes')
      track('creator_public_link_copied')
    } catch {
      inputRef.current?.select()
      setCopied('failed')
    }
  }

  return (
    <section className="cm-card cm-public" aria-labelledby="cm-public-title">
      <h2 id="cm-public-title">Your public link</h2>
      <p>This is the one to share, in your bio or anywhere else.</p>
      <input
        ref={inputRef}
        className="cq-location-input cm-url"
        value={url}
        readOnly
        aria-label="Your public link"
        onFocus={(e) => e.target.select()}
      />
      <div className="cm-row">
        <button type="button" className="cm-primary" onClick={copy}>
          {copied === 'yes' ? '✓ Copied' : 'Copy public link'}
        </button>
        <Link to={`/by/${page.handle}`}>View your page</Link>
      </div>
      {copied === 'failed' && (
        <p role="status">Couldn't copy. The link is selected: copy it by hand.</p>
      )}
      <p className="cm-small">
        Viewed {page.page_views.toLocaleString()}{' '}
        {page.page_views === 1 ? 'time' : 'times'}. Only you see this.
      </p>
    </section>
  )
}

function QuestList({
  page,
  manageKey,
  onPage,
  onError,
}: {
  page: MyCreatorPage
  manageKey: string
  onPage: (page: MyCreatorPage) => void
  onError: (err: unknown) => string
}) {
  const [link, setLink] = useState('')
  const [message, setMessage] = useState<{ text: string; bad: boolean } | null>(
    null,
  )
  const [busy, setBusy] = useState(false)
  // The quest whose Remove button was pressed once and awaits a second press.
  const [removing, setRemoving] = useState<string | null>(null)

  const add = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    const shortId = shareLinkId(link)
    if (!shortId) {
      setMessage({
        text: "That isn't a quest's share link. On the quest, tap Share, then Copy link. It looks like …/q/abcd2345.",
        bad: true,
      })
      return
    }
    setBusy(true)
    try {
      const result = await addMyQuest(manageKey, shortId)
      track('creator_quest_added', {
        source: 'manage',
        result: result.added ? 'added' : 'already',
      })
      onPage(result.page)
      setLink('')
      setMessage({
        text: result.added ? 'Added.' : "It's already on your page.",
        bad: false,
      })
    } catch (err) {
      track('creator_quest_added', { source: 'manage', result: 'failed' })
      setMessage({ text: onError(err), bad: true })
    } finally {
      setBusy(false)
    }
  }

  const remove = async (shortId: string) => {
    if (busy) return
    setBusy(true)
    try {
      onPage(await removeMyQuest(manageKey, shortId))
      track('creator_quest_removed')
      setMessage({ text: 'Removed from your page.', bad: false })
    } catch (err) {
      setMessage({ text: onError(err), bad: true })
    } finally {
      setRemoving(null)
      setBusy(false)
    }
  }

  return (
    <section className="cm-card" aria-labelledby="cm-quests-title">
      <h2 id="cm-quests-title">
        Your quests ({page.quests.length}/{page.max_quests})
      </h2>
      <form onSubmit={add}>
        <label className="cm-label" htmlFor="cm-add">
          Add a quest by its share link
        </label>
        <div className="cq-location-row">
          <input
            id="cm-add"
            className="cq-location-input cm-input"
            value={link}
            onChange={(e) => setLink(e.target.value)}
            placeholder="Paste a /q/ link"
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
          />
          <button type="submit" className="cq-search-btn" disabled={busy}>
            Add
          </button>
        </div>
      </form>
      <p className={message?.bad ? 'cq-error' : 'cq-hint'} role="status">
        {message?.text}
      </p>

      {page.quests.length === 0 ? (
        <p>
          Nothing here yet. Paste a link above, or use "Add to my page" when you
          share a quest from this browser.
        </p>
      ) : (
        <ul className="cm-quests">
          {page.quests.map((quest) => (
            <li key={quest.short_id}>
              <div className="cm-quest-info">
                {quest.available ? (
                  <>
                    {/* Opening it here counts as an open, like anyone's. */}
                    <Link to={`/q/${quest.short_id}`}>{quest.title}</Link>
                    <p className="cm-small">
                      Opened {quest.opens.toLocaleString()}{' '}
                      {quest.opens === 1 ? 'time' : 'times'} ·{' '}
                      {quest.stops.map((s) => s.name).join(' → ')}
                    </p>
                  </>
                ) : (
                  <p className="cm-small">
                    A quest that has been taken down. Its link no longer works
                    and it is not shown on your page.
                  </p>
                )}
              </div>
              {removing === quest.short_id ? (
                <span className="cm-confirm">
                  <button
                    type="button"
                    className="cm-danger"
                    disabled={busy}
                    onClick={() => remove(quest.short_id)}
                    autoFocus
                  >
                    Yes, remove
                  </button>
                  <button type="button" onClick={() => setRemoving(null)}>
                    Keep
                  </button>
                </span>
              ) : (
                <button
                  type="button"
                  className="cm-remove"
                  aria-label={`Remove ${quest.title}`}
                  onClick={() => setRemoving(quest.short_id)}
                >
                  Remove
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="cm-small">
        Open counts are not shown on your page, and include your own opens.
        Removing a quest takes it off this page only: its share link keeps
        working. To delete a shared quest altogether,{' '}
        <a href={CONTACT_URL} target="_blank" rel="noopener noreferrer">
          message us
        </a>
        .
      </p>
    </section>
  )
}

function ProfileForm({
  page,
  manageKey,
  onPage,
  onError,
}: {
  page: MyCreatorPage
  manageKey: string
  onPage: (page: MyCreatorPage) => void
  onError: (err: unknown) => string
}) {
  const [name, setName] = useState(page.display_name)
  const [bio, setBio] = useState(page.bio)
  const [instagram, setInstagram] = useState(page.instagram)
  const [message, setMessage] = useState<{ text: string; bad: boolean } | null>(
    null,
  )
  const [busy, setBusy] = useState(false)
  const nameLength = tidyText(name).length
  const bioLength = tidyText(bio).length
  const invalid =
    nameLength < 1 ||
    nameLength > CREATOR_NAME_MAX ||
    bioLength > CREATOR_BIO_MAX

  const save = async (event: FormEvent) => {
    event.preventDefault()
    if (busy || invalid) return
    setBusy(true)
    setMessage(null)
    try {
      const updated = await updateMyPage(manageKey, {
        display_name: name,
        bio,
        instagram,
      })
      onPage(updated)
      setName(updated.display_name)
      setBio(updated.bio)
      setInstagram(updated.instagram)
      track('creator_profile_saved', {
        has_bio: Boolean(updated.bio),
        has_instagram: Boolean(updated.instagram),
      })
      setMessage({ text: 'Saved.', bad: false })
    } catch (err) {
      setMessage({ text: onError(err), bad: true })
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="cm-card" aria-labelledby="cm-profile-title">
      <h2 id="cm-profile-title">What your page says</h2>
      <p className="cm-small">All of this is public.</p>
      <form onSubmit={save} className="cm-form">
        <label className="cm-label" htmlFor="cm-name">
          Name ({nameLength}/{CREATOR_NAME_MAX})
        </label>
        <input
          id="cm-name"
          className="cq-location-input cm-input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          aria-invalid={nameLength < 1 || nameLength > CREATOR_NAME_MAX}
        />
        <label className="cm-label" htmlFor="cm-bio">
          One-line bio, optional ({bioLength}/{CREATOR_BIO_MAX})
        </label>
        <input
          id="cm-bio"
          className="cq-location-input cm-input"
          value={bio}
          onChange={(e) => setBio(e.target.value)}
          aria-invalid={bioLength > CREATOR_BIO_MAX}
        />
        <label className="cm-label" htmlFor="cm-instagram">
          Instagram username, optional
        </label>
        <input
          id="cm-instagram"
          className="cq-location-input cm-input"
          value={instagram}
          onChange={(e) => setInstagram(e.target.value)}
          placeholder="priya.eats"
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
        />
        <button
          type="submit"
          className="cm-primary"
          disabled={busy || invalid}
        >
          Save
        </button>
        <p className={message?.bad ? 'cq-error' : 'cq-hint'} role="status">
          {message?.text}
        </p>
      </form>
    </section>
  )
}

export function ManagePage() {
  const [view, setView] = useState<View>({ status: 'loading' })
  // Goes up to open the page again: after a retry or a newly pasted link.
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let live = true
    void openMyPage().then((next) => {
      if (live) setView(next)
    })
    return () => {
      live = false
    }
  }, [attempt])

  const reopen = useCallback(() => {
    setView({ status: 'loading' })
    setAttempt((n) => n + 1)
  }, [])

  // A manage link pasted into this tab changes only the "#" part, so no page
  // loads and index.html does not run: take the key off the address bar here.
  useEffect(() => {
    const onHashChange = () => {
      if (captureKeyFromAddress()) reopen()
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [reopen])

  const setPage = (page: MyCreatorPage) =>
    setView((v) => (v.status === 'ready' ? { ...v, page } : v))

  // A key replaced while the page was open: say so and stop offering edits.
  const onError = (err: unknown): string => {
    if (isDeadKey(err)) {
      forgetKeys()
      setView(failure(err))
    }
    return err instanceof CreatorError
      ? err.message
      : "That didn't work. Try again."
  }

  return (
    <main className="cp-page">
      <div className="cp-inner">
        {view.status === 'loading' && (
          <LoadingState message="Opening your page..." />
        )}

        {view.status === 'signed_out' && (
          <section className="cm-card">
            <h1>Manage your page</h1>
            <p>
              Open your private manage link to get in. There is no password:
              the link is the key.
            </p>
            <p>
              <LostLink />
            </p>
            <Link to="/">Back home</Link>
          </section>
        )}

        {view.status === 'failed' && (
          <section className="cm-card" role="alert">
            <h1>
              {view.reason === 'bad_key' || view.reason === 'too_many'
                ? "That link doesn't work"
                : "Can't open your page"}
            </h1>
            <p>{view.message}</p>
            {view.reason === 'bad_key' ? (
              <p>
                <LostLink />
              </p>
            ) : (
              <button type="button" className="cm-primary" onClick={reopen}>
                Try again
              </button>
            )}
            <p>
              <Link to="/">Back home</Link>
            </p>
          </section>
        )}

        {view.status === 'choose' && (
          <section className="cm-card" aria-labelledby="cm-choose-title">
            <h1 id="cm-choose-title">Switch pages?</h1>
            <p>
              This link opens <strong>{view.page.display_name}</strong> (/by/
              {view.page.handle}).
            </p>
            <p>
              This browser manages{' '}
              <strong>{view.currentName ?? view.currentHandle}</strong> (/by/
              {view.currentHandle}). It can manage one page at a time.
            </p>
            <p className="cm-small">
              If you switch, you'll need your link for /by/{view.currentHandle}{' '}
              to manage it here again. If you didn't expect this link, keep
              your page.
            </p>
            <div className="cm-row">
              <button
                type="button"
                className="cm-primary"
                onClick={() => {
                  // Only the link on screen: another may have arrived since.
                  if (newKey() === view.key) dropNewKey()
                  reopen()
                }}
              >
                Keep {view.currentHandle}
              </button>
              <button
                type="button"
                className="cm-secondary"
                onClick={() => {
                  keepKey(view.key)
                  setView({ status: 'ready', page: view.page, key: view.key })
                }}
              >
                Switch
              </button>
            </div>
          </section>
        )}

        {view.status === 'ready' && (
          <>
            <header className="cp-header">
              <h1>Your page</h1>
              {view.notice && (
                <p className="cm-notice" role="status">
                  {view.notice}
                </p>
              )}
            </header>
            <PublicLink page={view.page} />
            <section className="cm-private" aria-label="About your manage link">
              <strong>
                Your manage link is private: it is the key to this page.
              </strong>
              <p>
                Anyone who has the link you were sent can change your page, so
                never post it or put it in your bio. This browser now remembers
                it. Keep the link somewhere safe as well, in case the browser
                forgets. <LostLink />
              </p>
            </section>
            <QuestList
              page={view.page}
              manageKey={view.key}
              onPage={setPage}
              onError={onError}
            />
            <ProfileForm
              page={view.page}
              manageKey={view.key}
              onPage={setPage}
              onError={onError}
            />
            <button
              type="button"
              className="cm-forget"
              onClick={() => {
                forgetKeys()
                setView({ status: 'signed_out' })
              }}
            >
              Forget the key on this browser
            </button>
          </>
        )}
      </div>
    </main>
  )
}

export default ManagePage
