import { Link } from 'react-router-dom'
import '../App.css'

function LegalShell({
  title,
  updated,
  children,
}: {
  title: string
  updated: string
  children: React.ReactNode
}) {
  return (
    <main className="legal-page">
      <div className="legal-inner">
        <Link to="/" className="legal-back">
          ← Back to Home
        </Link>
        <h1 className="legal-title">{title}</h1>
        <p className="legal-updated">Last updated {updated}</p>
        {children}
      </div>
    </main>
  )
}

export function PrivacyPage() {
  return (
    <LegalShell title="Privacy" updated="July 2026">
      <h2>The short version</h2>
      <p>
        MoodyEat has no accounts and collects no personal information. Your
        saved quests and journal entries (including any photos and notes) live
        in your browser's local storage on your device — they are never
        uploaded to our servers.
      </p>

      <h2>What leaves your device</h2>
      <ul>
        <li>
          <strong>Quest requests.</strong> When you build a quest, the
          location text, occasion, budget, and duration you chose are sent to
          our server to find matching places. They are not stored or linked to
          you.
        </li>
        <li>
          <strong>Location access.</strong> If you tap "Use my current
          location", your coordinates are used once to detect your area (via
          OpenStreetMap Nominatim) and are not stored. Denying access works
          fine — just type an area instead.
        </li>
        <li>
          <strong>Analytics.</strong> We use Plausible, a cookie-free
          analytics tool that records aggregate page views and events (like
          "quest created") without identifying you.
        </li>
      </ul>

      <h2>Third-party data</h2>
      <p>
        Place details, ratings, photos, and opening hours come from Google
        Places and map tiles from OpenStreetMap. Their own terms apply to that
        content.
      </p>

      <h2>Sharing</h2>
      <p>
        When you copy a share link, the quest's details are encoded into the
        link itself. Anyone you send it to can see that quest — share links
        the way you'd share a screenshot.
      </p>

      <h2>Questions</h2>
      <p>
        Reach us on Instagram — we're a small team in Hyderabad and we read
        everything.
      </p>
    </LegalShell>
  )
}

export function TermsPage() {
  return (
    <LegalShell title="Terms" updated="July 2026">
      <h2>What MoodyEat is</h2>
      <p>
        MoodyEat suggests multi-stop outings built from public place data. It
        is a planning aid, not a booking service — we have no relationship
        with the venues we suggest.
      </p>

      <h2>Accuracy</h2>
      <p>
        Ratings, opening hours, prices, and photos come from third-party
        sources and can be wrong or out of date. Check with the venue before
        making a trip you care about. Travel times are estimates.
      </p>

      <h2>Fair use</h2>
      <p>
        Use MoodyEat for personal, non-commercial trip planning. Don't scrape,
        resell, or hammer the service with automated traffic.
      </p>

      <h2>Liability</h2>
      <p>
        MoodyEat is provided as-is, free of charge, without warranties of any
        kind. We are not liable for anything that happens on an outing —
        including a date that goes badly.
      </p>

      <h2>Changes</h2>
      <p>
        We may update these terms as the product evolves; the date above
        reflects the latest revision.
      </p>
    </LegalShell>
  )
}
