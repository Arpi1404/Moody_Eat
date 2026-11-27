// A creator's own words must come through every edit unchanged.

import assert from 'node:assert/strict'
import test from 'node:test'
import { loadSource } from './loadSource.mjs'

const { tidyText, withoutLinks } = await loadSource('lib/creatorText.ts')
const { buildCustomQuest, insertStopAfter, removeStop, reorderStops, replaceStop } =
  await loadSource('lib/questBuild.ts')

/** A place `km` north of the origin. */
const place = (id, km) => ({
  provider_id: id,
  name: id,
  address: '',
  lat: km / 111.195,
  lng: 0,
  distance_meters: 0,
  rating: 4.5,
  types: ['cafe'],
})

// Reads like our own distance note, which an edit is allowed to cut from an
// automatic line.
const NOTE = 'Order the flat white, just a short walk away, and sit upstairs.'
const AUTOMATIC = 'Rated 4.5★ by locals, just a short walk away.'

function quest() {
  const built = buildCustomQuest({
    places: [place('a', 0), place('b', 0.3), place('c', 0.6)],
    occasion: 'friends',
    dayPart: 'evening',
    area: 'Testville',
    intro: 'My slow evening.',
    notes: { c: NOTE },
  })
  // Give the second stop an automatic line with a distance note in it.
  built.stops[1] = { ...built.stops[1], why_this_place: AUTOMATIC }
  return built
}

const lineOf = (q, id) => q.stops.find((s) => s.place.provider_id === id)
const newStop = (q, id) => ({
  ...q.stops[0],
  place: place(id, 2),
  why_this_place: 'Automatic line for the new place.',
  note_by_creator: undefined,
})

const edits = {
  'removing the stop before it': (q) => removeStop(q, 1),
  'removing the first stop': (q) => removeStop(q, 0),
  'swapping the stop before it': (q) => replaceStop(q, 1, newStop(q, 'd')),
  'adding a stop before it': (q) => insertStopAfter(q, 1, newStop(q, 'd')),
  'moving it to the front': (q) => reorderStops(q, 2, 0),
}

for (const [name, edit] of Object.entries(edits)) {
  test(`a creator's note is untouched by ${name}`, () => {
    const after = edit(quest())
    assert.equal(lineOf(after, 'c').why_this_place, NOTE)
    assert.equal(lineOf(after, 'c').note_by_creator, true)
    // The page rewrites an automatic intro; the creator's one keeps its marker.
    assert.equal(after.narrative, 'My slow evening.')
    assert.equal(after.narrative_by_creator, true)
  })
}

test('an automatic line still loses a distance note that no longer holds', () => {
  // The check above means nothing unless this edit does trim automatic lines.
  const after = reorderStops(quest(), 1, 0)
  assert.equal(lineOf(after, 'b').why_this_place, 'Rated 4.5★ by locals.')
})

test('a stop that replaces a noted one carries no creator marker', () => {
  const after = replaceStop(quest(), 2, newStop(quest(), 'd'))
  assert.equal(lineOf(after, 'd').why_this_place, 'Automatic line for the new place.')
  assert.ok(!lineOf(after, 'd').note_by_creator)
})

test('zero-width characters are removed, not turned into spaces', () => {
  for (const hidden of ['\u200b', '\u200c', '\u200d', '\u2060', '\ufeff']) {
    assert.equal(
      tidyText(`ex${hidden}ample.com${hidden} ${hidden}now`),
      'example.com now',
    )
    assert.equal(tidyText(hidden.repeat(3)), '')
    // Beside only one emoji, a joiner joins nothing.
    assert.equal(tidyText(`\u{1F525}${hidden} hot${hidden}\u{1F525}`), '\u{1F525} hot\u{1F525}')
  }
})

test('emoji made of joined parts stay whole', () => {
  for (const emoji of [
    '\u{1F468}\u200d\u{1F469}\u200d\u{1F467}', // family
    '\u{1F3F3}\ufe0f\u200d\u{1F308}', // rainbow flag
    '\u{1F468}\u{1F3FD}\u200d\u{1F4BB}', // with a skin tone
    '\u2764\ufe0f\u200d\u{1F525}', // heart on fire
  ]) {
    assert.equal(tidyText(`For ${emoji} only`), `For ${emoji} only`)
  }
})

test('a hidden character cannot slip a web address past the chat filter', () => {
  assert.equal(
    withoutLinks(tidyText('see spam\u200b-example.c\u2060om today')),
    'see (link removed) today',
  )
})

test('a note of only invisible characters is no note', () => {
  const built = buildCustomQuest({
    places: [place('a', 0)],
    occasion: 'solo',
    dayPart: 'morning',
    area: '',
    intro: '\u200b\ufeff',
    notes: { a: '\u2060 \u200c' },
  })
  assert.ok(!built.narrative_by_creator)
  assert.ok(!built.stops[0].note_by_creator)
})
