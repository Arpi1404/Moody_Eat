import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type Ref,
} from 'react'
import {
  fetchLocationSuggestions,
  fetchSuggestionLocation,
  type LocationSuggestion,
} from '../api'

const MIN_CHARS = 2
const DEBOUNCE_MS = 250

function newSessionToken(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}

/** Text put in the field when a suggestion is picked: "Banjara Hills,
 * Hyderabad". The city is the third part from the end of Google's
 * "…, City, State, Country" line; shorter lines have no city to add. */
function suggestionLabel(s: LocationSuggestion): string {
  const parts = s.secondary_text
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
  const city = parts.length >= 3 ? parts[parts.length - 3] : null
  return city && city !== s.main_text ? `${s.main_text}, ${city}` : s.main_text
}

function PinIcon() {
  return (
    <svg
      className="loc-suggest-pin"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <path
        d="M12 21s-6.5-5.6-6.5-10.5a6.5 6.5 0 0 1 13 0C18.5 15.4 12 21 12 21Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="10.5" r="2.2" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  )
}

/** A location text field that suggests matching places as you type.
 *
 * Typing still works with no suggestions at all (offline, API down): the
 * field is an ordinary text input and its text is searched as before.
 *
 * `onChange` fires for typing and for a pick (with the picked label).
 * `onResolve` follows a pick once its coordinates are known, and only if the
 * field still shows that pick. */
export function LocationInput({
  value,
  onChange,
  onResolve,
  inputRef,
  id,
  className,
  placeholder,
  required,
  ariaLabel,
}: {
  value: string
  onChange: (text: string) => void
  onResolve: (picked: { lat: number; lng: number; label: string }) => void
  inputRef?: Ref<HTMLInputElement>
  id?: string
  className?: string
  placeholder?: string
  required?: boolean
  ariaLabel?: string
}) {
  const [suggestions, setSuggestions] = useState<LocationSuggestion[]>([])
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const listId = useId()

  // One token per search: it starts with the first keystroke and ends with a
  // pick, so Google bills the keystrokes and the pick as a single lookup.
  const sessionRef = useRef<string | null>(null)
  const debounceRef = useRef<number | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const valueRef = useRef(value)

  useEffect(() => {
    valueRef.current = value
  }, [value])

  const cancelPending = () => {
    if (debounceRef.current != null) window.clearTimeout(debounceRef.current)
    debounceRef.current = null
    abortRef.current?.abort()
    abortRef.current = null
  }

  useEffect(() => cancelPending, [])

  const close = () => {
    setOpen(false)
    setActiveIndex(-1)
  }

  const handleType = (text: string) => {
    onChange(text)
    cancelPending()
    const query = text.trim()
    if (query.length < MIN_CHARS) {
      setSuggestions([])
      close()
      return
    }
    debounceRef.current = window.setTimeout(async () => {
      const controller = new AbortController()
      abortRef.current = controller
      sessionRef.current ??= newSessionToken()
      try {
        const found = await fetchLocationSuggestions(
          query,
          sessionRef.current,
          controller.signal,
        )
        if (controller.signal.aborted) return
        setSuggestions(found)
        setActiveIndex(-1)
        setOpen(found.length > 0)
      } catch {
        // No suggestions is fine: the typed text is still searched.
        if (!controller.signal.aborted) {
          setSuggestions([])
          close()
        }
      }
    }, DEBOUNCE_MS)
  }

  const pick = (suggestion: LocationSuggestion) => {
    const label = suggestionLabel(suggestion)
    const session = sessionRef.current ?? newSessionToken()
    sessionRef.current = null
    cancelPending()
    setSuggestions([])
    close()
    onChange(label)
    fetchSuggestionLocation(suggestion.place_id, session)
      .then((coords) => {
        if (valueRef.current === label) onResolve({ ...coords, label })
      })
      .catch(() => {
        // The label alone is still a searchable location.
      })
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (suggestions.length === 0) return
      event.preventDefault()
      const step = event.key === 'ArrowDown' ? 1 : -1
      setOpen(true)
      const count = suggestions.length
      setActiveIndex((current) => {
        if (!open || current < 0) return step === 1 ? 0 : count - 1
        return (current + step + count) % count
      })
    } else if (event.key === 'Enter') {
      if (open && activeIndex >= 0) {
        event.preventDefault()
        pick(suggestions[activeIndex])
      }
    } else if (event.key === 'Escape') {
      if (open) {
        // Close the list only; the sheet this field sits in stays open.
        event.stopPropagation()
        close()
      }
    }
  }

  const optionId = (index: number) => `${listId}-option-${index}`

  return (
    <div className="loc-field">
      <input
        ref={inputRef}
        id={id}
        className={className}
        type="text"
        placeholder={placeholder}
        value={value}
        required={required}
        autoComplete="off"
        role="combobox"
        aria-label={ariaLabel}
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={
          open && activeIndex >= 0 ? optionId(activeIndex) : undefined
        }
        onChange={(event) => handleType(event.target.value)}
        onKeyDown={handleKeyDown}
        onFocus={() => {
          if (suggestions.length > 0) setOpen(true)
        }}
        onBlur={close}
      />
      {open && (
        <ul id={listId} className="loc-suggest" role="listbox">
          {suggestions.map((suggestion, index) => (
            <li
              key={suggestion.place_id}
              id={optionId(index)}
              role="option"
              aria-selected={index === activeIndex}
              className={`loc-suggest-item${index === activeIndex ? ' loc-suggest-item--active' : ''}`}
              // Keep focus in the field so the tap lands before blur closes the list.
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => pick(suggestion)}
            >
              <PinIcon />
              <span className="loc-suggest-text">
                <span className="loc-suggest-main">{suggestion.main_text}</span>
                {suggestion.secondary_text && (
                  <span className="loc-suggest-secondary">
                    {suggestion.secondary_text}
                  </span>
                )}
              </span>
            </li>
          ))}
          {/* Attribution Google requires wherever its suggestions are shown. */}
          <li className="loc-suggest-credit" role="presentation" translate="no">
            Google Maps
          </li>
        </ul>
      )}
    </div>
  )
}
