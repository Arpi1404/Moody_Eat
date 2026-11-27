// A creator's public page, /by/<handle>: the quests they picked. Everything a
// person typed is rendered as plain text by React; nothing here is HTML.

import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ErrorState, LoadingState } from '../components/states'
import { track } from '../lib/analytics'
import { CONTACT_URL } from '../lib/contact'
import {
  CreatorError,
  fetchCreatorPage,
  type PublicCreatorPage,
} from '../lib/creatorApi'
import '../App.css'

type Loaded =
  | { handle: string; status: 'ready'; page: PublicCreatorPage }
  | { handle: string; status: 'missing' | 'unavailable' }
  | { handle: string; status: 'busy'; message: string }

export function CreatorPage() {
  const { handle = '' } = useParams<{ handle: string }>()
  const navigate = useNavigate()
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  // An answer for another handle is as good as none.
  const state = loaded?.handle === handle ? loaded : null

  useEffect(() => {
    let live = true
    fetchCreatorPage(handle)
      .then((page) => {
        if (!live) return
        setLoaded({ handle, status: 'ready', page })
        track('creator_page_viewed', { quest_count: page.quests.length })
      })
      .catch((err) => {
        if (!live) return
        const reason = err instanceof CreatorError ? err.reason : 'unavailable'
        if (reason === 'busy') {
          setLoaded({ handle, status: 'busy', message: (err as Error).message })
          return
        }
        const missing = reason === 'creator_not_found'
        setLoaded({ handle, status: missing ? 'missing' : 'unavailable' })
      })
    return () => {
      live = false
    }
  }, [handle])

  if (state?.status !== 'ready') {
    return (
      <main className="cp-page">
        <div className="cp-inner">
          {state === null ? (
            <LoadingState message="Loading quests..." />
          ) : (
            <ErrorState
              title={
                state.status === 'missing' ? 'Page not found' : 'Not available'
              }
              description={
                state.status === 'missing'
                  ? 'There is no creator page at this address.'
                  : state.status === 'busy'
                    ? state.message
                    : "Creator pages aren't available right now. Try again later."
              }
              retryLabel="Back home"
              onRetry={() => navigate('/')}
            />
          )}
        </div>
      </main>
    )
  }

  const { page } = state
  return (
    <main className="cp-page">
      <div className="cp-inner">
        <header className="cp-header">
          <h1>Quests picked by {page.display_name}</h1>
          {page.bio && <p className="cp-bio">{page.bio}</p>}
          {page.instagram && (
            <a
              className="cp-instagram"
              href={`https://www.instagram.com/${encodeURIComponent(page.instagram)}`}
              target="_blank"
              rel="noopener noreferrer nofollow"
            >
              @{page.instagram} on Instagram
            </a>
          )}
        </header>

        {page.quests.length === 0 ? (
          <p className="cp-empty">No quests here yet. Check back soon.</p>
        ) : (
          <ul className="cp-quests">
            {page.quests.map((quest) => (
              <li key={quest.short_id} className="cp-card">
                <h2>
                  <Link
                    to={`/q/${quest.short_id}`}
                    state={{
                      from: `/by/${page.handle}`,
                      fromLabel: 'Quests',
                    }}
                    onClick={() =>
                      track('creator_quest_opened', {
                        short_id: quest.short_id,
                      })
                    }
                  >
                    {quest.title}
                  </Link>
                </h2>
                {quest.made_by && (
                  <p className="cp-made-by">made by {quest.made_by}</p>
                )}
                {quest.intro && <p className="cp-intro">{quest.intro}</p>}
                <ol className="cp-stops">
                  {quest.stops.map((stop, i) => (
                    <li key={i}>
                      <span className="cp-stop-name">{stop.name}</span>
                      {stop.note && <p className="cp-note">{stop.note}</p>}
                    </li>
                  ))}
                </ol>
              </li>
            ))}
          </ul>
        )}

        <Link to="/create" className="cp-build">
          Build your own quest
        </Link>

        <p className="qp-report">
          <a
            href={CONTACT_URL}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => track('creator_report_tapped')}
          >
            Report this page
          </a>{' '}
          on Instagram. Tell us its address: <strong>/by/{page.handle}</strong>
        </p>
      </div>
    </main>
  )
}

export default CreatorPage
