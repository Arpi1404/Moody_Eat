import type { PlaceItem } from '../api'

export type LinkablePlace = Pick<
  PlaceItem,
  'name' | 'address' | 'lat' | 'lng' | 'provider_id'
>

/** The place's own Google Maps page (reviews, photos, menu, phone).
 *
 * Uses Google's documented Maps URLs format, which opens the Maps app on
 * phones and the website elsewhere. `provider_id` is the Google place id, so
 * the link lands on the exact place rather than a search for its name. */
export function googleMapsPlaceUrl(place: LinkablePlace): string {
  const base = 'https://www.google.com/maps/search/?api=1'
  if (place.provider_id) {
    return `${base}&query=${encodeURIComponent(place.name)}&query_place_id=${encodeURIComponent(place.provider_id)}`
  }
  const text = [place.name, place.address].filter(Boolean).join(', ')
  return `${base}&query=${encodeURIComponent(text || `${place.lat},${place.lng}`)}`
}
