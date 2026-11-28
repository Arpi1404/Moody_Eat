// The intro after a swap, add, remove or reorder. Run with `npm test`.
import assert from 'node:assert/strict'
import test from 'node:test'
import { loadSource } from './loadSource.mjs'

const { narrativeAfterEdit } = await loadSource('lib/narrative.ts')
const { buildCustomQuest, replaceStop } = await loadSource('lib/questBuild.ts')

const stop = (name, start = '17:30:00') => ({
  place: { provider_id: `id-${name}`, name },
  time_block_start: start,
})

const quest = (narrative, names, extra = {}) => ({
  occasion: 'date',
  total_cost_estimate: 'mid',
  narrative,
  stops: names.map((name) => stop(name)),
  ...extra,
})

/** `previous` with other stops, as an edit hands it over. */
const edited = (previous, names) => ({
  ...previous,
  stops: names.map((name) => stop(name)),
})

const after = (previous, names) => narrativeAfterEdit(previous, edited(previous, names))

test('a swap keeps the area', () => {
  const before = quest(
    'An evening date in Old Town: start at A, move on to B, then finish at C.',
    ['A', 'B', 'C'],
  )
  assert.equal(
    after(before, ['A', 'D', 'C']),
    'An evening date in Old Town: start at A, move on to D, then finish at C.',
  )
})

test('the area survives one edit after another, down to one stop and back', () => {
  let current = quest('An evening date in Old Town: start at A, then finish at B.', ['A', 'B'])
  for (const names of [['A'], ['A', 'C'], ['A', 'C', 'D', 'E'], ['E', 'A']]) {
    const next = edited(current, names)
    current = { ...next, narrative: narrativeAfterEdit(current, next) }
    assert.match(current.narrative, /^An evening date in Old Town[:,] /)
  }
  assert.equal(current.narrative, 'An evening date in Old Town: start at E, then finish at A.')
})

test('every phrase the server can open with gives up its area', () => {
  for (const lead of [
    'A date',
    'A date night',
    'A budget-friendly solo morning',
    'A splurge-worthy night out with friends',
    'An afternoon out with friends',
    'A family outing',
    'An outing with friends',
  ]) {
    const before = quest(`${lead} in Old Town: start at A, then finish at B.`, ['A', 'B'])
    assert.match(after(before, ['A', 'C']), / in Old Town: /, lead)
  }
})

test('an area with commas, colons or "in" in it is kept whole', () => {
  for (const area of ['Sector 5, North Side', 'Inn Lane', 'Block A: East', 'Baker in the Wall']) {
    const before = quest(`An evening date in ${area}, built around A.`, ['A'])
    assert.equal(after(before, ['B']), `An evening date in ${area}, built around B.`)
  }
})

test('stop names that look like the sentence do not confuse it', () => {
  const odd = 'Cafe: start at Noon, then finish'
  const before = quest(`An evening date in Old Town: start at ${odd}, then finish at B.`, [odd, 'B'])
  assert.equal(
    after(before, [odd, 'C']),
    `An evening date in Old Town: start at ${odd}, then finish at C.`,
  )
})

test('doubled spaces in a stop name still match the stored sentence', () => {
  // The server closes them up in the narrative and keeps them in the name.
  const before = quest('An evening date in Old Town, built around The Nook.', ['The  Nook'])
  assert.equal(after(before, ['B']), 'An evening date in Old Town, built around B.')
})

test('a quest built by hand keeps its area too', () => {
  const place = (id) => ({ provider_id: id, name: id, address: '', lat: 0, lng: 0, types: ['cafe'] })
  for (const ids of [['A'], ['A', 'B', 'C']]) {
    const built = buildCustomQuest({
      places: ids.map(place),
      occasion: 'solo',
      dayPart: 'morning',
      area: 'Old Town, Riverside',
    })
    const swapped = replaceStop(built, 0, { ...built.stops[0], place: place('Z') })
    assert.match(narrativeAfterEdit(built, swapped), / in Old Town[:,] /)
  }
})

test('a sentence with no area stays without one', () => {
  const before = quest('An evening date: start at A, then finish at B.', ['A', 'B'])
  assert.equal(after(before, ['A', 'C']), 'An evening date: start at A, then finish at C.')
})

test("prose we did not write lends no area", () => {
  for (const prose of [
    'Wander in the old lanes: start at A, then finish at B.',
    'Begin your evening in the hills with coffee, then head out.',
    // Ours in shape, but not about these stops.
    'An evening date in Old Town: start at X, then finish at Y.',
  ]) {
    assert.equal(
      after(quest(prose, ['A', 'B']), ['A', 'C']),
      'An evening date: start at A, then finish at C.',
      prose,
    )
  }
})

test("a creator's own intro is never rewritten", () => {
  const typed = 'An evening date in Old Town: start at A, then finish at B.'
  for (const intro of [typed, 'My favourite night.']) {
    const before = quest(intro, ['A', 'B'], { narrative_by_creator: true })
    assert.equal(after(before, ['C', 'D']), intro)
    assert.equal(after(before, ['A']), intro)
  }
})

test('the intro stays as it is when the stops do not change', () => {
  const before = quest('Anything at all.', ['A', 'B'])
  assert.equal(after(before, ['A', 'B']), 'Anything at all.')
})
