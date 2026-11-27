import { Link } from 'react-router-dom'
import { CONTACT_URL } from '../lib/contact'
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
    <LegalShell title="Privacy" updated="November 2026">
      <h2>The short version</h2>
      <p>
        MoodyEat has no accounts and never asks who you are. Your saved quests
        and journal live in your browser's local storage on your device. Your
        journal, photos and notes included, is never uploaded to our servers.
        A quest is stored on our server only when you share it (see Sharing
        below).
      </p>

      <h2>What leaves your device</h2>
      <ul>
        <li>
          <strong>Quest requests.</strong> When you ask us for a quest, the
          area you gave, the occasion, budget, time of day and number of stops,
          and the IDs of places from your recent quests (so we can suggest
          different ones) are sent to our server, which asks Google for
          matching places. A third-party AI service may be sent the area, the
          occasion, the budget and the places picked, to write the quest's
          introduction. We don't save your request or link it to you. Our
          server's technical logs can record the area a search was for.
        </li>
        <li>
          <strong>Location suggestions.</strong> As you type in the location
          field, what you have typed so far is sent to our server, and on to
          Google, to suggest matching places. It is not stored or linked to
          you.
        </li>
        <li>
          <strong>Search by name.</strong> When you search for a place by name
          while building your own quest, what you typed and the area you chose
          are sent to our server, and on to Google, to find matching places.
          We do not store what you typed or link it to you.
        </li>
        <li>
          <strong>Location access.</strong> If you tap "Use my current
          location", your coordinates are used to look up the name of your
          area (via OpenStreetMap Nominatim) and, rounded to about 100 metres,
          are sent to our server with that quest request so the plan is built
          around where you actually are. They are not stored. Denying access
          works fine — just type an area instead.
        </li>
        <li>
          <strong>Analytics.</strong> We use Umami, a cookie-free
          analytics tool that records aggregate page views and events (like
          "quest created") without identifying you.
        </li>
        <li>
          <strong>Swaps.</strong> When you swap a stop, we keep a record of
          which place you replaced and which one you chose instead, along
          with the occasion, the budget and the time of that stop. We use it
          to suggest better places in future plans. The record does not say
          who you are or which quest it came from, and it holds no location
          of yours, only the two places. Nothing is recorded if your browser
          sends a Do Not Track or Global Privacy Control signal.
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
        When you share a quest (on WhatsApp, by copying its link, or from the
        story-card option), we may store a copy of it on our server and give it
        a short link. The copy holds what the quest shows: its title, places,
        times and cost estimates, and anything you typed, including your "Made
        by" name, your intro and your notes on stops. We also keep how many
        times the link has been opened and when it was last opened. That count
        does not say who opened it.
      </p>
      <p>
        Anyone who has the link can see the quest, so share it the way you'd
        share a screenshot. We ask search engines not to list shared quests.
        If our server can't be reached, the link you get carries the whole
        quest inside the address instead.
      </p>
      <p>
        Changing a quest on your device does not change a link you have already
        sent; sharing again makes a new one. We keep shared quests until they
        are removed. To have one removed, or to report one,{' '}
        <a href={CONTACT_URL} target="_blank" rel="noopener noreferrer">
          message us on Instagram
        </a>{' '}
        with its link. Removing it stops the link working. It cannot reach
        copies people have already opened or saved, downloaded story cards, or
        previews other apps have kept.
      </p>

      <h2>Questions</h2>
      <p>
        <a href={CONTACT_URL} target="_blank" rel="noopener noreferrer">
          Reach us on Instagram
        </a>
        . We're a small team and we read everything.
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
