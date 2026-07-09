# MoodyEat — Marketing Plan & Post-Launch Roadmap

_Last updated: July 2026. Companion doc to the QA/fix work of July 7–9._

## Positioning

**One-liner:** Tell us the mood, we'll plan your evening in Hyderabad — 2–4 stops, mapped and timed.

**Audience:** Hyderabad, 18–30, IG-native. Couples planning dates, friend groups tired of "where should we go?" threads, solo explorers.

**What makes it different:** you don't assemble a plan — you get one. Real places, real ratings, walking times, one link to share with the group. Protect this in every feature decision: anything that turns the builder into homework dilutes the pitch.

**North-star metric: shares per completed quest.** Supporting funnel (already instrumented via Plausible `track()` events): visit → `quest_created` → `quest_saved` → `quest_started` → `quest_completed` → `quest_shared`.

## Launch gates (all must be true before spending effort on reach)

- [ ] `moodyeat.in` purchased, added to Vercel, HTTPS live
- [ ] Plausible site registered under the domain in `index.html`'s `data-domain` (currently `moodyeat.app` — update when domain lands) and events visibly arriving
- [ ] OpenCode API key rotated (fragments were logged pre-July-7)
- [ ] @moody_eat bio: site link + one-line pitch; first "how it works" post or highlight
- [ ] Directions buttons + 6 swap alternatives deployed without issues
- [ ] **The friend test:** send 5 real people a quest link on WhatsApp. Preview card renders, they open it, they understand it without you explaining. If this flops, fix product before promoting.

## Channel plan (all ₹0, effort only)

### 1. Instagram @moody_eat — the core channel
The product produces its own content: story cards and curated quests.

- **Cadence:** 2 reels + 1 carousel per week. Consistency beats volume.
- **Content pillars:**
  1. *Quest walkthroughs* — film a curated quest actually being done (Charminar → Shadab → Nimrah writes its own storyboard; the curated copy is already caption-grade).
  2. *Mood-based hooks* — "Date night in Banjara Hills under ₹1500", "4 hours free in HITEC, no plan? Watch."
  3. *UGC reshares* — every story-card share that tags you gets reshared. This is the flywheel; make it feel guaranteed.
- **First 9 grid posts:** 4 curated quest carousels, 2 walkthrough reels, 1 "how it works" (build → share card in 20s), 1 founder/why post, 1 poll-driven "you pick the next quest" post.
- **Every post CTA:** "Link in bio — build yours in 30 seconds."

### 2. Reddit + communities — one honest launch each
- r/hyderabad: "I built a free tool that plans your whole evening out in Hyderabad" — genuine builder post, screenshots, a couple of quest links (per-quest link previews now work). Answer every comment for 48h.
- 2–3 Hyderabad foodie Facebook/WhatsApp communities, same post adapted. One each. Never repeat-spam.

### 3. Micro-influencer named quests
- Target: 5–10 Hyderabad food/lifestyle pages, 10k–50k followers.
- Offer: a custom curated quest with their name on it ("Priya's Old City Crawl"), they post the story card, costs you a JSON entry.
- This becomes self-serve once the custom-quests feature ships (see roadmap #1).

### 4. WhatsApp soft-seeding
- Personal network first. The share link IS the product demo — previews now show the quest title and stops.

### Weekly review ritual (15 min)
Plausible funnel + IG insights. Ask one question: **are completed quests being shared?**
- Shares/completion < 10% → fix the share moment (card, CTA placement), don't buy more reach.
- Visits high but `quest_created` low → landing page/builder friction.
- Created high but `quest_started` low → plans aren't credible enough (place quality, duration honesty).

## Post-launch feature roadmap (in order)

### 1. Custom quests — user-assembled, shareable  *(~1–2 weeks; the growth feature)*
Users pick their own places (search via existing `/api/places/nearby`), order them, get the standard quest page + story card + share link. Why first: user-generated quests are share cards you didn't have to curate, and it makes the influencer program self-serve. The `#q=` share encoding already supports arbitrary quests — the work is the assembly UI.
*Success: % of shared quests that are custom-made.*

### 2. Stop-count selector (2/3/4 stops)  *(~2 days)*
The honest subset of "let users choose composition." Backend template insert logic already exists (long quests get a 4th stop). Do NOT ship full type-composition (1 cafe + 2 parks...) — it works against the one-tap pitch; revisit only if real users keep asking.
*Success: selector used without hurting quest completion rate.*

### 3. Reorder stops (drag or up/down)  *(~2–3 days)*
The client-side schedule/travel recompute from the swap fix already handles the math; this is mostly UI.
*Success: fewer abandoned quests after generation.*

### 4. Server-side quest store + short share links  *(~1 week; infra)*
Replaces 800-char `#q=` URLs with `moodyeat.in/q/abc123`, enables view counts on shared quests (finally: measure the receiving side of the loop) and real per-quest og images. Do this when share volume justifies it — the fragment links work fine at small scale.

### 5. Prerendered curated-quest landing pages (SEO)  *(~3–4 days)*
"Date night Banjara Hills", "things to do in Hyderabad today" — thin competition, high intent. Needs the curated quests rendered as static HTML at build time (vite-ssg or a small prerender script) so Google sees content, not an empty SPA shell.

### 6. Second city — gate, not a date
Expand (Bangalore first) only when Hyderabad shows: ≥100 weekly quest creations, ≥25% of creators returning within 30 days. Curated content is the moat and doesn't copy-paste; premature expansion just dilutes quality.

### 7. Accounts / cross-device sync — last
The mobile Profile tab stays "coming soon" until people actually ask to move quests between devices. localStorage is fine at this scale, and no signup is a feature while growing.

## Deliberately not doing

- Full stop-type composition UI (see #2)
- Paid ads before the share loop proves out organically
- Android/iOS wrapper apps — the mobile web app is already app-like; revisit at real scale
