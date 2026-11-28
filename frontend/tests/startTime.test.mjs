// The planner's day and start time choices. Run with `npm test`.
import assert from 'node:assert/strict'
import test from 'node:test'
import { loadSource } from './loadSource.mjs'

const {
  dayChoices,
  dayLabel,
  isoDay,
  keepStartValid,
  maxStopsFor,
  planDayPart,
  spokenDayPart,
  startForDayPart,
  timeChoices,
  timeLabel,
} = await loadSource('lib/startTime.ts')

// Saturday 28 November 2026, on the device's own clock.
const at = (h, m = 0) => new Date(2026, 10, 28, h, m)

test('today offers only the times not yet past, every half hour to 10 pm', () => {
  assert.deepEqual(timeChoices(at(17, 5), 0).slice(0, 3), ['17:30', '18:00', '18:30'])
  assert.equal(timeChoices(at(17, 5), 0).at(-1), '22:00')
  assert.deepEqual(timeChoices(at(17, 30), 0)[0], '17:30')
  assert.deepEqual(timeChoices(at(5, 0), 0)[0], '07:00')
  // Another day offers the whole day.
  assert.equal(timeChoices(at(17, 5), 1)[0], '07:00')
  assert.equal(timeChoices(at(17, 5), 1).length, 31)
})

test('today is offered until nothing can start any more', () => {
  assert.equal(dayChoices(at(21, 50))[0].disabled, false)
  assert.equal(dayChoices(at(22, 1))[0].disabled, true)
  assert.equal(dayChoices(at(22, 1)).length, 7)
})

test('days are named the way people say them, rolling over the month', () => {
  assert.equal(dayLabel(at(9), 0), 'Today')
  assert.equal(dayLabel(at(9), 1), 'Tomorrow')
  assert.equal(dayLabel(at(9), 2), 'Mon 30 Nov')
  assert.equal(dayLabel(at(9), 3), 'Tue 1 Dec')
  assert.equal(isoDay(at(23, 59), 3), '2026-12-01')
  assert.equal(isoDay(new Date(2026, 11, 30, 10), 2), '2027-01-01')
})

test('a day part button starts at its usual time, or the next one left today', () => {
  assert.deepEqual(startForDayPart(at(9), 0, 'evening'), { offset: 0, time: '17:30' })
  // At 6:10 pm the evening is not over: 6:30 pm.
  assert.deepEqual(startForDayPart(at(18, 10), 0, 'evening'), { offset: 0, time: '18:30' })
  // The morning is over at 3 pm: tomorrow morning.
  assert.deepEqual(startForDayPart(at(15), 0, 'morning'), { offset: 1, time: '10:00' })
  // Night after 10 pm: tomorrow.
  assert.deepEqual(startForDayPart(at(22, 5), 0, 'night'), { offset: 1, time: '20:00' })
})

test('a chosen start that has passed while the sheet was open moves on', () => {
  assert.deepEqual(keepStartValid(at(17, 40), { offset: 0, time: '17:30' }), { offset: 0, time: '18:00' })
  assert.deepEqual(keepStartValid(at(17, 40), { offset: 1, time: '09:00' }), { offset: 1, time: '09:00' })
  assert.deepEqual(keepStartValid(at(22, 30), { offset: 0, time: '20:00' }), { offset: 1, time: '20:00' })
})

test('the highlighted button and the plan follow the engine', () => {
  assert.equal(spokenDayPart('11:30'), 'morning')
  assert.equal(spokenDayPart('16:59'), 'afternoon')
  assert.equal(spokenDayPart('19:30'), 'evening')
  assert.equal(spokenDayPart('20:00'), 'night')
  assert.equal(planDayPart('11:00'), 'morning')
  assert.equal(planDayPart('14:30'), 'afternoon')
  assert.equal(planDayPart('18:00'), 'evening')
  assert.equal(planDayPart('18:30'), 'night')
})

test('a family night holds three stops; everything else four', () => {
  assert.equal(maxStopsFor('family', '20:00'), 3)
  assert.equal(maxStopsFor('family', '18:30'), 3)
  assert.equal(maxStopsFor('family', '17:30'), 4)
  assert.equal(maxStopsFor('date', '21:00'), 4)
})

test('times read as a person says them', () => {
  assert.equal(timeLabel('07:00'), '7 am')
  assert.equal(timeLabel('12:30'), '12:30 pm')
  assert.equal(timeLabel('19:30'), '7:30 pm')
  assert.equal(timeLabel('22:00'), '10 pm')
})

test('a quest names its day: today, tomorrow, else weekday and date', async () => {
  const { questDayLabel } = await loadSource('lib/startTime.ts')
  assert.equal(questDayLabel('2026-11-28', at(9)), 'Today')
  assert.equal(questDayLabel('2026-11-29', at(23, 59)), 'Tomorrow')
  assert.equal(questDayLabel('2026-12-03', at(9)), 'Thu 3 Dec')
  // A day already gone is still named, not called "Today".
  assert.equal(questDayLabel('2026-11-27', at(9)), 'Fri 27 Nov')
  // Quests from before the field, or a bad value: no label.
  assert.equal(questDayLabel(undefined, at(9)), null)
  assert.equal(questDayLabel(null, at(9)), null)
  assert.equal(questDayLabel('next week', at(9)), null)
})
