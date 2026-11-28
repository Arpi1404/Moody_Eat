// What the home page says about a catalogue quest, and which one it shows
// first. Run with `npm test`.

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { loadSource } from './loadSource.mjs'

const {
  cardLabel,
  costText,
  durationText,
  leadStop,
  pickHeroQuest,
  shortStopName,
  startText,
  stopNames,
} = await loadSource('lib/catalogue.ts')
const { closedTodayLine, indiaWeekday } = await loadSource('lib/closedDays.ts')

// The real catalogue, as the API serves it.
const snapshot = JSON.parse(
  await readFile(new URL('../scripts/curated-snapshot.json', import.meta.url), 'utf8'),
)

const quest = (id, start, names = ['Cafe', 'Park'], extra = {}) => ({
  id,
  title: `Quest ${id}`,
  occasion: 'date',
  total_duration_minutes: 210,
  total_cost_estimate: 'cheap',
  stops: names.map((name) => ({
    time_block_start: `${start}:00`,
    place: { provider_id: `${id}-${name}`, name },
  })),
  ...extra,
})

/** A moment given on India's clock. 28 Nov 2026 is a Saturday. */
const india = (day, time) => new Date(`2026-11-${day}T${time}:00+05:30`)

test('cost is the rupee range per person when there is one, else the tier', () => {
  const q = quest('a', '18:00')
  assert.equal(costText(q), '₹ Cheap')
  const priced = { ...q, est_total_per_person_min_inr: 400, est_total_per_person_max_inr: 800 }
  assert.equal(costText(priced), '≈₹400–800/person')
  const free = { ...q, est_total_per_person_min_inr: 0, est_total_per_person_max_inr: 0 }
  assert.equal(costText(free), 'Free')
})

test('durations and start times read plainly', () => {
  assert.equal(durationText(240), '4h')
  assert.equal(durationText(210), '3.5h')
  assert.equal(startText(quest('a', '18:00')), '6 pm')
  assert.equal(startText(quest('a', '16:30')), '4:30 pm')
  assert.equal(startText(quest('a', '07:05')), '7:05 am')
  assert.equal(startText(quest('a', '12:00')), '12 pm')
  assert.equal(startText({ ...quest('a', '12:00'), stops: [] }), null)
})

test('a stop list drops a bracket that repeats the name, and nothing else', () => {
  assert.equal(shortStopName('MTR (Mavalli Tiffin Rooms)'), 'MTR')
  assert.equal(shortStopName('Bull Temple (Dodda Basavana Gudi)'), 'Bull Temple')
  assert.equal(shortStopName('Paradise Biryani — Secunderabad'), 'Paradise Biryani — Secunderabad')
  assert.equal(shortStopName('(Untitled)'), '(Untitled)')
  assert.deepEqual(stopNames(quest('a', '18:00', ['One', 'Two (Annexe)', 'Three'])), [
    'One',
    'Two',
    'Three',
  ])
})

test('the lead photo is the first stop unless the quest names another', () => {
  const q = quest('a', '18:00', ['Lake', 'Bistro', 'Cafe'])
  assert.equal(leadStop(q).place.name, 'Lake')
  const named = { ...q, photo_stop: { stop_index: 1, place_id: 'a-Bistro' } }
  assert.equal(leadStop(named).place.name, 'Bistro')
  // It follows the place when stops move, and falls back when it has gone.
  const moved = { ...named, stops: [q.stops[1], q.stops[0]] }
  assert.equal(leadStop(moved).place.name, 'Bistro')
  const gone = { ...named, stops: [q.stops[0], q.stops[2]] }
  assert.equal(leadStop(gone).place.name, 'Lake')
  assert.equal(leadStop({ ...q, stops: [] }), undefined)
})

test('a card is read out in the order it is seen', () => {
  const q = quest('a', '18:00', ['Lake', 'MTR (Mavalli Tiffin Rooms)'], {
    audience_line: 'For a date that wants a plan, not a queue.',
    closed_days: [{ day: 'monday', stop_index: 1, place_id: 'a-MTR (Mavalli Tiffin Rooms)' }],
  })
  assert.equal(
    cardLabel(q, 'tuesday'),
    'Quest a. Date quest. For a date that wants a plan, not a queue. ' +
      'Stops in order: Lake, then MTR. 3.5h, ₹ Cheap. Not on Mondays.',
  )
  assert.equal(
    cardLabel(q, 'monday', { withAudience: false, withStart: true }),
    'Quest a. Date quest. Stops in order: Lake, then MTR. Starts 6 pm. 3.5h, ₹ Cheap. ' +
      'MTR (Mavalli Tiffin Rooms) is closed today. Not on Mondays.',
  )
})

const mixed = [
  quest('morning', '07:30'),
  quest('noon', '13:45'),
  quest('late-afternoon', '16:30'),
  quest('evening', '18:00'),
  quest('late', '19:30'),
]

test('the first quest suits the time the visitor arrives, on the India clock', () => {
  const pickedAt = (time) => {
    const seen = new Set()
    for (const day of ['23', '24', '25', '26', '27', '28', '29']) {
      seen.add(pickHeroQuest(mixed, india(day, time)).id)
    }
    return [...seen].sort()
  }
  assert.deepEqual(pickedAt('08:00'), ['morning'])
  assert.deepEqual(pickedAt('12:00'), ['late-afternoon', 'noon'])
  assert.deepEqual(pickedAt('16:00'), ['evening', 'late', 'late-afternoon'])
  assert.deepEqual(pickedAt('19:00'), ['evening', 'late'])
  assert.deepEqual(pickedAt('22:00'), ['late'])
  assert.deepEqual(pickedAt('02:00'), ['late'])
})

test('when nothing suits the hour, another open quest is shown', () => {
  const evenings = [quest('x', '16:30'), quest('y', '18:00')]
  assert.equal(pickHeroQuest(evenings, india('28', '07:00')).stops.length, 2)
  assert.equal(pickHeroQuest([quest('m', '07:30')], india('28', '19:00')).id, 'm')
  assert.equal(pickHeroQuest([], india('28', '19:00')), null)
  assert.equal(pickHeroQuest([{ ...quest('e', '18:00'), stops: [] }], india('28', '19:00')), null)
})

test('everyone gets the same quest through that part of a day, whatever the order', () => {
  const evenings = [quest('x', '18:00'), quest('y', '18:15'), quest('z', '18:30')]
  const first = pickHeroQuest(evenings, india('28', '15:00')).id
  assert.equal(pickHeroQuest([...evenings].reverse(), india('28', '17:59')).id, first)
  // The same instant from a device in another time zone.
  assert.equal(pickHeroQuest(evenings, new Date('2026-11-28T04:30:00-05:00')).id, first)
  // It moves on the next day.
  assert.notEqual(pickHeroQuest(evenings, india('29', '15:00')).id, first)
})

test('it never shows a quest with a stop shut that day', () => {
  const shutMondays = quest('shut', '18:00', ['Museum'], {
    closed_days: [{ day: 'monday', stop_index: 0, place_id: 'shut-Museum' }],
  })
  const open = quest('open', '07:30')
  assert.equal(pickHeroQuest([shutMondays, open], india('30', '18:30')).id, 'open')
  assert.equal(pickHeroQuest([shutMondays], india('30', '18:30')), null)
})

test('with the real catalogue, every city has an open pick at every hour of a week', () => {
  for (const city of snapshot.cities) {
    for (let day = 23; day <= 29; day++) {
      for (let hour = 0; hour < 24; hour++) {
        const now = india(day, `${String(hour).padStart(2, '0')}:00`)
        const pick = pickHeroQuest(city.quests, now)
        assert.ok(pick, `${city.key} ${day} ${hour}:00`)
        assert.equal(closedTodayLine(pick, indiaWeekday(now)), null, pick.title)
      }
    }
  }
})

test('every real quest has what its card shows', () => {
  for (const q of snapshot.cities.flatMap((c) => c.quests)) {
    assert.ok(q.audience_line, q.title)
    assert.ok(startText(q), q.title)
    assert.ok(leadStop(q), q.title)
    assert.ok(stopNames(q).length >= 2 && stopNames(q).length <= 4, q.title)
  }
})
