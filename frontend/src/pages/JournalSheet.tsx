import { useEffect, useRef, useState } from 'react'
import type { JournalEntry } from '../types/journal'
import type { Quest } from '../types/quest'

const RATING_FACES = ['😞', '😕', '🙂', '😄', '🤩']
const MAX_PHOTO_BYTES = 1024 * 1024
const MAX_PHOTO_EDGE = 1400

function dataUrlBytes(dataUrl: string): number {
  const base64 = dataUrl.split(',')[1] ?? ''
  return Math.ceil((base64.length * 3) / 4)
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = reject
    image.src = src
  })
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result === 'string') resolve(reader.result)
      else reject(new Error('Could not read image.'))
    }
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

async function resizePhoto(file: File): Promise<string> {
  const original = await readFileAsDataUrl(file)
  const image = await loadImage(original)
  const scale = Math.min(1, MAX_PHOTO_EDGE / Math.max(image.width, image.height))
  const width = Math.max(1, Math.round(image.width * scale))
  const height = Math.max(1, Math.round(image.height * scale))
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height

  const context = canvas.getContext('2d')
  if (!context) throw new Error('Could not resize image.')
  context.drawImage(image, 0, 0, width, height)

  // TODO: move to backend storage post-v1. Base64 photos in localStorage do not scale.
  return canvas.toDataURL('image/jpeg', 0.82)
}

export function JournalSheet({
  quest,
  onSave,
  onCancel,
}: {
  quest: Quest
  onSave: (entry: JournalEntry) => void
  onCancel: () => void
}) {
  const [rating, setRating] = useState<number | null>(null)
  const [photos, setPhotos] = useState<string[]>([])
  const [note, setNote] = useState('')
  const [processingPhotos, setProcessingPhotos] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const toastTimer = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (toastTimer.current) window.clearTimeout(toastTimer.current)
    }
  }, [])

  const showToast = (message: string) => {
    setToast(message)
    if (toastTimer.current) window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(null), 2400)
  }

  const handlePhotoChange = async (files: FileList | null) => {
    if (!files?.length) return
    setProcessingPhotos(true)
    const accepted: string[] = []
    let rejected = 0

    for (const file of Array.from(files)) {
      try {
        const resized = await resizePhoto(file)
        if (dataUrlBytes(resized) > MAX_PHOTO_BYTES) {
          rejected += 1
          continue
        }
        accepted.push(resized)
      } catch {
        rejected += 1
      }
    }

    if (accepted.length > 0) setPhotos((current) => [...current, ...accepted])
    if (rejected > 0) {
      showToast('Some photos were too large after resize. Keep each under 1MB.')
    }
    setProcessingPhotos(false)
  }

  const handleSave = () => {
    if (rating == null) return
    onSave({
      questId: quest.id,
      completedAt: new Date().toISOString(),
      rating,
      photos,
      note: note.trim(),
    })
  }

  return (
    <div className="journal-sheet-overlay" role="presentation">
      <button
        type="button"
        className="journal-sheet-backdrop"
        aria-label="Close journal sheet"
        onClick={onCancel}
      />
      <section
        className="journal-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="journal-sheet-title"
      >
        <div className="journal-sheet-handle" aria-hidden />
        <header className="journal-sheet-header">
          <p className="journal-sheet-eyebrow">Quest complete</p>
          <h2 id="journal-sheet-title">Capture the memory</h2>
          <p>{quest.title}</p>
        </header>

        <div className="journal-field">
          <span className="journal-field-label">How did it feel?</span>
          <div className="journal-rating-row" role="radiogroup" aria-label="Overall rating">
            {RATING_FACES.map((face, index) => {
              const value = index + 1
              return (
                <button
                  key={face}
                  type="button"
                  className={`journal-rating-btn${rating === value ? ' journal-rating-btn--active' : ''}`}
                  role="radio"
                  aria-checked={rating === value}
                  onClick={() => setRating(value)}
                >
                  {face}
                </button>
              )
            })}
          </div>
        </div>

        <div className="journal-field">
          <label className="journal-upload">
            <span className="journal-field-label">Photos optional</span>
            <span className="journal-upload-box">
              {processingPhotos ? 'Resizing photos...' : 'Add photos'}
            </span>
            <input
              type="file"
              accept="image/*"
              multiple
              disabled={processingPhotos}
              onChange={(event) => handlePhotoChange(event.currentTarget.files)}
            />
          </label>
          {photos.length > 0 && (
            <div className="journal-photo-preview-row">
              {photos.map((photo, index) => (
                <img key={`${photo.slice(0, 32)}-${index}`} src={photo} alt="" />
              ))}
            </div>
          )}
        </div>

        <label className="journal-field">
          <span className="journal-field-label">One-line note optional</span>
          <input
            className="journal-note-input"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            maxLength={120}
            placeholder="What should you remember?"
          />
        </label>

        <button
          type="button"
          className="journal-save-btn"
          disabled={rating == null || processingPhotos}
          onClick={handleSave}
        >
          Save memory
        </button>
        <button type="button" className="journal-cancel-btn" onClick={onCancel}>
          Not now
        </button>
      </section>

      {toast && (
        <div className="saved-toast" role="status" aria-live="polite">
          {toast}
        </div>
      )}
    </div>
  )
}
