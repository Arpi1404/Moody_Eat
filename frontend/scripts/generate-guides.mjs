// Build-time SEO pages: renders the curated quests as static HTML under
// dist/guides/, plus a hub page, sitemap.xml, and robots.txt. Runs via the
// `postbuild` npm hook, so `npm run build` produces them automatically.
//
// Data source is scripts/curated-snapshot.json — a checked-in copy so builds
// are deterministic and never depend on the backend being up. Refresh it
// after editing backend/curated_quests.py:
//   node -e "fetch('https://moodyeat-production-f1b5.up.railway.app/api/quests/curated?city=Hyderabad').then(r=>r.json()).then(q=>require('fs').writeFileSync('./scripts/curated-snapshot.json',JSON.stringify(q,null,2)))"

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const DIST = join(__dirname, '..', 'dist')
const BASE_URL = 'https://www.moodyeat.in'
const CITY = 'Hyderabad'

const OCCASION_LABEL = {
  date: 'Date night',
  friends: 'Friends hangout',
  solo: 'Solo day out',
  family: 'Family outing',
}

const quests = JSON.parse(
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
<footer>MoodyEat plans your evening out in ${CITY} — free, no signup. <a href="/">Build a quest</a> · <a href="/guides/">All guides</a></footer>
</div></body>
</html>`
}

function guidePage(quest, slug, others) {
  const occasion = OCCASION_LABEL[quest.occasion] ?? quest.occasion
  const stopNames = quest.stops.map((s) => s.place.name)
  const description =
    `${occasion} plan in ${CITY}: ${stopNames.join(' → ')}. ` +
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
    .slice(0, 4)
    .map(
      (o) =>
        `<li><a href="/guides/${o.slug}/">${esc(o.quest.title)}</a> — ${OCCASION_LABEL[o.quest.occasion] ?? o.quest.occasion}</li>`,
    )
    .join('\n')

  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'ItemList',
    name: `${quest.title} — ${occasion} in ${CITY}`,
    description,
    itemListElement: quest.stops.map((s, i) => ({
      '@type': 'ListItem',
      position: i + 1,
      name: s.place.name,
      description: s.why_this_place,
    })),
  }

  const body = `
<p class="eyebrow">${esc(occasion)} · ${CITY}</p>
<h1>${esc(quest.title)}</h1>
<p class="lede">${esc(quest.narrative)}</p>
${stopsHtml}
<a class="cta" href="/">Plan your own evening in 30 seconds →</a>
<a class="cta secondary" href="/create">Or build it stop by stop</a>
<section class="more">
<p class="eyebrow">More ${CITY} plans</p>
<ul>${othersHtml}</ul>
</section>
<script type="application/ld+json">${JSON.stringify(jsonLd)}</script>`

  return pageShell({
    title: `${quest.title} — ${occasion} in ${CITY} | MoodyEat`,
    description,
    canonical: `${BASE_URL}/guides/${slug}/`,
    body,
  })
}

function hubPage(entries) {
  const byOccasion = {}
  for (const e of entries) {
    ;(byOccasion[e.quest.occasion] ??= []).push(e)
  }
  const sections = Object.entries(byOccasion)
    .map(
      ([occ, list]) => `
<p class="eyebrow">${esc(OCCASION_LABEL[occ] ?? occ)}</p>
${list
  .map(
    (e) => `<a class="card" href="/guides/${e.slug}/">
<strong>${esc(e.quest.title)}</strong>
<span>${e.quest.stops.map((s) => esc(s.place.name)).join(' → ')}</span>
</a>`,
  )
  .join('\n')}`,
    )
    .join('\n')

  const description = `Hand-planned evenings out in ${CITY}: date nights, friends hangouts, solo days, and family outings — with timings, real places, and maps.`
  const body = `
<h1>${CITY} evening plans, ready to go</h1>
<p class="lede">${description}</p>
${sections}
<a class="cta" href="/">Plan a custom evening in 30 seconds →</a>`

  return pageShell({
    title: `Things to do in ${CITY}: ready-made evening plans | MoodyEat`,
    description,
    canonical: `${BASE_URL}/guides/`,
    body,
  })
}

// ── Generate ──────────────────────────────────────────────────────────────────

const entries = quests.map((quest) => ({ quest, slug: slugify(quest.title) }))

for (const entry of entries) {
  const others = entries.filter((e) => e.slug !== entry.slug)
  const dir = join(DIST, 'guides', entry.slug)
  mkdirSync(dir, { recursive: true })
  writeFileSync(join(dir, 'index.html'), guidePage(entry.quest, entry.slug, others))
}

mkdirSync(join(DIST, 'guides'), { recursive: true })
writeFileSync(join(DIST, 'guides', 'index.html'), hubPage(entries))

const urls = [
  `${BASE_URL}/`,
  `${BASE_URL}/create`,
  `${BASE_URL}/guides/`,
  ...entries.map((e) => `${BASE_URL}/guides/${e.slug}/`),
]
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

console.log(`guides: ${entries.length} pages + hub, sitemap.xml, robots.txt`)
