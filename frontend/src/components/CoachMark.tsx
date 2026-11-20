import { useEffect, useLayoutEffect, useRef, type ReactNode } from 'react'

/** Where the bubble sits relative to the control it points at. */
export type CoachPlacement = 'left' | 'below' | 'below-start' | 'above'

/** Space kept between the bubble and the edge of the screen. */
const GUTTER = 12

/** Top and bottom of the screen that fixed bars may cover. */
const COVERED_TOP = 80
const COVERED_BOTTOM = 110

/** A one-time pointer attached to the control it explains.
 *
 * Render it inside a positioned wrapper around that control. It never takes
 * focus and never blocks the page: "Got it", or simply using the control,
 * sends it away.
 *
 * `reveal` scrolls the page to the bubble when it appears somewhere off
 * screen. Only for when the person asked to be shown around: a hint that
 * turns up on its own should never move the page under them. */
export function CoachMark({
  placement,
  title,
  children,
  onDismiss,
  reveal = false,
}: {
  placement: CoachPlacement
  title: string
  children: ReactNode
  onDismiss: () => void
  reveal?: boolean
}) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const node = ref.current
    if (!reveal || !node) return
    const rect = node.getBoundingClientRect()
    const inView =
      rect.top >= COVERED_TOP &&
      rect.bottom <= window.innerHeight - COVERED_BOTTOM
    if (inView) return
    const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    node.scrollIntoView({ block: 'center', behavior: calm ? 'auto' : 'smooth' })
  }, [reveal])

  // A centred bubble next to a control near the side of the screen would hang
  // off the edge. Slide it back in; the arrow stays on the control.
  useLayoutEffect(() => {
    if (placement !== 'below' && placement !== 'above') return
    const node = ref.current
    if (!node) return
    const fit = () => {
      node.style.setProperty('--coach-shift', '0px')
      const rect = node.getBoundingClientRect()
      const width = document.documentElement.clientWidth
      let shift = 0
      if (rect.left < GUTTER) shift = GUTTER - rect.left
      else if (rect.right > width - GUTTER) shift = width - GUTTER - rect.right
      node.style.setProperty('--coach-shift', `${Math.round(shift)}px`)
    }
    fit()
    window.addEventListener('resize', fit)
    return () => window.removeEventListener('resize', fit)
  }, [placement])

  return (
    <div ref={ref} className={`coach coach--${placement}`} role="note">
      <div className="coach-bubble">
        <p className="coach-text">
          <strong>{title}</strong> {children}
        </p>
        <button type="button" className="coach-dismiss" onClick={onDismiss}>
          Got it
        </button>
      </div>
      <span className="coach-arrow" aria-hidden />
    </div>
  )
}
