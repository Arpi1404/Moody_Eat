import { useCallback, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  NameSearchError,
  searchNearbyPlaces,
  searchPlacesByName,
  type PlaceItem,
} from '../api'
import { LocationInput } from '../components/LocationInput'
import { PlaceLink } from '../components/PlaceLink'
import { track } from '../lib/analytics'
import { formatInrEstimate } from '../lib/budget'
import { CREATOR_INTRO_MAX, CREATOR_NOTE_MAX, tidyText } from '../lib/creatorText'
import {
  areaKey,
  COORDINATES_RE,
  nameSearchAnchor,
  type ResolvedArea,
} from '../lib/nameSearchArea'
import { shortAddresses } from '../lib/placeAddress'
import { buildCustomQuest } from '../lib/questBuild'
import type { DayPart, Occasion } from '../types/quest'
import '../App.css'

const MAX_STOPS = 4
const MIN_NAME_CHARS = 3

type NameSearch =
  | { status: 'idle' }
  | { status: 'searching' }
  | { status: 'done'; places: PlaceItem[]; area: string }
  | { status: 'error'; message: string }

const NAME_SEARCH_ERRORS = {
  area_not_found:
    'We couldn\'t find that area. Pick one from the suggestions under “Where?”.',
  too_many:
    'That\'s a lot of searches at once. Wait a minute, or browse by category below.',
  unavailable:
    'Search by name isn\'t working right now. You can still browse by category below.',
}

function nameSearchStatusText(search: NameSearch): string {
  if (search.status === 'searching') return 'Searching…'
  if (search.status === 'error') return search.message
  if (search.status === 'idle') return ''
  const count = search.places.length
  if (count === 0) {
    return `No place by that name near ${search.area}. Check the spelling, or change the area.`
  }
  return `${count} ${count === 1 ? 'place' : 'places'} near ${search.area}`
}

const OCCASION_OPTIONS: { value: Occasion; label: string; emoji: string }[] = [
  { value: 'date', label: 'Date', emoji: '🕯️' },
  { value: 'friends', label: 'Friends', emoji: '🥂' },
  { value: 'solo', label: 'Solo', emoji: '🍵' },
  { value: 'family', label: 'Family', emoji: '🧆' },
]

const DAY_PART_OPTIONS: { value: DayPart; label: string }[] = [
  { value: 'morning', label: 'Morning' },
  { value: 'afternoon', label: 'Afternoon' },
  { value: 'evening', label: 'Evening' },
  { value: 'night', label: 'Night' },
]

const DAY_PART_DEFAULT_BY_OCCASION: Record<Occasion, DayPart> = {
  date: 'evening',
  friends: 'night',
  solo: 'morning',
  family: 'afternoon',
}

const SEARCH_CATEGORIES: { type: string; label: string }[] = [
  { type: 'restaurant', label: 'Restaurants' },
  { type: 'cafe', label: 'Cafés' },
  { type: 'bar', label: 'Bars' },
  { type: 'bakery', label: 'Bakeries' },
  { type: 'night_club', label: 'Clubs' },
  { type: 'park', label: 'Parks' },
  { type: 'tourist_attraction', label: 'Sights' },
  { type: 'museum', label: 'Museums' },
  { type: 'art_gallery', label: 'Galleries' },
  { type: 'shopping_mall', label: 'Malls' },
  { type: 'movie_theater', label: 'Movies' },
  { type: 'bowling_alley', label: 'Bowling' },
]

function distanceLabel(meters: number): string {
  if (meters < 1000) return `${Math.round(meters)}m`
  return `${(meters / 1000).toFixed(1)}km`
}

/** One search result with its Add button, from either kind of search. */
function ResultCard({
  place,
  address,
  added,
  questFull,
  onAdd,
}: {
  place: PlaceItem
  /** Shown for name results, where two branches can share a name. */
  address?: string
  added: boolean
  questFull: boolean
  onAdd: (place: PlaceItem) => void
}) {
  const priceLabel = formatInrEstimate(
    place.price_range_start_inr,
    place.price_range_end_inr,
  )
  const spoken = address ? `${place.name}, ${address}` : place.name
  return (
    <li className="cq-result-card">
      <div className="cq-result-info">
        <p className="cq-result-name">
          <PlaceLink place={place} surface="create" />
        </p>
        {address && <p className="cq-result-address">{address}</p>}
        <p className="cq-result-meta">
          {place.rating != null && (
            <>★ {place.rating.toFixed(1)}
              {place.user_ratings_total != null && (
                <span> ({place.user_ratings_total.toLocaleString()})</span>
              )}
              {' · '}
            </>
          )}
          {distanceLabel(place.distance_meters)}
          {priceLabel && <> · {priceLabel}</>}
        </p>
      </div>
      <button
        type="button"
        className={`cq-add-btn${added ? ' cq-add-btn--added' : ''}`}
        aria-label={added ? `Added: ${spoken}` : `Add ${spoken}`}
        disabled={added || questFull}
        title={
          questFull && !added
            ? `Quest is full (${MAX_STOPS} stops max)`
            : undefined
        }
        onClick={() => onAdd(place)}
      >
        {added ? '✓ Added' : '+ Add'}
      </button>
    </li>
  )
}

/** A text box for the creator's own words, with its running count. It lets
 * text run over and says so: a length cap on the box would cut a paste short
 * without a word. */
function CreatorTextField({
  id,
  label,
  value,
  max,
  placeholder,
  autoFocus,
  onChange,
}: {
  id: string
  label: string
  value: string
  max: number
  placeholder: string
  autoFocus: boolean
  onChange: (value: string) => void
}) {
  // Counted as it will be saved: trimmed, on one line.
  const length = tidyText(value).length
  const over = length > max
  return (
    <div className="cq-words-field">
      <label htmlFor={id}>{label}</label>
      <textarea
        id={id}
        rows={3}
        value={value}
        placeholder={placeholder}
        autoFocus={autoFocus}
        aria-describedby={`${id}-count`}
        aria-invalid={over || undefined}
        onChange={(e) => onChange(e.target.value)}
      />
      <p
        id={`${id}-count`}
        className={`cq-count${over ? ' cq-count--over' : ''}`}
      >
        {length}/{max}
        {over && ` · ${length - max} too many`}
      </p>
    </div>
  )
}

export function CreateQuestPage() {
  const navigate = useNavigate()
  const [occasion, setOccasion] = useState<Occasion>('friends')
  const [dayPartChoice, setDayPartChoice] = useState<DayPart | null>(null)
  const [location, setLocation] = useState('')
  // Set while the field holds a picked suggestion: places are searched around
  // its coordinates and the field's text is its label. Typing clears it.
  const [picked, setPicked] = useState<{
    lat: number
    lng: number
    label: string
  } | null>(null)
  const [geoLoading, setGeoLoading] = useState(false)
  const [activeType, setActiveType] = useState<string | null>(null)
  const [results, setResults] = useState<PlaceItem[]>([])
  const [resolvedArea, setResolvedArea] = useState('')
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [selected, setSelected] = useState<PlaceItem[]>([])
  const [creatorName, setCreatorName] = useState('')
  const [intro, setIntro] = useState('')
  // Notes are kept by place id and outlive removing a stop, so adding it back
  // brings its note back.
  const [notes, setNotes] = useState<Record<string, string>>({})
  // The note or intro box just opened with its button: it takes focus.
  const [openedField, setOpenedField] = useState<string | null>(null)
  const [nameQuery, setNameQuery] = useState('')
  const [nameSearch, setNameSearch] = useState<NameSearch>({ status: 'idle' })
  // Goes up whenever a name search starts or stops mattering, so a late answer
  // is dropped.
  const nameRequestRef = useRef(0)
  // Typed areas the server has geocoded for a name search, so that searching
  // one again does not pay for it again. Kept only while the page is open.
  const geocodedAreasRef = useRef(new Map<string, ResolvedArea>())

  const dayPart = dayPartChoice ?? DAY_PART_DEFAULT_BY_OCCASION[occasion]
  const selectedIds = new Set(selected.map((p) => p.provider_id))
  const questFull = selected.length >= MAX_STOPS
  const wordsTooLong =
    tidyText(intro).length > CREATOR_INTRO_MAX ||
    selected.some(
      (p) => tidyText(notes[p.provider_id] ?? '').length > CREATOR_NOTE_MAX,
    )
  const nameAddresses =
    nameSearch.status === 'done'
      ? shortAddresses(nameSearch.places.map((p) => p.address))
      : []

  /** Name results belong to one area: changing it, or browsing by category,
   * puts them away. */
  const clearNameSearch = useCallback(() => {
    nameRequestRef.current += 1
    setNameSearch({ status: 'idle' })
  }, [])

  // A failure here is kept to this search: category results and the pills
  // carry on as they were.
  const runNameSearch = async (event: FormEvent) => {
    event.preventDefault()
    if (nameSearch.status === 'searching' || searching) return
    const text = nameQuery.trim().replace(/\s+/g, ' ')
    const typedArea = location.trim()
    const problem = !typedArea
      ? 'Pick an area under “Where?” first, then search.'
      : text.length < MIN_NAME_CHARS
        ? `Type at least ${MIN_NAME_CHARS} characters of the name.`
        : null
    if (problem) {
      setNameSearch({ status: 'error', message: problem })
      return
    }
    const area =
      picked?.label ??
      (COORDINATES_RE.test(typedArea) ? 'your location' : typedArea)
    const requestId = ++nameRequestRef.current
    setNameSearch({ status: 'searching' })
    const { send, knownName } = nameSearchAnchor(
      typedArea,
      picked,
      geocodedAreasRef.current,
    )
    try {
      const res = await searchPlacesByName({ q: text, ...send })
      // Worth keeping even if this answer is too late to show.
      if ('area' in send) {
        geocodedAreasRef.current.set(areaKey(typedArea), res.resolved_location)
      }
      if (nameRequestRef.current !== requestId) return
      // The count only: what was typed never goes to analytics.
      track('create_name_search', { result_count: res.places.length })
      // One list at a time, but a search that found nothing replaces nothing.
      if (res.places.length > 0) {
        setResults([])
        setSearchError(null)
        setActiveType(null)
        // Names the quest. Empty for the 📍 position, which nothing has
        // named: "your location" is for the messages only.
        setResolvedArea(
          res.resolved_location.name || knownName || picked?.label || '',
        )
      }
      setNameSearch({ status: 'done', places: res.places, area })
    } catch (err) {
      if (nameRequestRef.current !== requestId) return
      const reason = err instanceof NameSearchError ? err.reason : 'unavailable'
      setNameSearch({ status: 'error', message: NAME_SEARCH_ERRORS[reason] })
    }
  }

  const runSearch = useCallback(
    async (type: string) => {
      if (!location.trim() || searching) return
      clearNameSearch()
      setActiveType(type)
      setSearching(true)
      setSearchError(null)
      try {
        const res = await searchNearbyPlaces({
          query: picked
            ? `${picked.lat.toFixed(5)},${picked.lng.toFixed(5)}`
            : location.trim(),
          categories: [type],
          radius_meters: 3000,
          limit: 12,
        })
        setResults(res.places)
        setResolvedArea(res.resolved_location.name)
        if (res.places.length === 0) {
          setSearchError('No good matches for that category here — try another.')
        }
      } catch (err) {
        setResults([])
        setSearchError(
          err instanceof Error ? err.message : 'Search failed — try again.',
        )
      } finally {
        setSearching(false)
      }
    },
    [clearNameSearch, location, picked, searching],
  )

  const useMyLocation = () => {
    if (!navigator.geolocation || geoLoading) return
    setGeoLoading(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        // Three decimals (about 100 m) is all a search needs, and is what
        // the privacy page promises.
        setLocation(`${pos.coords.latitude.toFixed(3)},${pos.coords.longitude.toFixed(3)}`)
        setPicked(null)
        clearNameSearch()
        setGeoLoading(false)
      },
      () => {
        setSearchError('Could not read your location — type an area instead.')
        setGeoLoading(false)
      },
      { timeout: 8000 },
    )
  }

  const addPlace = (place: PlaceItem) => {
    if (questFull || selectedIds.has(place.provider_id)) return
    setSelected((prev) => [...prev, place])
  }

  const removePlace = (providerId: string) => {
    if (openedField === providerId) setOpenedField(null)
    setSelected((prev) => prev.filter((p) => p.provider_id !== providerId))
  }

  const movePlace = (index: number, delta: number) => {
    setSelected((prev) => {
      const to = index + delta
      if (to < 0 || to >= prev.length) return prev
      const next = [...prev]
      const [moved] = next.splice(index, 1)
      next.splice(to, 0, moved)
      return next
    })
  }

  const handleCreate = () => {
    if (selected.length === 0 || wordsTooLong) return
    // A coordinate search resolves to a street address; the picked label
    // ("Banjara Hills, Hyderabad") is the better name for the quest.
    const area = picked?.label || resolvedArea || location.trim()
    const quest = buildCustomQuest({
      places: selected,
      occasion,
      dayPart,
      // Raw coordinates must never reach a title or a shared link.
      area: COORDINATES_RE.test(area) ? '' : area,
      createdBy: creatorName.trim() || undefined,
      intro,
      notes,
    })
    track('custom_quest_created', {
      stop_count: selected.length,
      occasion,
      day_part: dayPart,
      // Booleans and counts only — no name, note or intro ever goes here.
      has_creator_name: Boolean(creatorName.trim()),
      has_intro: Boolean(quest.narrative_by_creator),
      note_count: quest.stops.filter((s) => s.note_by_creator).length,
    })
    localStorage.setItem(`quest_${quest.id}`, JSON.stringify(quest))
    navigate(`/quest/${quest.id}`, { state: { quest, justCreated: true } })
  }

  return (
    <main className="cq-page">
      <div className="cq-inner">
        <Link to="/" className="qp-back-link">
          <span aria-hidden>←</span> Back to home
        </Link>

        <header className="cq-header">
          <h1>Build your own quest</h1>
          <p>
            Pick 1–{MAX_STOPS} places — we'll map the route, time the stops,
            and make it shareable.
          </p>
        </header>

        <div className="cq-controls">
          <div>
            <span className="sheet-field-label">Occasion</span>
            <div className="sheet-pill-row" role="group" aria-label="Occasion">
              {OCCASION_OPTIONS.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  className={`sheet-pill${occasion === o.value ? ' sheet-pill--active' : ''}`}
                  aria-pressed={occasion === o.value}
                  onClick={() => setOccasion(o.value)}
                >
                  <span aria-hidden style={{ marginRight: 6 }}>{o.emoji}</span>
                  {o.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <span className="sheet-field-label">When?</span>
            <div className="sheet-pill-row" role="group" aria-label="Time of day">
              {DAY_PART_OPTIONS.map((d) => (
                <button
                  key={d.value}
                  type="button"
                  className={`sheet-pill${dayPart === d.value ? ' sheet-pill--active' : ''}`}
                  aria-pressed={dayPart === d.value}
                  onClick={() => setDayPartChoice(d.value)}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <span className="sheet-field-label">Where?</span>
            <div className="cq-location-row">
              <LocationInput
                className="cq-location-input"
                value={location}
                onChange={(text) => {
                  setLocation(text)
                  setPicked(null)
                  clearNameSearch()
                }}
                onResolve={setPicked}
                placeholder="City, neighbourhood, or area"
                ariaLabel="Location"
              />
              <button
                type="button"
                className="cq-geo-btn"
                onClick={useMyLocation}
                disabled={geoLoading}
                title="Use my current location"
              >
                {geoLoading ? '…' : '📍'}
              </button>
            </div>
          </div>

          <div>
            <label className="sheet-field-label" htmlFor="cq-creator-name">
              Made by <span className="cq-optional">(optional)</span>
            </label>
            <input
              id="cq-creator-name"
              className="cq-location-input"
              value={creatorName}
              onChange={(e) => setCreatorName(e.target.value)}
              placeholder="Your name or IG handle"
              maxLength={40}
              autoComplete="off"
            />
            <p className="cq-hint">
              Put your name on it — shown on the quest page and the share card.
            </p>
          </div>

          <div>
            <form role="search" onSubmit={runNameSearch}>
              <label className="sheet-field-label" htmlFor="cq-name-search">
                Search by name
              </label>
              <div className="cq-location-row">
                <input
                  id="cq-name-search"
                  type="search"
                  className="cq-location-input cq-name-input"
                  value={nameQuery}
                  onChange={(e) => {
                    setNameQuery(e.target.value)
                    // The field's own clear button empties it in one go.
                    if (!e.target.value) clearNameSearch()
                  }}
                  placeholder="A spot you already love"
                  maxLength={120}
                  autoComplete="off"
                  enterKeyHint="search"
                />
                <button
                  type="submit"
                  className="cq-search-btn"
                  disabled={searching || nameSearch.status === 'searching'}
                >
                  Search
                </button>
              </div>
            </form>
            {!location.trim() && (
              <p className="cq-hint">
                Pick an area under “Where?” first, then search by name or tap a
                category.
              </p>
            )}
            {/* Always here, so screen readers hear it change. */}
            <p
              className={`cq-name-status ${nameSearch.status === 'error' ? 'cq-error' : 'cq-hint'}`}
              role="status"
            >
              {nameSearchStatusText(nameSearch)}
            </p>
            {nameSearch.status === 'done' && nameSearch.places.length > 0 && (
              <section className="cq-results" aria-label="Places found by name">
                <ul>
                  {nameSearch.places.map((place, i) => (
                    <ResultCard
                      key={place.provider_id}
                      place={place}
                      address={nameAddresses[i]}
                      added={selectedIds.has(place.provider_id)}
                      questFull={questFull}
                      onAdd={addPlace}
                    />
                  ))}
                </ul>
                {/* Attribution Google requires for results shown without its map. */}
                <p className="loc-suggest-credit" translate="no">
                  Google Maps
                </p>
              </section>
            )}
          </div>

          <div>
            <span className="sheet-field-label">Or browse by category</span>
            <div className="cq-category-row" role="group" aria-label="Place category">
              {SEARCH_CATEGORIES.map((c) => (
                <button
                  key={c.type}
                  type="button"
                  className={`sheet-pill cq-category-pill${activeType === c.type ? ' sheet-pill--active' : ''}`}
                  aria-pressed={activeType === c.type}
                  disabled={!location.trim() || searching}
                  onClick={() => runSearch(c.type)}
                >
                  {c.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {selected.length > 0 && (
          <section className="cq-selected" aria-label="Your stops">
            <span className="sheet-field-label">
              Your stops ({selected.length}/{MAX_STOPS})
            </span>
            <ol className="cq-selected-list">
              {selected.map((place, i) => (
                <li key={place.provider_id} className="cq-selected-item">
                  <span className="cq-selected-index" aria-hidden>{i + 1}</span>
                  <span className="cq-selected-name">
                    <PlaceLink place={place} surface="create" />
                  </span>
                  <span className="cq-selected-actions">
                    <button
                      type="button"
                      aria-label={`Move ${place.name} earlier`}
                      disabled={i === 0}
                      onClick={() => movePlace(i, -1)}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      aria-label={`Move ${place.name} later`}
                      disabled={i === selected.length - 1}
                      onClick={() => movePlace(i, 1)}
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      aria-label={`Remove ${place.name}`}
                      onClick={() => removePlace(place.provider_id)}
                    >
                      ✕
                    </button>
                  </span>
                  <div className="cq-selected-words">
                    {openedField === place.provider_id ||
                    notes[place.provider_id] ? (
                      <CreatorTextField
                        id={`cq-note-${place.provider_id}`}
                        label={`Why ${place.name}?`}
                        value={notes[place.provider_id] ?? ''}
                        max={CREATOR_NOTE_MAX}
                        placeholder="What to order, where to sit, when to go"
                        autoFocus={openedField === place.provider_id}
                        onChange={(value) =>
                          setNotes((prev) => ({
                            ...prev,
                            [place.provider_id]: value,
                          }))
                        }
                      />
                    ) : (
                      <button
                        type="button"
                        className="cq-words-btn"
                        aria-label={`Add a note about ${place.name}`}
                        onClick={() => setOpenedField(place.provider_id)}
                      >
                        ✎ Add a note
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ol>
            <div className="cq-intro">
              {openedField === 'intro' || intro ? (
                <CreatorTextField
                  id="cq-intro"
                  label="Your intro"
                  value={intro}
                  max={CREATOR_INTRO_MAX}
                  placeholder="What is this quest for, and who will love it?"
                  autoFocus={openedField === 'intro'}
                  onChange={setIntro}
                />
              ) : (
                <button
                  type="button"
                  className="cq-words-btn"
                  onClick={() => setOpenedField('intro')}
                >
                  ✎ Add an intro
                </button>
              )}
            </div>
            <p className="cq-hint">
              Optional. Your words replace our automatic lines, and anyone with
              your share link can read them.
            </p>
          </section>
        )}

        {searching && <p className="cq-hint">Finding good spots…</p>}
        {searchError && !searching && <p className="cq-error">{searchError}</p>}

        {results.length > 0 && !searching && (
          <section className="cq-results" aria-label="Search results">
            <ul>
              {results.map((place) => (
                <ResultCard
                  key={place.provider_id}
                  place={place}
                  added={selectedIds.has(place.provider_id)}
                  questFull={questFull}
                  onAdd={addPlace}
                />
              ))}
            </ul>
          </section>
        )}
      </div>

      <div className="cq-create-bar">
        <button
          type="button"
          className="cq-create-btn"
          disabled={selected.length === 0 || wordsTooLong}
          onClick={handleCreate}
        >
          {wordsTooLong
            ? 'Shorten your words to create'
            : `Create quest${selected.length > 0 ? ` (${selected.length} stop${selected.length === 1 ? '' : 's'})` : ''} ✦`}
        </button>
      </div>
    </main>
  )
}

export default CreateQuestPage
