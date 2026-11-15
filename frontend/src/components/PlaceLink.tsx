import type { ReactNode } from 'react'
import { track } from '../lib/analytics'
import { googleMapsPlaceUrl, type LinkablePlace } from '../lib/placeLinks'

/** Where in the app the link was tapped (sent with the analytics event). */
export type PlaceLinkSurface = 'quest' | 'swap' | 'create' | 'results'

function ExternalIcon() {
  return (
    <svg
      className="place-link-icon"
      width="11"
      height="11"
      viewBox="0 0 12 12"
      fill="none"
      aria-hidden
    >
      <path
        d="M4 2.5h5.5V8M9.5 2.5 2.5 9.5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** The name with the arrow tied to its last word, so on a narrow card the
 * arrow never wraps onto a line of its own. */
function NameWithIcon({ name }: { name: string }) {
  const trimmed = name.trim()
  const cut = trimmed.lastIndexOf(' ') + 1
  return (
    <>
      {trimmed.slice(0, cut)}
      <span className="place-link-tail">
        {trimmed.slice(cut)}
        <ExternalIcon />
      </span>
    </>
  )
}

/** Opens a place's Google Maps page in a new tab.
 *
 * Renders its children (the place name when there are none) followed by a
 * small arrow. `decorative` is for a second link to the same place inside one
 * card (the photo): it stays tappable, gets no arrow, and is skipped by
 * keyboards and screen readers, which reach the place through the name. */
export function PlaceLink({
  place,
  surface,
  className = 'place-link',
  decorative = false,
  children,
}: {
  place: LinkablePlace
  surface: PlaceLinkSurface
  className?: string
  decorative?: boolean
  children?: ReactNode
}) {
  return (
    <a
      className={className}
      href={googleMapsPlaceUrl(place)}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={decorative ? undefined : `${place.name} on Google Maps`}
      aria-hidden={decorative || undefined}
      tabIndex={decorative ? -1 : undefined}
      onClick={() =>
        track('place_opened', { place_id: place.provider_id, surface })
      }
    >
      {decorative ? (
        children
      ) : children == null ? (
        <NameWithIcon name={place.name} />
      ) : (
        <>
          {children}
          <ExternalIcon />
        </>
      )}
    </a>
  )
}
