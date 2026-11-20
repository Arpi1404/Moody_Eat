// Roughly where the visitor is, from the IP address of the request — Vercel
// adds these headers to every function call. The home page uses it to pick
// which city's hand-made quests to show first and to rank location
// suggestions, without ever raising the browser's location prompt.
//
// City-level at best, so the answer is rounded to one decimal place (about
// 11 km) and never cached or stored.

export default function handler(req, res) {
  const lat = Number.parseFloat(req.headers['x-vercel-ip-latitude'])
  const lng = Number.parseFloat(req.headers['x-vercel-ip-longitude'])
  const known = Number.isFinite(lat) && Number.isFinite(lng)

  res.statusCode = 200
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.setHeader('Cache-Control', 'private, no-store')
  res.end(
    JSON.stringify(
      known
        ? { lat: Math.round(lat * 10) / 10, lng: Math.round(lng * 10) / 10 }
        : {},
    ),
  )
}
