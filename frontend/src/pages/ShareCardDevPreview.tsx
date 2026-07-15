import { useEffect, useRef, useState } from 'react'
import { toPng } from 'html-to-image'
import { shareCardFontEmbedCss } from '../lib/shareFonts'
import { ShareableQuestCard } from './ShareableQuestCard'
import type { Occasion, Quest } from '../types/quest'

// Dev-only harness (mounted behind import.meta.env.DEV) for iterating on the
// share card, which otherwise only renders off-screen during PNG capture.

const SAMPLE_QUEST: Quest = {
  id: 'dev-share-preview',
  title: 'Slow Evening in Jubilee Hills',
  occasion: 'date',
  stops: [
    {
      place: {
        provider_id: '',
        name: 'Roastery Coffee House',
        address: 'Banjara Hills, Hyderabad',
        lat: 17.41,
        lng: 78.44,
        distance_meters: 1200,
        rating: 4.6,
        user_ratings_total: 8200,
      },
      category: 'cafe',
      time_block_start: '17:00',
      time_block_end: '18:15',
      travel_to_next_minutes: 12,
      travel_mode: 'driving',
      why_this_place:
        'A leafy colonial bungalow pouring single-estate brews — the calmest way to start.',
    },
    {
      place: {
        provider_id: '',
        name: 'Sarva Bhavana',
        address: 'Jubilee Hills, Hyderabad',
        lat: 17.42,
        lng: 78.42,
        distance_meters: 2400,
        rating: 4.5,
        user_ratings_total: 3100,
      },
      category: 'restaurant',
      time_block_start: '18:30',
      time_block_end: '20:00',
      travel_to_next_minutes: 9,
      travel_mode: 'driving',
      why_this_place:
        'Seasonal thalis and low candlelight; the tasting menu is built for two.',
    },
    {
      place: {
        provider_id: '',
        name: 'Moonshine Project',
        address: 'Film Nagar, Hyderabad',
        lat: 17.41,
        lng: 78.41,
        distance_meters: 1800,
        rating: 4.4,
        user_ratings_total: 5400,
      },
      category: 'bar',
      time_block_start: '20:15',
      time_block_end: '21:45',
      travel_to_next_minutes: null,
      travel_mode: null,
      why_this_place:
        'Rooftop nightcap with skyline views — end the night above the city lights.',
    },
  ],
  total_duration_minutes: 285,
  total_cost_estimate: 'mid',
  created_by: 'Priya',
  narrative:
    'Three unhurried stops through the hills — coffee under old trees, a candlelit dinner, and a rooftop to close the night.',
  created_at: new Date().toISOString(),
}

export function ShareCardDevPreview() {
  const [viewportHeight, setViewportHeight] = useState(window.innerHeight)
  useEffect(() => {
    const onResize = () => setViewportHeight(window.innerHeight)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  const scale = Math.max(Math.min((viewportHeight - 32) / 1920, 0.5), 0.2)
  const cardRef = useRef<HTMLDivElement | null>(null)
  const [pngUrl, setPngUrl] = useState<string | null>(null)
  const [occasion, setOccasion] = useState<Occasion>('date')
  const [fourStops, setFourStops] = useState(false)
  const stops = fourStops
    ? [
        ...SAMPLE_QUEST.stops.slice(0, -1),
        {
          ...SAMPLE_QUEST.stops[0],
          place: { ...SAMPLE_QUEST.stops[0].place, name: 'Conçu Dessert Bar' },
          category: 'cafe' as const,
          time_block_start: '20:00',
          why_this_place: 'A sweet detour before the nightcap.',
        },
        SAMPLE_QUEST.stops[SAMPLE_QUEST.stops.length - 1],
      ]
    : SAMPLE_QUEST.stops
  const quest = { ...SAMPLE_QUEST, occasion, stops }

  const capture = async () => {
    const node = cardRef.current
    if (!node) return
    // Mirror the exact options QuestPage uses so this previews the real export.
    const fontEmbedCSS = await shareCardFontEmbedCss().catch(() => '')
    const dataUrl = await toPng(node, {
      backgroundColor: '#1c1310',
      cacheBust: true,
      fontEmbedCSS,
      pixelRatio: 1,
      skipFonts: true,
      width: 1080,
      height: 1920,
    })
    setPngUrl(dataUrl)
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        gap: 24,
        padding: '16px',
        background: '#2a2521',
      }}
    >
      <div
        style={{
          width: 1080 * scale,
          height: 1920 * scale,
          overflow: 'hidden',
          borderRadius: 12,
          boxShadow: '0 24px 80px rgba(0,0,0,0.5)',
        }}
      >
        <div style={{ transform: `scale(${scale})`, transformOrigin: 'top left' }}>
          <ShareableQuestCard ref={cardRef} quest={quest} />
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {(['date', 'friends', 'solo', 'family'] as Occasion[]).map((o) => (
          <button
            key={o}
            onClick={() => setOccasion(o)}
            style={{
              padding: '8px 14px',
              fontSize: 14,
              fontWeight: o === occasion ? 700 : 400,
            }}
          >
            {o}
          </button>
        ))}
        <button
          onClick={() => setFourStops((v) => !v)}
          style={{ padding: '8px 14px', fontSize: 14 }}
        >
          {fourStops ? '4 stops' : '3 stops'}
        </button>
        <button onClick={capture} style={{ padding: '10px 16px', fontSize: 14 }}>
          Capture PNG
        </button>
        {pngUrl && (
          <img
            src={pngUrl}
            alt="Captured share card"
            style={{ width: 1080 * scale, height: 1920 * scale, borderRadius: 12 }}
          />
        )}
      </div>
    </div>
  )
}
