// Serves /quest/* and /q/* to link-preview crawlers (see vercel.json
// rewrites) with per-quest og tags injected into the static index.html.
// Humans keep hitting the static SPA directly; only bot user agents land here.
//
// Two link generations:
//   /q/<shortId>  — quest lives in the backend store; fetch it (without
//                   counting a view) and render title + stop names.
//   /quest/<id>   — legacy fragment links; the quest never reaches the
//                   server, so ?st= (title) / ?sd= (description) params
//                   carry the preview text.

const TITLE_LIMIT = 120
const DESC_LIMIT = 200

// Railway backend. Override with QUEST_OG_API_BASE (or reuse the SPA's
// VITE_API_BASE_URL if it is exposed to the function runtime).
const API_BASE =
  process.env.QUEST_OG_API_BASE ??
  process.env.VITE_API_BASE_URL ??
  'https://moodyeat-production-f1b5.up.railway.app'

const OCCASION_LABELS = {
  date: 'Date night',
  friends: 'Friends hangout',
  solo: 'Solo time',
  family: 'Family outing',
}

async function fetchStoredQuestMeta(shortId) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 3000)
  try {
    const res = await fetch(
      `${API_BASE}/api/quest/stored/${encodeURIComponent(shortId)}?count_view=false`,
      { signal: controller.signal },
    )
    if (!res.ok) return null
    const quest = await res.json()
    if (!quest || typeof quest.title !== 'string' || !Array.isArray(quest.stops)) {
      return null
    }
    const names = quest.stops
      .map((stop) => stop?.place?.name)
      .filter((name) => typeof name === 'string' && name)
    const hours = Number(quest.total_duration_minutes) / 60
    const duration = Number.isFinite(hours)
      ? Number.isInteger(hours)
        ? `${hours}h`
        : `${hours.toFixed(1)}h`
      : null
    const summary = [
      OCCASION_LABELS[quest.occasion] ?? 'Quest',
      `${names.length} stops`,
      duration,
      typeof quest.created_by === 'string' && quest.created_by
        ? `by ${quest.created_by}`
        : null,
    ]
      .filter(Boolean)
      .join(' · ')
    const route = names.join(' → ')
    return {
      title: quest.title.slice(0, TITLE_LIMIT),
      description: (route ? `${summary} — ${route}` : summary).slice(0, DESC_LIMIT),
    }
  } catch {
    return null
  } finally {
    clearTimeout(timer)
  }
}

function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function setMeta(html, attr, name, value) {
  // Vite may format meta tags across multiple lines, so allow any whitespace
  // between attributes.
  const pattern = new RegExp(`(<meta\\s+${attr}="${name}"\\s+content=")[^"]*(")`)
  return html.replace(pattern, (_, before, after) => before + value + after)
}

export function injectQuestTags(html, { title, description, url }) {
  const safeTitle = escapeHtml(`${title} — MoodyEat`)
  html = html.replace(/<title>[^<]*<\/title>/, `<title>${safeTitle}</title>`)
  html = setMeta(html, 'property', 'og:title', safeTitle)
  html = setMeta(html, 'name', 'twitter:title', safeTitle)
  if (description) {
    const safeDesc = escapeHtml(`${description} — tap to see the full plan.`)
    html = setMeta(html, 'name', 'description', safeDesc)
    html = setMeta(html, 'property', 'og:description', safeDesc)
    html = setMeta(html, 'name', 'twitter:description', safeDesc)
  }
  if (url) {
    html = setMeta(html, 'property', 'og:url', escapeHtml(url))
  }
  return html
}

export default async function handler(req, res) {
  const proto = req.headers['x-forwarded-proto'] ?? 'https'
  const host = req.headers['x-forwarded-host'] ?? req.headers.host
  const origin = `${proto}://${host}`

  let html
  try {
    const upstream = await fetch(`${origin}/index.html`)
    if (!upstream.ok) throw new Error(`index.html fetch failed: ${upstream.status}`)
    html = await upstream.text()
  } catch {
    // Never let preview rendering take down the page for a crawler.
    res.statusCode = 302
    res.setHeader('Location', '/')
    res.end()
    return
  }

  const url = new URL(req.url, origin)

  const shortLinkMatch = url.pathname.match(/^\/q\/([a-z0-9]{4,16})$/)
  if (shortLinkMatch) {
    const meta = await fetchStoredQuestMeta(shortLinkMatch[1])
    if (meta) {
      html = injectQuestTags(html, {
        title: meta.title,
        description: meta.description,
        url: origin + url.pathname,
      })
    }
  } else {
    const title = (url.searchParams.get('st') ?? '').trim().slice(0, TITLE_LIMIT)
    const description = (url.searchParams.get('sd') ?? '').trim().slice(0, DESC_LIMIT)

    if (title) {
      html = injectQuestTags(html, {
        title,
        description,
        url: origin + url.pathname + url.search,
      })
    }
  }

  res.statusCode = 200
  res.setHeader('Content-Type', 'text/html; charset=utf-8')
  res.setHeader('Cache-Control', 'public, max-age=0, s-maxage=86400')
  res.end(html)
}
