// Build-time SEO pages: renders the curated quests as static HTML under
// dist/guides/, plus sitemap.xml and robots.txt. Runs via the `postbuild`
// npm hook, so `npm run build` produces them automatically.
//
//   /guides/                  every city, every quest
//   /guides/<city>/           one city's quests, by occasion
//   /guides/<city>/<slug>/    one quest
//
// Data source is scripts/curated-snapshot.json — a checked-in copy so builds
// are deterministic and never depend on the backend being up. Refresh it
// after editing anything under backend/curated/:
//   cd backend && python -m scripts.export_curated

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const DIST = join(__dirname, '..', 'dist')
const BASE_URL = 'https://www.moodyeat.in'

const OCCASION_LABEL = {
  date: 'Date night',
  friends: 'Friends hangout',
  solo: 'Solo day out',
  family: 'Family outing',
}

// Guides used to live at /guides/<slug>/, Hyderabad only. Each old address
// forwards to where that quest is now — or to the Hyderabad page when the
// quest was retired. Values are paths under /guides/.
const LEGACY_REDIRECTS = {
  'charminar-to-chai-old-city-wander': 'hyderabad/charminar-to-chai-old-city-wander',
  'jubilee-hills-slow-burn': 'hyderabad/jubilee-hills-slow-burn',
  'hitec-city-game-night': 'hyderabad/hitec-city-game-night',
  'paradise-promenade-repeat': 'hyderabad/paradise-promenade-repeat',
  'banjara-quiet-hours': 'hyderabad/banjara-quiet-hours',
  'golconda-sunset-tolichowki-dinner': 'hyderabad/golconda-afternoon-tolichowki-dinner',
  'banjara-hills-after-dark': 'hyderabad',
  'jubilee-hills-bar-loop': 'hyderabad',
  'salar-jung-slow-looking': 'hyderabad',
  'gachibowli-green-hours': 'hyderabad',
  'necklace-road-picnic': 'hyderabad',
  'hitec-family-weekend': 'hyderabad',
  'gurgaon/brunch-then-vintage-wheels': 'gurgaon',
}

const snapshot = JSON.parse(
  readFileSync(join(__dirname, 'curated-snapshot.json'), 'utf8'),
)

function esc(s) {
  return String(s ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
}

function slugify(title) {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')
}

function formatTime(hhmm) {
  const [hStr, mStr] = String(hhmm).split(':')
  const h = parseInt(hStr, 10)
  const m = parseInt(mStr, 10)
  const ampm = h >= 12 ? 'pm' : 'am'
  const hour = h % 12 || 12
  return m === 0 ? `${hour}${ampm}` : `${hour}:${String(m).padStart(2, '0')}${ampm}`
}

function listCities(names) {
  return names.length < 2
    ? names.join('')
    : `${names.slice(0, -1).join(', ')} and ${names.at(-1)}`
}

const SHARED_CSS = `
  :root { color-scheme: light; }
  * { box-sizing: border-box; margin: 0; }
  body { background: #faf6ef; color: #3d3428; font: 16px/1.65 Georgia, 'Times New Roman', serif; }
  .wrap { max-width: 660px; margin: 0 auto; padding: 32px 20px 64px; }
  a { color: #c7522a; }
  header.site a { text-decoration: none; font-weight: 700; font-size: 18px; color: #1f1a14; }
  header.site span { color: #c7522a; }
  .eyebrow { text-transform: uppercase; letter-spacing: 0.12em; font-size: 12px; color: #c7522a; margin: 28px 0 6px; font-weight: 700; }
  h1 { font-size: 30px; line-height: 1.2; color: #1f1a14; margin-bottom: 12px; }
  h2.city { font-size: 24px; line-height: 1.2; color: #1f1a14; margin: 40px 0 0; }
  h2.city a { color: inherit; text-decoration: none; }
  .lede { font-size: 17px; margin-bottom: 24px; }
  .stop { background: #fff; border: 1px solid #e8dfd0; border-radius: 14px; padding: 18px 20px; margin: 14px 0; }
  .stop h2 { font-size: 19px; color: #1f1a14; }
  .stop .meta { font-size: 13px; color: #8a7c66; margin: 4px 0 10px; }
  .stop p { font-size: 15px; }
  .travel { font-size: 13px; color: #8a7c66; margin: 8px 4px; }
  .cta { display: block; text-align: center; background: #c7522a; color: #fff; text-decoration: none; border-radius: 999px; padding: 14px 20px; font-weight: 700; margin: 28px 0 10px; font-family: system-ui, sans-serif; }
  .cta.secondary { background: transparent; color: #c7522a; border: 1.5px solid #c7522a; }
  .more { margin-top: 36px; border-top: 1px solid #e8dfd0; padding-top: 20px; }
  .more li { margin: 6px 0; }
  .cities { font-size: 15px; margin: 4px 0 8px; }
  footer { margin-top: 40px; font-size: 13px; color: #8a7c66; }
  .card { display: block; background: #fff; border: 1px solid #e8dfd0; border-radius: 14px; padding: 16px 18px; margin: 12px 0; text-decoration: none; }
  .card strong { color: #1f1a14; font-size: 17px; }
  .card span { display: block; color: #8a7c66; font-size: 13px; margin-top: 4px; }
`

function pageShell({ title, description, canonical, body }) {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>
<meta name="description" content="${esc(description)}">
<link rel="canonical" href="${canonical}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(description)}">
<meta property="og:type" content="article">
<meta property="og:url" content="${canonical}">
<meta property="og:image" content="${BASE_URL}/og-image.png">
<style>${SHARED_CSS}</style>
</head>
<body><div class="wrap">
<header class="site"><a href="/">Moody<span>Eat</span></a></header>
${body}
<footer>MoodyEat plans your evening out — free, no signup. <a href="/">Build a quest</a> · <a href="/guides/">All guides</a></footer>
</div></body>
</html>`
}

function questCard(entry) {
  return `<a class="card" href="${entry.path}">
<strong>${esc(entry.quest.title)}</strong>
<span>${entry.quest.stops.map((s) => esc(s.place.name)).join(' → ')}</span>
</a>`
}

function guidePage(entry, others) {
  const { quest, city } = entry
  const occasion = OCCASION_LABEL[quest.occasion] ?? quest.occasion
  const stopNames = quest.stops.map((s) => s.place.name)
  const description =
    `${occasion} plan in ${city.name}: ${stopNames.join(' → ')}. ` +
    `Timings, why each spot, and a shareable map — planned in 30 seconds on MoodyEat.`

  const stopsHtml = quest.stops
    .map((s, i) => {
      const travel =
        s.travel_to_next_minutes != null
          ? `<p class="travel">↓ ${s.travel_to_next_minutes} min ${esc(s.travel_mode ?? 'drive')} to the next stop</p>`
          : ''
      return `<article class="stop">
<h2>${i + 1}. ${esc(s.place.name)}</h2>
<p class="meta">${formatTime(s.time_block_start)} – ${formatTime(s.time_block_end)}${s.place.rating ? ` · ★ ${s.place.rating}` : ''}${s.place.address ? ` · ${esc(s.place.address)}` : ''}</p>
<p>${esc(s.why_this_place)}</p>
</article>${travel}`
    })
    .join('\n')

  const othersHtml = others
    .map(
      (o) =>
        `<li><a href="${o.path}">${esc(o.quest.title)}</a> — ${OCCASION_LABEL[o.quest.occasion] ?? o.quest.occasion}</li>`,
    )
    .join('\n')

  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'ItemList',
    name: `${quest.title} — ${occasion} in ${city.name}`,
    description,
    itemListElement: quest.stops.map((s, i) => ({
      '@type': 'ListItem',
      position: i + 1,
      name: s.place.name,
      description: s.why_this_place,
    })),
  }

  const body = `
<p class="eyebrow">${esc(occasion)} · <a href="/guides/${city.key}/">${esc(city.name)}</a></p>
<h1>${esc(quest.title)}</h1>
<p class="lede">${esc(quest.narrative)}</p>
${stopsHtml}
<a class="cta" href="/?city=${city.key}">Plan your own evening in 30 seconds →</a>
<a class="cta secondary" href="/create">Or build it stop by stop</a>
<section class="more">
<p class="eyebrow">More ${esc(city.name)} plans</p>
<ul>${othersHtml}</ul>
</section>
<script type="application/ld+json">${JSON.stringify(jsonLd)}</script>`

  return pageShell({
    title: `${quest.title} — ${occasion} in ${city.name} | MoodyEat`,
    description,
    canonical: `${BASE_URL}${entry.path}`,
    body,
  })
}

function cityHubPage(city, entries, otherCities) {
  const byOccasion = {}
  for (const e of entries) {
    ;(byOccasion[e.quest.occasion] ??= []).push(e)
  }
  const sections = Object.entries(byOccasion)
    .map(
      ([occ, list]) => `
<p class="eyebrow">${esc(OCCASION_LABEL[occ] ?? occ)}</p>
${list.map(questCard).join('\n')}`,
    )
    .join('\n')

  const elsewhere = otherCities
    .map((c) => `<a href="/guides/${c.key}/">${esc(c.name)}</a>`)
    .join(' · ')

  const description = `Hand-planned evenings out in ${city.name}: date nights, friends hangouts, solo days, and family outings — with timings, real places, and maps.`
  const body = `
<h1>${esc(city.name)} evening plans, ready to go</h1>
<p class="lede">${description}</p>
${sections}
<a class="cta" href="/?city=${city.key}">Plan a custom evening in 30 seconds →</a>
<p class="cities">Also: ${elsewhere}</p>`

  return pageShell({
    title: `Things to do in ${city.name}: ready-made evening plans | MoodyEat`,
    description,
    canonical: `${BASE_URL}/guides/${city.key}/`,
    body,
  })
}

function hubPage(cities) {
  const names = listCities(cities.map((c) => c.city.name))
  const sections = cities
    .map(
      ({ city, entries }) => `
<h2 class="city"><a href="/guides/${city.key}/">${esc(city.name)}</a></h2>
${entries.map(questCard).join('\n')}`,
    )
    .join('\n')

  const description = `Hand-planned evenings out in ${names}: date nights, friends hangouts, solo days, and family outings — with timings, real places, and maps.`
  const body = `
<h1>Evening plans, ready to go</h1>
<p class="lede">${description} Somewhere else? MoodyEat builds a plan around wherever you are.</p>
${sections}
<a class="cta" href="/">Plan a custom evening in 30 seconds →</a>`

  return pageShell({
    title: `Ready-made evening plans in ${names} | MoodyEat`,
    description,
    canonical: `${BASE_URL}/guides/`,
    body,
  })
}

function redirectPage(target) {
  // A static stand-in for a 301: search engines follow an instant refresh,
  // and the canonical tells them which address to keep.
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>This guide has moved | MoodyEat</title>
<link rel="canonical" href="${BASE_URL}${target}">
<meta http-equiv="refresh" content="0; url=${target}">
</head>
<body><p>This guide has moved: <a href="${target}">${target}</a></p></body>
</html>`
}

function writePage(path, html) {
  const dir = join(DIST, ...path.split('/').filter(Boolean))
  mkdirSync(dir, { recursive: true })
  writeFileSync(join(dir, 'index.html'), html)
}

// ── Generate ──────────────────────────────────────────────────────────────────

const cities = snapshot.cities.map((city) => ({
  city,
  entries: city.quests.map((quest) => {
    const slug = slugify(quest.title)
    return { quest, city, slug, path: `/guides/${city.key}/${slug}/` }
  }),
}))

const written = new Set(['/guides/'])

for (const { city, entries } of cities) {
  for (const entry of entries) {
    writePage(entry.path, guidePage(entry, entries.filter((e) => e !== entry)))
    written.add(entry.path)
  }
  const others = cities.map((c) => c.city).filter((c) => c.key !== city.key)
  writePage(`/guides/${city.key}/`, cityHubPage(city, entries, others))
  written.add(`/guides/${city.key}/`)
}

writePage('/guides/', hubPage(cities))

for (const [oldSlug, target] of Object.entries(LEGACY_REDIRECTS)) {
  const to = `/guides/${target}/`
  if (!written.has(to)) {
    // A quest was renamed or removed: point the old address somewhere real.
    throw new Error(`LEGACY_REDIRECTS: "${oldSlug}" forwards to ${to}, which is not a page.`)
  }
  writePage(`/guides/${oldSlug}/`, redirectPage(to))
}

const urls = [`${BASE_URL}/`, `${BASE_URL}/create`, ...[...written].map((p) => `${BASE_URL}${p}`)]
writeFileSync(
  join(DIST, 'sitemap.xml'),
  `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.map((u) => `  <url><loc>${u}</loc></url>`).join('\n')}
</urlset>
`,
)
writeFileSync(
  join(DIST, 'robots.txt'),
  `User-agent: *
Allow: /

Sitemap: ${BASE_URL}/sitemap.xml
`,
)

const guideCount = cities.reduce((n, c) => n + c.entries.length, 0)
console.log(
  `guides: ${guideCount} pages across ${cities.length} cities + hubs, ` +
    `${Object.keys(LEGACY_REDIRECTS).length} redirects, sitemap.xml, robots.txt`,
)
