import { useEffect, useRef, useState } from 'react'

const STEPS = [
  {
    emoji: '🧭',
    title: 'Pick a mood, get a plan',
    body: 'Choose an occasion and an area. We line up a few stops with timings, travel between them and a rough budget.',
  },
  {
    emoji: '🔀',
    title: 'Make it yours',
    body: 'Swap any stop, change the order, or shuffle the whole plan. Tap a place to see it on Google Maps.',
  },
  {
    emoji: '✅',
    title: 'Take it out',
    body: 'Press Start and tick off stops as you go. Keep the night in your journal, with a photo if you like.',
  },
  {
    emoji: '💌',
    title: 'Bring people along',
    body: 'Send the plan as a link or a share card. Know your spots already? Build a quest of your own.',
  },
] as const

/** The small "New here?" card a first-time visitor sees on the home page.
 * It never blocks the page: the tour only opens if they ask for it. */
export function WelcomeNudge({
  onOpen,
  onDismiss,
}: {
  onOpen: () => void
  onDismiss: () => void
}) {
  return (
    <aside className="tour-nudge" aria-label="New here?">
      <span className="tour-nudge-wave" aria-hidden>
        👋
      </span>
      <p className="tour-nudge-text">
        <strong>New here?</strong> Take the 20{'\u2011'}second tour.
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

/** The tour itself: four short cards, skippable at every step.
 *
 * `onClose` reports how far the visitor got. `onExample`, when given, adds a
 * "See an example" button to the last card. */
export function TourSheet({
  onClose,
  onExample,
}: {
  onClose: (result: { step: number; completed: boolean }) => void
  onExample?: () => void
}) {
  const [step, setStep] = useState(0)
  const primaryRef = useRef<HTMLButtonElement>(null)
  const isLast = step === STEPS.length - 1
  const current = STEPS[step]

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose({ step, completed: false })
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose, step])

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
        aria-label="Close the tour"
        onClick={() => onClose({ step, completed: false })}
      />
      <section
        className="swap-sheet tour-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-title"
      >
        <div className="swap-sheet-handle" aria-hidden />
        <p className="swap-sheet-eyebrow">
          How it works · {step + 1} of {STEPS.length}
        </p>
        <div className="tour-step" aria-live="polite">
          <span className="tour-step-emoji" aria-hidden>
            {current.emoji}
          </span>
          <h2 id="tour-title" className="tour-step-title">
            {current.title}
          </h2>
          <p className="tour-step-body">{current.body}</p>
        </div>
        <div className="tour-dots" aria-hidden>
          {STEPS.map((s, i) => (
            <span
              key={s.title}
              className={`tour-dot${i === step ? ' tour-dot--active' : ''}`}
            />
          ))}
        </div>
        <button
          ref={primaryRef}
          type="button"
          className="swap-confirm-btn tour-primary"
          onClick={() =>
            isLast
              ? onClose({ step, completed: true })
              : setStep((index) => index + 1)
          }
        >
          {isLast ? 'Got it' : 'Next'}
        </button>
        {!isLast && (
          <button
            type="button"
            className="tour-secondary"
            onClick={() => onClose({ step, completed: false })}
          >
            Skip
          </button>
        )}
        {isLast && onExample && (
          <button type="button" className="tour-secondary" onClick={onExample}>
            See an example quest
          </button>
        )}
      </section>
    </>
  )
}
