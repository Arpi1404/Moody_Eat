// Fraunces/Inter load from Google Fonts, a cross-origin stylesheet that
// html-to-image can't read — captures used to silently fall back to Georgia.
// Instead we fetch the same CSS, keep only the latin faces the share card
// needs, inline their woff2 files as data URIs, and hand the result to
// toPng via fontEmbedCSS. Callers treat a failure as "no embed CSS" and the
// capture degrades to the serif fallback stack instead of erroring.

const FONT_CSS_URL =
  'https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,100..900&family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900&display=swap'

let cached: Promise<string> | null = null

async function toDataUri(url: string): Promise<string> {
  const blob = await (await fetch(url)).blob()
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(blob)
  })
}

async function buildFontEmbedCss(): Promise<string> {
  const css = await (await fetch(FONT_CSS_URL)).text()
  const faces = css
    .split('@font-face')
    .slice(1)
    .map((block) => `@font-face${block.slice(0, block.indexOf('}') + 1)}`)
    // The card renders latin text only; skip cyrillic/greek/vietnamese subsets.
    .filter((face) => face.includes('U+0000-00FF'))

  const inlined = await Promise.all(
    faces.map(async (face) => {
      const match = /url\((https:[^)]+)\)/.exec(face)
      if (!match) return face
      return face.replace(match[1], await toDataUri(match[1]))
    }),
  )
  return inlined.join('\n')
}

/** CSS with data-URI @font-face rules for the share card capture. Cached. */
export function shareCardFontEmbedCss(): Promise<string> {
  if (!cached) {
    cached = buildFontEmbedCss().catch((err) => {
      cached = null
      throw err
    })
  }
  return cached
}
