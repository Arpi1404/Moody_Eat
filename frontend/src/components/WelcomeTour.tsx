import { useEffect, useRef } from 'react'

/** The small "New here?" card a first-time visitor sees on the home page.
 * It never blocks the page: the explainer only opens if they ask for it. */
export function WelcomeNudge({
  onOpen,
  onDismiss,
}: {
  onOpen: () => void
  onDismiss: () => void
}) {
  return (
    <aside className="tour-nudge" aria-label="New here?">
      <p className="tour-nudge-text">
        <strong>New here?</strong> See how it works.
      </p>
      <button type="button" className="tour-nudge-open" onClick={onOpen}>
        Show me
      </button>
      <button
        type="button"
        className="tour-nudge-close"
        aria-label="Dismiss"
        onClick={onDismiss}
      >
        ✕
      </button>
    </aside>
  )
}

/** "How it works": one card that says what to do first.
 *
 * It stops there on purpose. Everything a quest lets you do afterwards is
 * taught on the quest page, next to the control (see CoachMark).
 *
 * `onClose` reports whether the visitor read it through ("Got it") or backed
 * out. `onExample`, when given, adds a "See an example quest" button. */
export function TourSheet({
  onClose,
  onExample,
}: {
  onClose: (completed: boolean) => void
  onExample?: () => void
}) {
  const primaryRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose(false)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  useEffect(() => {
    document.body.style.overflow = 'hidden'
    primaryRef.current?.focus()
    return () => {
      document.body.style.overflow = ''
    }
  }, [])

  return (
    <>
      <button
        type="button"
        className="swap-sheet-overlay"
        aria-label="Close"
        onClick={() => onClose(false)}
      />
      <section
        className="swap-sheet tour-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-title"
      >
        <div className="swap-sheet-handle" aria-hidden />
        <p className="swap-sheet-eyebrow">How it works</p>
        <div className="tour-step">
          <h2 id="tour-title" className="tour-step-title">
            Pick a mood, get a plan
          </h2>
          <p className="tour-step-body">
            Choose an occasion and an area. We line up a few stops with
            timings, travel between them and a rough budget. Any stop you
            don't fancy, you can change.
          </p>
        </div>
        <button
          ref={primaryRef}
          type="button"
          className="swap-confirm-btn tour-primary"
          onClick={() => onClose(true)}
        >
          Got it
        </button>
        {onExample && (
          <button type="button" className="tour-secondary" onClick={onExample}>
            See an example quest
          </button>
        )}
      </section>
    </>
  )
}
