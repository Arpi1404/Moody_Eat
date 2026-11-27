// The message at the limit on new quests. Run with `npm test`.

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { fileURLToPath } from 'node:url'
import { transformWithEsbuild } from 'vite'

const source = fileURLToPath(new URL('../src/lib/tooManyQuests.ts', import.meta.url))
const { code } = await transformWithEsbuild(await readFile(source, 'utf8'), source, {
  loader: 'ts',
  format: 'esm',
})
const { TooManyQuestsError, tooManyQuestsMessage } = await import(
  `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
)

const A_MINUTE = "That's a lot of quests at once. Wait a minute, then try again."
const later = (minutes) =>
  `That's a lot of quests for one hour. Try again in about ${minutes} minutes.`

test('a wait of up to a minute says to wait a minute', () => {
  for (const seconds of [1, 15, 60]) {
    assert.equal(tooManyQuestsMessage(seconds), A_MINUTE)
  }
})

test('a longer wait says about how many minutes, rounded up', () => {
  assert.equal(tooManyQuestsMessage(61), later(2))
  assert.equal(tooManyQuestsMessage(1500), later(25))
  assert.equal(tooManyQuestsMessage(3356), later(56))
  assert.equal(tooManyQuestsMessage(3600), later(60))
})

test('a reply with no usable wait still reads sensibly', () => {
  for (const missing of [undefined, null, '3600', Number.NaN]) {
    assert.equal(tooManyQuestsMessage(missing), A_MINUTE)
  }
})

test('the error carries the message the pages show', () => {
  const err = new TooManyQuestsError(1500)
  assert.ok(err instanceof Error)
  assert.equal(err.message, later(25))
})
