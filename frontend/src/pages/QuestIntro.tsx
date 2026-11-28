// The quest's opening lines. Kept to three so that the first stop is near the
// top of the screen, with the rest one tap away.

import { useEffect, useId, useRef, useState } from 'react'

export function QuestIntro({ text }: { text: string }) {
  const ref = useRef<HTMLParagraphElement>(null)
  const id = useId()
  const [open, setOpen] = useState(false)
  const [cut, setCut] = useState(false)

  // Whether three lines hide anything depends on the width and the font, so it
  // is measured: again when either changes, or the words do.
  useEffect(() => {
    const node = ref.current
    if (!node || open) return
    const measure = () => setCut(node.scrollHeight > node.clientHeight + 1)
    const observer = new ResizeObserver(measure)
    // Reports once on starting, then on every change of size.
    observer.observe(node)
    let current = true
    void document.fonts?.ready.then(() => {
      if (current) measure()
    })
    return () => {
      current = false
      observer.disconnect()
    }
  }, [open, text])

  return (
    <div className="qp-intro">
      <p
        ref={ref}
        id={id}
        className={`qp-narrative${open ? '' : ' qp-narrative--short'}`}
      >
        {text}
      </p>
      {(cut || open) && (
        <button
          type="button"
          className="qp-intro-toggle"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((was) => !was)}
        >
          {open ? 'Show less' : 'Read more'}
        </button>
      )}
    </div>
  )
}
