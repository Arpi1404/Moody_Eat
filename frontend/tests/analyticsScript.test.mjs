// The analytics tracker is a fixed copy kept in public/, and the tag in
// index.html is what keeps it from loading from, or telling, anyone else.
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')
const html = read('index.html').replace(/<!--[\s\S]*?-->/g, '')
const scripts = [...html.matchAll(/<script\b([^>]*)>/g)].map((m) => m[1])
const tracker = scripts.find((attrs) => attrs.includes('data-website-id'))

test('the tracker copy matches the SHA-256 in its header', () => {
  const file = read('public/site-events.js')
  const code = file.slice(file.indexOf('*/\n') + 3)
  const [, recorded] = /SHA-256: ([0-9a-f]{64})/.exec(file)
  assert.equal(createHash('sha256').update(code).digest('hex'), recorded)
})

test('index.html loads no script from another server', () => {
  for (const attrs of scripts) {
    const src = /\ssrc="([^"]*)"/.exec(attrs)?.[1]
    if (src !== undefined) assert.match(src, /^\/(?!\/)/)
  }
})

test('the tracker tag keeps its settings', () => {
  for (const attr of [
    'src="/site-events.js"',
    'data-host-url="https://gateway.umami.is"',
    'data-website-id="4f8f2eac-9e9d-44e9-a11a-e68ad70bdf6f"',
    'data-domains="moodyeat.in,www.moodyeat.in"',
    'data-exclude-search="true"',
    'data-exclude-hash="true"',
    'data-do-not-track="true"',
  ]) {
    assert.ok(tracker.includes(attr), attr)
  }
})

test("a creator's key leaves the address bar before the tracker is loaded", () => {
  const capture = html.indexOf('moodyeat:creator_key_new')
  assert.ok(capture > -1)
  assert.ok(capture < html.indexOf('src="/site-events.js"'))
})
