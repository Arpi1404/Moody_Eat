// When opening a manage link must ask before changing which page a browser
// manages, and which server replies mean a key is dead. Run with `npm test`.

import assert from 'node:assert/strict'
import test from 'node:test'
import { loadSource } from './loadSource.mjs'

const { keyHandle, isOtherPage, mustAskBeforeSwitching } = await loadSource(
  'lib/creatorKeySwitch.ts',
)

const MINE = 'priya.aaaaaaaa'
const REPLACED = 'priya.bbbbbbbb'
const THEIRS = 'sam-eats.cccccccc'

test("a key's page is the part before the first dot", () => {
  assert.equal(keyHandle(MINE), 'priya')
  assert.equal(keyHandle('sam-eats.a.b'), 'sam-eats')
  assert.equal(keyHandle('nodot'), 'nodot')
})

test('a first key, or a replaced one for the same page, is not asked about', () => {
  assert.equal(isOtherPage(null, THEIRS), false)
  assert.equal(isOtherPage(MINE, REPLACED), false)
  assert.equal(isOtherPage(MINE, MINE), false)
  for (const check of ['works', 'dead', 'unknown']) {
    assert.equal(mustAskBeforeSwitching(null, THEIRS, check), false)
    assert.equal(mustAskBeforeSwitching(MINE, REPLACED, check), false)
  }
})

test('a working key for another page is never replaced without asking', () => {
  assert.equal(isOtherPage(MINE, THEIRS), true)
  assert.equal(mustAskBeforeSwitching(MINE, THEIRS, 'works'), true)
})

test('when the stored key cannot be checked, ask rather than lose it', () => {
  assert.equal(mustAskBeforeSwitching(MINE, THEIRS, 'unknown'), true)
})

test('a dead stored key is given up without asking', () => {
  assert.equal(mustAskBeforeSwitching(MINE, THEIRS, 'dead'), false)
})

test('one handle that starts like another is still another page', () => {
  assert.equal(isOtherPage('priya.x', 'priya-eats.x'), true)
})

const { CreatorError, failureFrom, isDeadKey } = await loadSource('lib/creatorApi.ts')

test('a checked and refused key is dead, whichever way it is refused', () => {
  const refused = failureFrom(401, { detail: { code: 'bad_key' } })
  const onceTooOften = failureFrom(429, { detail: { code: 'too_many' } })
  assert.equal(refused.reason, 'bad_key')
  assert.equal(onceTooOften.reason, 'too_many')
  assert.ok(isDeadKey(refused) && isDeadKey(onceTooOften))
})

test('the ceiling on requests says nothing about the key', () => {
  const busy = failureFrom(429, { detail: 'Rate limit exceeded. Try again later.' })
  assert.equal(busy.reason, 'busy')
  assert.match(busy.message, /Wait a minute/)
  assert.equal(isDeadKey(busy), false)
  assert.equal(isDeadKey(new CreatorError('unavailable')), false)
  assert.equal(isDeadKey(new Error('offline')), false)
})

test('other refusals keep their meaning', () => {
  assert.equal(failureFrom(404, { detail: { code: 'creator_not_found' } }).reason, 'creator_not_found')
  assert.equal(failureFrom(404, { detail: 'Not Found' }).reason, 'unavailable')
  assert.equal(failureFrom(500, null).reason, 'unavailable')
  const full = failureFrom(409, { detail: { code: 'page_full', message: 'Full.' } })
  assert.deepEqual([full.reason, full.message], ['refused', 'Full.'])
})
