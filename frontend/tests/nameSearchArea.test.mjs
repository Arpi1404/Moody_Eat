// What a search by name sends as its area. Run with `npm test`.
//
// nameSearchArea.ts has no imports, so it is compiled here with the compiler
// Vite already ships and loaded on its own. Works on the Node 20 that CI uses.

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { fileURLToPath } from 'node:url'
import { transformWithEsbuild } from 'vite'

const source = fileURLToPath(
  new URL('../src/lib/nameSearchArea.ts', import.meta.url),
)
const { code } = await transformWithEsbuild(await readFile(source, 'utf8'), source, {
  loader: 'ts',
  format: 'esm',
})
const { areaKey, nameSearchAnchor } = await import(
  `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
)

const nothing = new Map()

test('a picked suggestion sends its coordinates', () => {
  const picked = { lat: 12.9352, lng: 77.6245, label: 'Koramangala, Bengaluru' }
  assert.deepEqual(nameSearchAnchor('Koramangala, Bengaluru', picked, nothing), {
    send: { lat: 12.9352, lng: 77.6245 },
    knownName: '',
  })
})

test('the 📍 button’s coordinates are sent as numbers, not geocoded', () => {
  for (const field of ['12.972,77.641', ' 12.972, 77.641 ', '-33.865,151.209']) {
    const { send } = nameSearchAnchor(field, null, nothing)
    assert.deepEqual(Object.keys(send), ['lat', 'lng'], field)
  }
  assert.deepEqual(nameSearchAnchor('12.972,77.641', null, nothing).send, {
    lat: 12.972,
    lng: 77.641,
  })
})

test('text that is not a position on the map goes as an area', () => {
  for (const field of ['Indiranagar', '12, 34', '95.000,10.000', '12.9,200.0']) {
    assert.deepEqual(nameSearchAnchor(field, null, nothing).send, { area: field })
  }
})

test('a typed area is geocoded once, then sent as coordinates', () => {
  const remembered = new Map()
  const first = nameSearchAnchor('  Park Street ', null, remembered)
  assert.deepEqual(first, { send: { area: 'Park Street' }, knownName: '' })

  // What the page keeps from the first answer.
  remembered.set(areaKey('  Park Street '), {
    lat: 22.553,
    lng: 88.352,
    name: 'Park Street, Kolkata',
  })
  for (const field of ['Park Street', 'park   street']) {
    assert.deepEqual(nameSearchAnchor(field, null, remembered), {
      send: { lat: 22.553, lng: 88.352 },
      knownName: 'Park Street, Kolkata',
    })
  }
  // Any other text is a new area.
  assert.deepEqual(nameSearchAnchor('Park Street, London', null, remembered).send, {
    area: 'Park Street, London',
  })
})
