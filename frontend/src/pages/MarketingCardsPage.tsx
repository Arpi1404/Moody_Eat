import { useRef, useState } from 'react'
import { toPng } from 'html-to-image'
import JSZip from 'jszip'
import { shareCardFontEmbedCss } from '../lib/shareFonts'
import { ShareableQuestCard } from './ShareableQuestCard'
import type { Quest } from '../types/quest'
import curatedSnapshot from '../../scripts/curated-snapshot.json'

// Dev-only marketing asset factory (mounted behind import.meta.env.DEV).
// Renders every curated quest through the real share-card component and
// exports Instagram-ready PNGs:
//   story: 1080x1920  (Stories / Reels cover)
//   feed:  1080x1350  (grid post — the story card framed on the brand dark)
// Run the dev server with a backend that can serve /api/places/photo (e.g.
// the prod proxy) so the cards carry real photos instead of emoji tiles.

const QUESTS = curatedSnapshot as unknown as Quest[]

const STORY_W = 1080
const STORY_H = 1920
const FEED_W = 1080
const FEED_H = 1350
// Card scaled to sit inside the feed frame with breathing room.
const FEED_SCALE = 0.645

function slugify(title: string): string {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')
    .slice(0, 48)
}

function downloadPng(dataUrl: string, fileName: string) {
  const anchor = document.createElement('a')
  anchor.href = dataUrl
  anchor.download = fileName
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
}

async function waitForAssets(node: HTMLElement): Promise<void> {
  await document.fonts.ready.catch(() => undefined)
  const images = Array.from(node.querySelectorAll('img'))
  await Promise.all(
    images.map(async (image) => {
      if (image.complete && image.naturalWidth > 0) return
      await Promise.race([
        image.decode().catch(() => undefined),
        new Promise((resolve) => window.setTimeout(resolve, 1700)),
      ])
    }),
  )
}

export function MarketingCardsPage() {
  const cardRefs = useRef<(HTMLDivElement | null)[]>([])
  const frameRefs = useRef<(HTMLDivElement | null)[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [progress, setProgress] = useState<string | null>(null)
  const [lastPng, setLastPng] = useState<string | null>(null)

  const capture = async (
    node: HTMLElement | null,
    width: number,
    height: number,
  ): Promise<string | null> => {
    if (!node) return null
    await waitForAssets(node)
    const fontEmbedCSS = await shareCardFontEmbedCss().catch(() => '')
    const dataUrl = await toPng(node, {
      backgroundColor: '#1c1310',
      cacheBust: true,
      fontEmbedCSS,
      pixelRatio: 1,
      skipFonts: true,
      width,
      height,
    })
    setLastPng(dataUrl)
    return dataUrl
  }

  const downloadStory = async (index: number) => {
    setBusy(`story-${index}`)
    try {
      const dataUrl = await capture(cardRefs.current[index], STORY_W, STORY_H)
      if (dataUrl) {
        downloadPng(dataUrl, `moodyeat-${slugify(QUESTS[index].title)}-story.png`)
      }
    } finally {
      setBusy(null)
    }
  }

  const downloadFeed = async (index: number) => {
    setBusy(`feed-${index}`)
    try {
      const dataUrl = await capture(frameRefs.current[index], FEED_W, FEED_H)
      if (dataUrl) {
        downloadPng(dataUrl, `moodyeat-${slugify(QUESTS[index].title)}-feed.png`)
      }
    } finally {
      setBusy(null)
    }
  }

  // Browsers block bursts of programmatic downloads (Chrome allows only the
  // first few), so "download all" bundles every PNG into ONE zip file.
  const downloadAll = async () => {
    setBusy('all')
    try {
      const zip = new JSZip()
      const total = QUESTS.length * 2
      let done = 0
      const add = async (
        node: HTMLElement | null,
        width: number,
        height: number,
        fileName: string,
      ) => {
        done += 1
        setProgress(`Rendering ${done}/${total} — ${fileName}`)
        const dataUrl = await capture(node, width, height)
        if (dataUrl) {
          zip.file(fileName, dataUrl.split(',')[1], { base64: true })
        }
      }

      for (let i = 0; i < QUESTS.length; i += 1) {
        const slug = slugify(QUESTS[i].title)
        await add(cardRefs.current[i], STORY_W, STORY_H, `moodyeat-${slug}-story.png`)
        await add(frameRefs.current[i], FEED_W, FEED_H, `moodyeat-${slug}-feed.png`)
      }

      const fileCount = Object.keys(zip.files).length
      setProgress(`Zipping ${fileCount} files…`)
      const blob = await zip.generateAsync({ type: 'blob' })
      const url = URL.createObjectURL(blob)
      downloadPng(url, 'moodyeat-instagram-cards.zip')
      window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
      setProgress(
        `Done — moodyeat-instagram-cards.zip (${fileCount} files, ${(blob.size / 1024 / 1024).toFixed(1)} MB)`,
      )
    } catch (err) {
      setProgress(`Failed: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: '#141414', color: '#f4ede2', padding: 24 }}>
      <div style={{ maxWidth: 960, margin: '0 auto' }}>
        <h1 style={{ margin: '0 0 4px', fontSize: 22 }}>Marketing cards</h1>
        <p style={{ margin: '0 0 16px', fontSize: 13, opacity: 0.75 }}>
          {QUESTS.length} curated quests → story (1080×1920) + feed (1080×1350)
          PNGs, rendered by the production share-card component. Run against a
          backend with photo access for real images.
        </p>
        <button
          type="button"
          onClick={downloadAll}
          disabled={busy !== null}
          style={{ marginBottom: 8, padding: '10px 18px', fontSize: 14, cursor: 'pointer' }}
        >
          {busy === 'all' ? 'Rendering…' : `Download all ${QUESTS.length * 2} PNGs as one ZIP`}
        </button>
        {progress && (
          <p style={{ margin: '0 0 16px', fontSize: 13, opacity: 0.85 }} aria-live="polite">
            {progress}
          </p>
        )}

        {QUESTS.map((quest, i) => (
          <div
            key={quest.id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 16,
              padding: '10px 0',
              borderTop: '1px solid rgba(255,255,255,0.12)',
            }}
          >
            {/* Live thumbnail of the actual card */}
            <div style={{ width: STORY_W * 0.09, height: STORY_H * 0.09, overflow: 'hidden', flex: '0 0 auto' }}>
              <div style={{ transform: 'scale(0.09)', transformOrigin: 'top left' }}>
                <ShareableQuestCard
                  ref={(node) => {
                    cardRefs.current[i] = node
                  }}
                  quest={quest}
                />
              </div>
            </div>
            <div style={{ flex: 1 }}>
              <p style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>{quest.title}</p>
              <p style={{ margin: 0, fontSize: 12, opacity: 0.65 }}>
                {quest.occasion} · {quest.total_cost_estimate} · {quest.stops.length} stops
              </p>
            </div>
            <button type="button" disabled={busy !== null} onClick={() => downloadStory(i)} style={{ cursor: 'pointer' }}>
              {busy === `story-${i}` ? '…' : 'Story PNG'}
            </button>
            <button type="button" disabled={busy !== null} onClick={() => downloadFeed(i)} style={{ cursor: 'pointer' }}>
              {busy === `feed-${i}` ? '…' : 'Feed PNG'}
            </button>

            {/* Off-screen feed frame: the story card floated on the brand dark */}
            <div style={{ position: 'fixed', left: -20000, top: 0 }}>
              <div
                ref={(node) => {
                  frameRefs.current[i] = node
                }}
                style={{
                  width: FEED_W,
                  height: FEED_H,
                  background:
                    'radial-gradient(90% 60% at 12% 0%, rgba(217, 93, 46, 0.22), transparent 60%),' +
                    'radial-gradient(80% 55% at 95% 100%, rgba(232, 176, 75, 0.16), transparent 60%),' +
                    '#1c1310',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  overflow: 'hidden',
                }}
              >
                <div style={{ transform: `scale(${FEED_SCALE})`, flex: '0 0 auto' }}>
                  <ShareableQuestCard quest={quest} />
                </div>
              </div>
            </div>
          </div>
        ))}

        {lastPng && (
          <div style={{ marginTop: 20 }}>
            <p style={{ fontSize: 13, opacity: 0.75 }}>Last export preview:</p>
            <img src={lastPng} alt="Last exported card" style={{ maxWidth: 320, display: 'block' }} />
          </div>
        )}
      </div>
    </div>
  )
}

export default MarketingCardsPage
