// The schedule maths behind editing a quest. Run with `npm test`.
//
import assert from 'node:assert/strict'
import test from 'node:test'
import { loadSource } from './loadSource.mjs'

const {
  FILM_MINUTES,
  addMinutes,
  buildCustomQuest,
  durationMinutes,
  insertStopAfter,
  removeStop,
  reorderStops,
  replaceStop,
  travelLeg,
} = await loadSource('lib/questBuild.ts')

/** A place `km` north of the origin. */
const place = (id, km, types = ['cafe']) => ({
  provider_id: id,
  name: id,
  address: '',
  lat: km / 111.195,
  lng: 0,
  distance_meters: 0,
  types,
})

const stop = (id, km, start, end, minutes = null, mode = null) => ({
  place: place(id, km),
  category: 'cafe',
  time_block_start: `${start}:00`,
  time_block_end: `${end}:00`,
  travel_to_next_minutes: minutes,
  travel_mode: mode,
  why_this_place: 'A good one.',
})

/** Four stops 2 km apart with hand-written hops. Geometry would call every one
 * of them a 6 minute drive, so a hop that was kept is easy to tell from one
 * that was worked out again. */
const handMade = () => ({
  id: 'q',
  title: 't',
  occasion: 'date',
  stops: [
    stop('a', 0, '17:00', '17:30', 21, 'walking'),
    stop('b', 2, '17:51', '18:51', 22, 'walking'),
    stop('c', 4, '19:13', '19:43', 23, 'walking'),
    stop('d', 6, '20:06', '20:46'),
  ],
  total_duration_minutes: 226,
  total_cost_estimate: 'mid',
  narrative: '',
  created_at: '',
})

const newStop = (id, km) => stop(id, km, '00:00', '00:40')

const hops = (quest) =>
  quest.stops
    .slice(0, -1)
    .map(
      (from, i) =>
        `${from.place.provider_id}>${quest.stops[i + 1].place.provider_id} ` +
        `${from.travel_to_next_minutes} ${from.travel_mode}`,
    )

const computed = (quest, i) => {
  const leg = travelLeg(quest.stops[i], quest.stops[i + 1])
  return `${quest.stops[i].place.provider_id}>${quest.stops[i + 1].place.provider_id} ${leg.minutes} ${leg.mode}`
}

/** Starts at the same time, and every stop begins one hop after the last ends. */
function assertChains(quest) {
  assert.equal(quest.stops[0].time_block_start, '17:00:00')
  for (let i = 0; i + 1 < quest.stops.length; i += 1) {
    assert.equal(
      quest.stops[i + 1].time_block_start,
      addMinutes(quest.stops[i].time_block_end, quest.stops[i].travel_to_next_minutes),
      `start of stop ${i + 2}`,
    )
  }
  const last = quest.stops.at(-1)
  assert.equal(last.travel_to_next_minutes, null)
  assert.equal(last.travel_mode, null)
  assert.equal(
    quest.total_duration_minutes,
    durationMinutes('17:00:00', last.time_block_end),
  )
}

test('removing a middle stop works out only the hop that joins its neighbours', () => {
  const quest = removeStop(handMade(), 1)

  assert.deepEqual(hops(quest), [computed(quest, 0), 'c>d 23 walking'])
  assert.equal(computed(quest, 0), 'a>c 11 driving')
  assertChains(quest)
})

test('removing the first stop keeps the other hops and the start time', () => {
  const quest = removeStop(handMade(), 0)

  assert.deepEqual(hops(quest), ['b>c 22 walking', 'c>d 23 walking'])
  assertChains(quest)
})

test('removing the last stop moves nothing before it', () => {
  const before = handMade()
  const quest = removeStop(before, 3)

  assert.deepEqual(hops(quest), ['a>b 21 walking', 'b>c 22 walking'])
  assert.deepEqual(
    quest.stops.map((s) => s.time_block_start),
    before.stops.slice(0, 3).map((s) => s.time_block_start),
  )
  assertChains(quest)
})

test('adding a stop works out the hops to and from it, and no others', () => {
  const quest = insertStopAfter(handMade(), 1, newStop('new', 3))

  assert.deepEqual(hops(quest), [
    'a>b 21 walking',
    computed(quest, 1),
    computed(quest, 2),
    'c>d 23 walking',
  ])
  assertChains(quest)
})

test('adding at the end keeps every existing hop', () => {
  const quest = insertStopAfter(removeStop(handMade(), 3), 2, newStop('new', 6))

  assert.deepEqual(hops(quest).slice(0, 2), ['a>b 21 walking', 'b>c 22 walking'])
  assert.equal(hops(quest)[2], computed(quest, 2))
  assertChains(quest)
})

test('swapping a stop works out the two hops beside it', () => {
  const quest = replaceStop(handMade(), 2, newStop('new', 4.2))

  assert.deepEqual(hops(quest), ['a>b 21 walking', computed(quest, 1), computed(quest, 2)])
  assertChains(quest)
})

test('swapping the first stop keeps the start time and the later hops', () => {
  const replacement = stop('new', 0.1, '17:00', '17:30')
  const quest = replaceStop(handMade(), 0, replacement)

  assert.deepEqual(hops(quest), [computed(quest, 0), 'b>c 22 walking', 'c>d 23 walking'])
  assertChains(quest)
})

test('reordering keeps hops between stops that stay neighbours, either way round', () => {
  // a b c d -> b a c d: a and b only change places; a>c is new.
  const quest = reorderStops(handMade(), 1, 0)

  assert.deepEqual(hops(quest), ['b>a 21 walking', computed(quest, 1), 'c>d 23 walking'])
  assertChains(quest)
})

test('a hop with no stored time is worked out', () => {
  const before = handMade()
  before.stops[2] = { ...before.stops[2], travel_to_next_minutes: null, travel_mode: null }

  const quest = removeStop(before, 0)

  assert.deepEqual(hops(quest), ['b>c 22 walking', computed(quest, 1)])
  assertChains(quest)
})

test('the hand-written walk from Charminar to Hotel Shadab survives edits', () => {
  const at = (id, lat, lng, minutes = null, mode = null) => ({
    ...stop(id, 0, '17:00', '17:30', minutes, mode),
    place: { ...place(id, 0), lat, lng },
  })
  // The curated stops, 816 m apart in a straight line: past the walking limit.
  const charminar = at('charminar', 17.3616, 78.4747, 10, 'walking')
  const shadab = at('shadab', 17.3689, 78.4755, 11, 'walking')
  assert.equal(travelLeg(charminar, shadab).mode, 'driving')

  const quest = {
    ...handMade(),
    stops: [charminar, shadab, at('nimrah', 17.3614, 78.4741)],
  }
  const another = at('new', 17.365, 78.476)
  const edits = {
    'add after the second stop': insertStopAfter(quest, 1, another),
    'add at the end': insertStopAfter(quest, 2, another),
    'swap the last stop': replaceStop(quest, 2, another),
    'remove the last stop': removeStop(quest, 2),
    'move the last stop first': reorderStops(quest, 2, 0),
    'swap the two around': reorderStops(quest, 1, 0),
  }

  for (const [edit, edited] of Object.entries(edits)) {
    const from = edited.stops.findIndex(
      (s, i) =>
        ['charminar', 'shadab'].includes(s.place.provider_id) &&
        ['charminar', 'shadab'].includes(edited.stops[i + 1]?.place.provider_id),
    )
    assert.notEqual(from, -1, edit)
    assert.equal(edited.stops[from].travel_to_next_minutes, 10, edit)
    assert.equal(edited.stops[from].travel_mode, 'walking', edit)
  }
})

test('an edit leaves the quest it was made from untouched', () => {
  const before = handMade()
  const copy = structuredClone(before)

  removeStop(before, 1)
  insertStopAfter(before, 0, newStop('new', 1))
  replaceStop(before, 1, newStop('other', 2.5))
  reorderStops(before, 0, 2)

  assert.deepEqual(before, copy)
})

test('a film on a hand-built quest gets a film’s length, other activities do not', () => {
  const quest = buildCustomQuest({
    places: [
      place('film', 0, ['movie_theater', 'point_of_interest']),
      place('lanes', 0.1, ['bowling_alley']),
      // A mall with screens is still a mall.
      place('mall', 0.2, ['shopping_mall', 'movie_theater']),
    ],
    occasion: 'friends',
    dayPart: 'evening',
    area: '',
  })

  assert.deepEqual(
    quest.stops.map((s) => durationMinutes(s.time_block_start, s.time_block_end)),
    [FILM_MINUTES, 60, 60],
  )
})
