// What may go into a stop's Call and Website links. Run with `npm test`.
import assert from 'node:assert/strict'
import test from 'node:test'
import { loadSource } from './loadSource.mjs'

const { phoneLink, websiteLink } = await loadSource('lib/placeContact.ts')

test('a number as Google writes it becomes a tel: link', () => {
  for (const [written, dialled] of [
    ['+91 80 4123 4567', 'tel:+918041234567'],
    ['080-4123 4567', 'tel:08041234567'],
    ['(022) 2202 3456', 'tel:02222023456'],
    ['+1 (415) 555-0100', 'tel:+14155550100'],
    ['  +91 98450 12345  ', 'tel:+919845012345'],
    ['1800 123 456', 'tel:1800123456'],
  ]) {
    assert.equal(phoneLink(written), dialled, written)
  }
})

test('the bracketed trunk 0 is not dialled after a country code', () => {
  assert.equal(phoneLink('+44 (0)20 7946 0018'), 'tel:+442079460018')
  assert.equal(phoneLink('(0)20 7946 0018'), 'tel:02079460018')
})

test('anything that is not plainly a number gets no Call button', () => {
  for (const bad of [
    undefined,
    null,
    '',
    '   ',
    918041234567,
    {},
    'call us',
    '080.4123.4567',
    '+91 80 4123 4567 ext 2',
    '*#06#',
    '*21*9845012345#',
    '9845012345,,123',
    '9845012345;postd=1',
    '98450\n12345',
    '98450\t12345',
    '91+ 9845012345',
    '++91 9845012345',
    'tel:+919845012345',
    'javascript:alert(1)',
    '+91 <b>',
    '12345',
    '()- ()-',
    '1234567890123456',
    '1'.repeat(31),
  ]) {
    assert.equal(phoneLink(bad), null, JSON.stringify(bad))
  }
})

test('http and https addresses are linked', () => {
  assert.deepEqual(websiteLink('https://cafe.example/menu?x=1#hours'), {
    href: 'https://cafe.example/menu?x=1#hours',
    label: 'Website',
  })
  assert.equal(websiteLink('HTTP://Cafe.Example').href, 'http://cafe.example/')
  assert.equal(websiteLink('  https://cafe.example  ').href, 'https://cafe.example/')
})

test('nothing else is', () => {
  for (const bad of [
    undefined,
    null,
    '',
    42,
    'cafe.example',
    'www.cafe.example',
    '//cafe.example',
    '/menu',
    'javascript:alert(1)',
    'JavaScript://cafe.example/%0aalert(1)',
    'data:text/html,hello',
    'file:///etc/passwd',
    'ftp://cafe.example',
    'intent://cafe.example',
    'tel:+919845012345',
    'mailto:a@cafe.example',
    'https:cafe.example',
    'https:/cafe.example',
    'https://',
    'https://cafe.example/a b',
    'https://cafe.ex\nample',
    'java\tscript:alert(1)',
    'https://cafe.example/<script>',
    'https://cafe.example\\@elsewhere.example',
    'https://instagram.com@elsewhere.example/',
    'https://user:pass@cafe.example/',
    `https://cafe.example/${'a'.repeat(500)}`,
  ]) {
    assert.equal(websiteLink(bad), null, JSON.stringify(bad))
  }
})

test('the button is named after a service the address belongs to', () => {
  for (const [url, label] of [
    ['https://www.instagram.com/somecafe/', 'Instagram'],
    ['http://instagram.com/somecafe', 'Instagram'],
    ['https://m.facebook.com/somecafe', 'Facebook'],
    ['https://wa.me/919845012345', 'WhatsApp'],
    ['https://api.whatsapp.com/send?phone=919845012345', 'WhatsApp'],
    ['https://www.zomato.com/city/some-cafe', 'Zomato'],
    ['https://www.swiggy.com/restaurants/some-cafe', 'Swiggy'],
    ['https://www.tripadvisor.in/Restaurant_Review', 'Tripadvisor'],
    ['https://linktr.ee/somecafe', 'Linktree'],
    ['https://INSTAGRAM.com./somecafe', 'Instagram'],
  ]) {
    assert.equal(websiteLink(url).label, label, url)
  }
})

test('a look-alike address is only ever "Website"', () => {
  for (const url of [
    'https://notinstagram.com/somecafe',
    'https://instagram.com.elsewhere.example/',
    'https://tripadvisor.elsewhere.example/',
    'https://elsewhere.example/instagram.com',
    'https://elsewhere.example/?u=https://zomato.com',
  ]) {
    assert.equal(websiteLink(url).label, 'Website', url)
  }
})
