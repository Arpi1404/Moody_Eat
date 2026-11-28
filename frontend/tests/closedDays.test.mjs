// Catalogue quests that do not work every day. Run with `npm test`.

import assert from 'node:assert/strict'
import test from 'node:test'
import { loadSource } from './loadSource.mjs'

const { closedNotice, closedTodayLast, closedTodayLine, indiaWeekday, notOnLine } =
  await loadSource('lib/closedDays.ts')

const quest = (id, names, closed_days) => ({
  id,
  stops: names.map((name) => ({ place: { provider_id: `id-${name}`, name } })),
  ...(closed_days ? { closed_days } : {}),
})

const shut = (day, stop_index, name) => ({ day, stop_index, place_id: `id-${name}` })

const museum = quest('m', ['Park', 'Cafe', 'Museum'], [shut('monday', 2, 'Museum')])
const twoShut = quest(
  't',
  ['Park', 'Cafe', 'Bookshop'],
  [shut('monday', 2, 'Bookshop'), shut('monday', 0, 'Park')],
)
const everyDay = quest('e', ['Cafe', 'Bar'])

test('today is the date in India, not on the device', () => {
  // 28 Nov 2026 is a Saturday. India turns over at 18:30 UTC.
  assert.equal(indiaWeekday(new Date('2026-11-28T18:29:59Z')), 'saturday')
  assert.equal(indiaWeekday(new Date('2026-11-28T18:30:00Z')), 'sunday')
  // The same moment, written in another zone, is the same day.
  assert.equal(indiaWeekday(new Date('2026-11-29T20:00:00-05:00')), 'monday')
  assert.equal(indiaWeekday(new Date('2026-11-30T00:00:00+05:30')), 'monday')
  assert.equal(indiaWeekday(new Date('2026-12-04T12:00:00Z')), 'friday')
})

test('a quest that works all week says nothing', () => {
  assert.equal(notOnLine(everyDay), null)
  assert.equal(closedTodayLine(everyDay, 'monday'), null)
  assert.equal(closedNotice(everyDay, 'monday'), null)
  assert.equal(notOnLine({ ...everyDay, closed_days: null }), null)
})

test('a closed day is named on every day', () => {
  assert.equal(notOnLine(museum), 'Not on Mondays')
  assert.equal(closedTodayLine(museum, 'tuesday'), null)
  assert.deepEqual(closedNotice(museum, 'tuesday'), {
    today: false,
    headline: 'Not on Mondays.',
    detail: 'Museum is shut on Mondays.',
  })
})

test('on that day it says which stop is closed', () => {
  assert.equal(closedTodayLine(museum, 'monday'), 'Museum is closed today')
  assert.deepEqual(closedNotice(museum, 'monday'), {
    today: true,
    headline: 'Museum is closed today.',
    detail: 'Not on Mondays.',
  })
})

test('two shut stops are named in the order they are visited', () => {
  assert.equal(closedTodayLine(twoShut, 'monday'), 'Park and Bookshop are closed today')
  assert.equal(notOnLine(twoShut), 'Not on Mondays')
  assert.equal(
    closedNotice(twoShut, 'friday').detail,
    'Park and Bookshop are shut on Mondays.',
  )
})

test('two closed days read in week order', () => {
  const both = quest('b', ['A', 'B'], [shut('friday', 1, 'B'), shut('monday', 0, 'A')])
  assert.equal(notOnLine(both), 'Not on Mondays or Fridays')
  assert.equal(
    closedNotice(both, 'sunday').detail,
    'A is shut on Mondays; B is shut on Fridays.',
  )
})

test('a closed day follows its place through edits to a saved copy', () => {
  const [park, cafe, museumStop] = museum.stops
  const reordered = { ...museum, stops: [museumStop, park, cafe] }
  assert.equal(closedTodayLine(reordered, 'monday'), 'Museum is closed today')

  const removed = { ...museum, stops: [park, cafe] }
  assert.equal(notOnLine(removed), null)

  const gallery = { place: { provider_id: 'id-Gallery', name: 'Gallery' } }
  const swapped = { ...museum, stops: [park, cafe, gallery] }
  assert.equal(notOnLine(swapped), null)
  assert.equal(closedTodayLine(swapped, 'monday'), null)
})

test('quests with a stop shut today go to the end, and none is dropped', () => {
  const row = [museum, everyDay, twoShut, quest('z', ['Z'])]
  assert.deepEqual(
    closedTodayLast(row, 'monday').map((q) => q.id),
    ['e', 'z', 'm', 't'],
  )
  assert.deepEqual(
    closedTodayLast(row, 'tuesday').map((q) => q.id),
    ['m', 'e', 't', 'z'],
  )
  assert.deepEqual(row.map((q) => q.id), ['m', 'e', 't', 'z'])
})
