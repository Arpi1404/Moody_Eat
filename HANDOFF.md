# MoodyEat — Engineering Handoff

_Written 14 July 2026. Context document for any agent/developer picking up this
project. Read this together with `ROADMAP.md` (marketing plan + product gates)
and `README.md` (setup + env vars)._

---

## 1. What this product is

**MoodyEat** (https://www.moodyeat.in) plans an evening out, wherever you are:
pick an occasion (date / friends / solo / family), a time of day, a budget,
and 1–4 stops — the engine returns a "quest": real Google Places venues,
scheduled with travel legs and time blocks, with ₹ per-person estimates, a
map, and a shareable link/story card. Users can also hand-assemble a quest
at `/create`. Quests can be built anywhere; Hyderabad, Bangalore and
Gurgaon also have six hand-made quests each. The copy never ties the
product to a city or country — it sells quests. IG-native audience, no
signup. (Budgets and price estimates are still in ₹.)

**North-star metric:** shares per completed quest (see `ROADMAP.md`).
Instrumented via Umami.

### Stack & deploys
| Layer | Tech | Deploy |
|---|---|---|
| Frontend | React 19 + TypeScript + Vite 6 + React Router 7 | Vercel, auto-deploys `main` → www.moodyeat.in |
| Backend | FastAPI + Pydantic v2 + httpx (`python:3.13-slim` image) | **Cloud Run**, service `moodyeat-api` (asia-south1) → moodyeat-api-tm4cqfantq-el.a.run.app. **Deployed by hand — pushing `main` does not update it** (see Deploying) |
| Places data | Google Places API (New) `places:searchNearby` + legacy Details for hours/photos | key in the Cloud Run service env |
| Weather | Open-Meteo (free, keyless) | — |
| Analytics | Umami Cloud, free plan (`frontend/src/lib/analytics.ts`; script tag in `frontend/index.html`) | — |
| Errors | Sentry SDK installed, **opt-in**: activates only when `SENTRY_DSN` env is set on the Cloud Run service (not set as of 14 Nov 2026) | — |

### Deploying
- **Frontend:** push `main`. Vercel builds and publishes www.moodyeat.in
  (live about 20 s after the push on 14 Nov 2026).
- **Backend:** not connected to git. From the repo root, with `gcloud`
  signed in to the project:
  ```
  gcloud run deploy moodyeat-api --source backend --region asia-south1
  ```
  It builds `backend/Dockerfile` from the **working tree, not a commit** —
  run `git status --short backend` first. `backend/.gcloudignore` decides
  what is uploaded. The service keeps its env vars and limits (1 CPU,
  512 MB, max 3 instances) and the new revision takes 100% of traffic.
  Takes a few minutes.
- **Service env:** `GOOGLE_PLACES_API_KEY`, `OPENCODE_API_KEY`,
  `ALLOWED_ORIGINS`, `QUEST_STORE_BACKEND=firestore` (Cloud Run's disk is
  wiped between instances, so share links live in Firestore).
- **Order matters when a change spans both.** The frontend is live seconds
  after a push; the backend only when someone runs the deploy. On
  14 Nov 2026 a frontend that sent `location_label` reached a backend that
  ignored it, and quest descriptions showed raw coordinates until the
  backend was deployed. Deploy the backend first when it stays compatible
  with the old frontend (it ignores request fields it doesn't know), then
  push.
- **Checking what is running:** `GET /openapi.json` on the service lists
  the request fields the live revision accepts — free, no Places quota.
  Roll back with `gcloud run services update-traffic moodyeat-api
  --region asia-south1 --to-revisions <revision>=100`.
- **Railway is no longer the backend.** moodyeat-production-f1b5.up.railway.app
  returns 404 as of 14 Nov 2026. Whether the Railway project (and the
  SQLite share-link data on its volume) still exists was not checked.

### Repo map (the parts that matter)
```
backend/
  quest_generator.py        # the engine: scoring, viability, scheduling, weather gating
  quest_store.py            # shared-quest store (short links, view counts): SQLite on /data, or Firestore via QUEST_STORE_BACKEND
  quest_templates.py        # stop-sequence templates per occasion (ordered type fallbacks)
  price_inference.py        # price signal chain + INR band tables
  curated_quests.py         # city registry: 3 cities x 6 hand-authored quests, lookups by name / quest id
  curated/<city>.py         # the quests themselves (hyderabad, bangalore, gurgaon) + builders.py
  scripts/lookup_place.py   # venue name -> ready-to-paste place(...) with real Place ID, rating, hours
  scripts/verify_curated.py # asks Google: every curated stop still open, 4.0+, pin within 500 m
  scripts/export_curated.py # writes frontend/scripts/curated-snapshot.json for the guide pages
  models.py                 # Pydantic models incl. QuestGenerationRequest
  routes.py                 # /api/quest/generate, /alternatives, /places/nearby, curated
  services/
    google_places.py        # Places API (New) + legacy fallback (PLACES_USE_NEW_API flag)
    nearby_places_service.py# geocode + fetch + QUALITY FILTERS (type/name denylists)
    weather_service.py      # Open-Meteo rain check (fail-open)
  tests/                    # 61 tests; conftest.py stubs weather so the suite is offline
frontend/src/
  pages/HomePage.tsx        # occasion tiles + builder sheet (when/budget/stops stepper)
  pages/CreateQuestPage.tsx # custom quest builder (/create)
  pages/QuestPage.tsx       # quest view: chips, feedback, share sheet (WhatsApp/PNG/link), shuffle
  pages/QuestCard.tsx       # map + stop cards + swap + reorder
  lib/cities.ts             # the 3 curated cities, nearest-city maths, saved pick, rough visitor position
  lib/questBuild.ts         # SHARED schedule math (mirrors backend travel model) + custom-quest assembly
  lib/questHistory.ts       # recent-places memory for repeat-visitor variety
  lib/budget.ts             # ₹ formatting (incl. "under ₹X" / "Free" clamps)
  lib/questShare.ts         # #q= fragment share encoding (whole Quest object, deflate+base64url)
frontend/scripts/
  generate-guides.mjs       # postbuild: static SEO pages under dist/guides/<city>/ + sitemap + robots
  curated-snapshot.json     # checked-in data for deterministic guide builds
marketing/                  # 6-week launch playbook, captions, reddit post, influencer DM
                            # (assets: dev route /dev/marketing-cards renders curated quests
                            #  into IG story/feed PNGs via the share-card component)
frontend/api/quest-og       # Vercel function: OG preview for crawlers hitting /quest/* (from share-card PR)
frontend/api/geo            # Vercel function: visitor's rough position from Vercel's IP headers
```

---

## 2. What was built in this engagement (commits on `main`)

Chronological; each was tested (backend pytest, frontend build+lint) and
verified in a real browser before push.

1. **`b0b4048` — budget-aware quests.** Root cause of "same suggestions
   regardless of budget": legacy Nearby Search returns no price data for
   Indian places. Migrated to Places API (New) with `priceLevel` +
   `priceRange` (real INR) in the field mask; `PLACES_USE_NEW_API=false`
   env flag instantly reverts to legacy. Added a price-inference chain
   (`google_price_range` → `google_price_level` → type/name heuristics
   like dhaba/tiffin vs lounge/brewery → unknown) with per-source scoring
   confidence. Surfaced ₹ per stop + per-quest totals in API and UI. Added
   `variety_seed` (shuffles only near-tied top candidates). Fixed swap
   `cost_change` (was hardcoded 0). Fixed logging (app telemetry was
   silently dropped — `logging.basicConfig` in `main.py`).

2. **`c38e9e8` — Track 1–3 batch.** Stop-count selector; reorder stops with
   client-side schedule recompute; 👍/👎 plan feedback (`quest_feedback`
   analytics event, one vote per quest via localStorage); Sentry opt-in;
   hours-unknown places became a *last resort* instead of a hard reject;
   both long-standing ESLint errors fixed (lint is clean — keep it that way).

3. **`d0c622e` — day-part selection.** Start time was hardcoded per occasion
   (solo=10am, date=7pm…). `day_part` (morning/afternoon/evening/night →
   10:00/13:00/17:30/20:00) overrides it; opening-hours viability then
   naturally rejects e.g. parks at night. "When?" pills with per-occasion
   defaults.

4. **`5cd1989` — stops stepper replaces duration.** Removed the "How long?"
   input (it stretched dwell times artificially); duration is now an output.
   `stop_count` range 1–4 via a −/+ stepper (1 = "just pick me one place").
   Shortfall notices now compare against the *requested* count.

5. **`ce930d6` — quest quality filters.** Live QA found "Soulmate Pet
   Services" served as a family activity. Type denylist gained
   veterinary_care/pet_store/doctor/…; name denylist gained
   services/institute/academy/classes/clinic/…. Cheap quests hard-reject
   places *known* to be price level ≥3 while cheaper viable options exist
   (kept as last resort otherwise — a stop is never emptied). ₹ display:
   "≈₹1–200" → "under ₹200"; free band → "Free".

6. **`e21dd26` — custom quest builder + WhatsApp sharing.** `/create`:
   search places by category via existing `/api/places/nearby`, add 1–4
   stops, reorder, create. Assembly is fully client-side
   (`lib/questBuild.ts` — extracted the schedule math shared with
   swap/reorder), producing a standard Quest so everything downstream works
   unchanged. Share sheet gained "Share on WhatsApp" (wa.me deep link,
   `share_method: whatsapp`) as the first option.

7. **`16c6d09` — monsoon awareness.** Open-Meteo hourly precipitation
   probability for the quest's 4-hour window; ≥60% drops outdoor-certain
   types (park/zoo/amusement_park) from a stop's fallback chain — only when
   an indoor alternative exists. Quest carries a user-visible
   `weather_note`. Fail-open on any error; results cached 30 min;
   `tests/conftest.py` stubs it so the suite never hits the network.

8. **`7b50333` — repeat-visitor variety + SEO guide pages.**
   `exclude_place_ids` on the generate request (soft exclusion: recently
   seen places lose only while fresh options exist); frontend keeps a
   14-day localStorage history (cap 24) of generated-quest places.
   `postbuild` script renders the 12 curated quests as static HTML at
   `/guides/<slug>/` + hub + `sitemap.xml` + `robots.txt` from the
   checked-in snapshot; Vercel serves static files before the SPA rewrite,
   footer links `/guides/` with a plain `<a>`.

9. **Short links + server-side quest store (Tier 1 #1).** SQLite on the
   Railway volume (`/data/quests.db`; `QUEST_DB_PATH` overrides,
   `backend/.data/` local fallback). `POST /api/quest/store` (content-hash
   deduped, 8-char short id, 100 KB cap, rate-limited) →
   `moodyeat.in/q/<shortid>`; `GET /api/quest/stored/<id>` serves it and
   counts a view (`?count_view=false` for crawlers), `/stats` exposes the
   count — the receiving side of the share loop is finally measured.
   Share sheet now produces short links (WhatsApp/copy), falling back to
   the old `#q=` fragment URL if the store API is down; old fragment links
   keep working. `/api/quest-og` fetches stored quests to render real
   per-quest previews (title + stop route) for `/q/*` crawler hits
   (vercel.json rewrite added). New route `/q/:shortId` in the SPA;
   `shared_quest_opened` analytics event on open.

10. **Creator-named quests + pure-veg filter (Tier 1 #2 and #3).**
    `Quest.created_by` (optional, ≤60 chars): a "Made by" field on `/create`
    titles the quest "Priya's Banjara Hills Quest" and shows a byline on the
    quest page ("✦ made by Priya"), the story card ("Curated by Priya"), and
    the OG preview ("· by Priya") — the influencer program is now self-serve.
    Pure veg shipped here too but was **removed in Nov 2026 (item 11)**.
    Analytics: `custom_quest_created` gains `has_creator_name` (boolean —
    the name itself never goes to analytics).

11. **Search fixes + pure-veg removal (Nov 2026).** Found by running real
    quest generations and reading the candidate pools.
    - **Pure veg removed end to end** (toggle, `pure_veg` request field,
      `veg_note`, `servesVegetarianFood` in the field mask). Google's flag
      is true for biryani/mandi/chicken restaurants, so the filter was
      close to a no-op: a "pure veg" family quest led with a biryani house.
      Dropping the field also takes searchNearby back down from the
      Enterprise + Atmosphere SKU to Enterprise (per Google's SKU table,
      `priceRange` is Enterprise; the veg flag was what raised the tier).
      If it comes back, key it on the `vegetarian_restaurant` type and the
      place name, not the flag. `marketing/captions.md` and
      `marketing/reddit-post.md` still advertise the toggle.
    - **📍 anchors to the device, not the city centre.** The button used to
      fill in the city name ("Hyderabad"), which geocodes to Himayatnagar —
      ~14 km from Gachibowli. It now sends `lat,lng` (rounded to 3 decimals)
      as `location` plus a display-only `location_label` ("Gachibowli,
      Hyderabad") used for the title and narrative, so coordinates never
      reach a title or a shared link. Typing in the field clears the
      coordinates. Privacy page updated to match.
    - **Split opening hours.** `PlaceHours.windows` carries every window of
      the day; the generator checks a slot against the window it falls in.
      Reading only the first window made parks (open mornings + evenings)
      and lunch/dinner restaurants look shut every evening.
    - **Wasted paid calls.** `meal_takeaway` dropped from the friends
      template (it is deny-listed, so its three searches always returned
      nothing); zoo/aquarium probe the widest radius first and skip the
      nearer tiers when it has nothing strong; geocoding is reused within a
      request instead of repeating once per search.
    Still open from that study: match on Google's primary type instead of
    any tag, slot-appropriate types (dessert ≠ bakery), day-part-aware stop
    order, and scoring the first stop on distance from the searched area.
    Also noticed: `deps.py` builds a new `NearbyPlacesService` per request,
    so the 10-minute places cache never survives across requests.

12. **Analytics moved from Plausible to Umami Cloud (Nov 2026).** The
    Plausible trial ended; Umami's free plan includes custom events. Only
    the script tag in `frontend/index.html` and the body of `track()`
    changed, so event names and properties are the same as before. The
    script tag sets three things on purpose:
    - `data-domains` — runs only on `moodyeat.in` / `www.moodyeat.in`, so
      localhost and Vercel preview deployments record nothing.
    - `data-exclude-search` and `data-exclude-hash` — Umami records the
      full URL by default. Fallback share links carry the quest title in
      `?st=` and the whole quest in `#q=`, and `/results?q=` carries the
      typed area, so both are left out. The cost: `utm_*` tags on links
      are not recorded either; referrers still are.
    There is no pre-load queue (Plausible had one). The Umami script sits
    ahead of the app bundle in `index.html` and both are deferred, so it is
    defined first; if it is blocked, `track()` is a no-op.

13. **Places open on Google Maps (Nov 2026).** Tester feedback: there was
    no way to look a suggested place up. Place names are now links to the
    place's Google Maps page (`components/PlaceLink.tsx`, URL built in
    `lib/placeLinks.ts` from the place id — no backend change, no extra
    API cost). Covered: quest stop cards (name and photo), swap-sheet
    alternatives ("View on Google Maps"), build-your-own search results and
    chosen stops, and the legacy `/results` list. Swap cards changed from a
    `<button>` to a wrapper holding a select button plus the link, because
    a link inside a button is invalid HTML. New analytics event
    `place_opened` (place_id, surface: quest | swap | create | results),
    alongside the existing `directions_opened`. Not covered: the static
    `/guides` pages and the map pins.

14. **Location suggestions (Nov 2026).** The "Where?" fields on the home
    sheet and on build-your-own now offer a dropdown of matching places as
    you type (`components/LocationInput.tsx`).
    - Backend: `GET /api/places/autocomplete?q=&session=` (Google Places
      Autocomplete (New); since the multi-city change it leans towards
      the visitor's rough position sent as `&lat=&lng=`, and is not limited
      to a country unless `SUGGEST_REGION_CODE` is set) and
      `GET /api/places/autocomplete/location?place_id=&session=` (Place
      Details, `location` field only). The key stays server-side.
    - Picking a suggestion reuses the 📍 hand-off: the request carries
      `lat,lng` as `location` and the readable name as `location_label`.
      Typing without picking still sends plain text, as before.
    - Cost: each search uses one session token, so the keystroke requests
      are free and the pick is one Place Details Essentials call. Typing
      and not picking is billed per request. Both have a monthly free
      allowance (10,000 on Google's global price list; the India list says
      70,000) — check which list the billing account is on.
    - Suggestions have their own rate limit (120/min per client,
      `SUGGEST_RATE_LIMIT_PER_MINUTE`) so typing cannot use up the one for
      searches. Nothing is cached: Google's terms do not allow it.
    - The dropdown carries the "Google Maps" attribution Google requires.
      If the endpoint fails the field is an ordinary text box.
    - Not covered: the legacy `/plan` page.

15. **First-visit tour (Nov 2026).** `components/WelcomeTour.tsx`,
    flags in `lib/onboarding.ts` (localStorage `moodyeat:tour_seen`,
    `moodyeat:quest_tips_seen`).
    - Home: a small "New here?" card appears 1.5 s after a first visit. It
      never blocks the page; the four-card tour opens only if tapped. Not
      shown to anyone whose browser already holds a quest, and not again
      after it is dismissed, finished, or a quest is generated.
    - "How it works" in the footer (`/?tour=1`) reopens it any time.
    - Quest page: a one-line tip above the stops explains the icon-only
      swap and reorder buttons, until dismissed. Not on read-only previews.
    - Analytics: `tour_opened` (source: nudge | link), `tour_closed` (step,
      completed), `tour_nudge_dismissed`.

16. **Three curated cities, quests anywhere (Nov 2026).** The site no
    longer presents itself as Hyderabad-only.
    - **Content.** Six quests per city (2 date, 2 friends, 1 solo, 1
      family) in `backend/curated/{hyderabad,bangalore,gurgaon}.py`.
      Hyderabad went from 12 to 6 and those six were repaired: the old
      place IDs had been resolved by a script that no longer worked, and
      one stop had closed (Farzi Cafe), one pointed at a corporate office
      (Ironhill), two were street addresses, two were rated 3.8, and
      several were scheduled outside opening hours. "Golconda Sunset…" is
      now "Golconda Afternoon…" because the fort shuts at 5. Bangalore and
      Gurgaon are new; the four old Gurgaon placeholders are gone.
    - **Checks.** `tests/test_curated_quests.py` (offline: mix, no repeated
      venue, real `ChIJ…` IDs, stops within 40 km of the centre, schedules
      that add up) and `scripts/verify_curated.py` (online: open, 4.0+,
      pin within 500 m). The verifier and the new `lookup_place.py` use
      Places API (New) — the legacy Details / Find Place endpoints are
      **not enabled** on this project's key.
    - **API.** `GET /api/quests/curated?city=` accepts keys and other
      names (bengaluru, gurugram, secunderabad);
      `GET /api/quests/curated/{id}` returns one quest so a curated link
      opens on any device.
    - **Home page.** City toggle under "We made these for you"
      (`lib/cities.ts`). First city shown: `/?city=<key>` link → the
      visitor's saved pick → the curated city within 40 km of their rough
      position → Hyderabad. Rough position = device location only if the
      site was already allowed (never a prompt on load), else
      `/api/geo` (Vercel IP headers; often a city off on mobile data).
      Delhi and Noida fall to Gurgaon. Visitors known to be elsewhere get
      a "we'll build a quest wherever you are" line. Six cards show as a
      3×2 grid from 900 px; narrower screens keep the swipe row.
    - **Guides.** `/guides/<city>/<slug>/` with a hub per city. The 12 old
      `/guides/<slug>/` addresses are static redirect stubs
      (`LEGACY_REDIRECTS` in `generate-guides.mjs`; the build fails if one
      points at a page that no longer exists).
    - **Analytics.** `curated_city_shown` (city, source: link | saved |
      device | ip | default), `curated_city_changed` (city), and
      `curated_quest_tapped` now carries `city`.
    - **Not covered.** Budgets and price bands are ₹-only, so a quest
      built outside India shows no estimate or an INR-shaped one;
      `/api/geo` does nothing in local dev (use `?city=`); the copy in
      each quest was written from general knowledge and checked against
      Google for existence, rating and hours, not walked by a local.

Also merged during this period (by the owner, not this engagement):
**`51645a2`** — dark editorial share-card redesign PR + `/api/quest-og`
crawler preview function.

### Analytics events added
`quest_generated` (occasion, budget, day_part, stops_requested, stop_count),
`quest_reshuffled`, `quest_feedback` (vote), `custom_quest_created`,
`build_own_tapped`, `stops_reordered`, `quest_shared` (share_method now
includes `whatsapp`), `shared_quest_opened` (short_id — recipient opened a
/q/ link; server-side `views` in the quest store counts the same thing
without needing the analytics provider), `custom_quest_created` also carries
`has_creator_name`. Pre-existing funnel
events unchanged.

---

## 3. Current state & known quirks (verify, don't assume)

- **Production is healthy** (last verified 20 Nov 2026, at the API level
  on Cloud Run revision `moodyeat-api-00004-sm7`, deployed that day with
  the multi-city backend: curated lists for all three cities and their
  other names, a curated quest by id, a generated quest, location
  suggestions leaning to a position, a place photo, a share-store lookup,
  and CORS from www.moodyeat.in. The frontend for it ships when
  Arpi1404/Moody_Eat#5 merges. Previous revision, for a rollback:
  `moodyeat-api-00003-xr7`).
- **Local dev works again** (verified 14 Nov 2026): the Google key in
  `backend/.env` returns Places data. Start the API from `backend/` with
  `.venv/bin/python -m uvicorn main:app --port 8000` — the venv's own
  `uvicorn` launcher points at the folder the venv was created in and
  fails. With `ALLOWED_ORIGINS` unset in the shell, CORS allows the local
  dev ports (5500, 5173, 3000); `frontend/.env.local` points at :8000.
- **Search Console**: domain property verified, sitemap submitted 14 Jul,
  status "Couldn't fetch" = normal first-crawl lag. Sitemap confirmed live
  (200) at https://www.moodyeat.in/sitemap.xml.
- **Sentry**: code ships ready; activates only when `SENTRY_DSN` is set on
  the Cloud Run service. It was not set as of 14 Nov 2026, so errors are
  not being reported anywhere.
- **Google billing**: `priceRange` in the field mask may bill searchNearby
  at a higher SKU tier — watch the first weeks. A billing alert is
  recommended (see next steps).
- **Curated snapshot**: `frontend/scripts/curated-snapshot.json` must be
  refreshed after editing anything under `backend/curated/`
  (`cd backend && python -m scripts.export_curated`), or guide pages go
  stale.
- **Borderline curated ratings**: Hotel Shadab, Nimrah, Paradise
  (Hyderabad) and Airlines Hotel (Bangalore) sit at exactly 4.0, COMO
  (Gurgaon) at 4.1 — the first to fail `verify_curated` if they dip.
- **12 backend test warnings** are just `datetime.utcnow()` deprecation in
  models — known, harmless, fix opportunistically.

### Commands
```
# backend tests (155)         # frontend
cd backend                     cd frontend
venv\Scripts\python -m pytest  npm run build   # also generates dist/guides/
                               npm run lint    # must stay at 0 problems
```

---

## 4. Next steps (agreed with the owner — do these)

### Tier 1 — highest value
1. ~~**Short links + quest store + per-quest OG previews.**~~ **DONE
   (15 Jul 2026, see item 9 above).** Owner attached the Railway volume at
   `/data`. Remaining nice-to-have: a *rendered OG image* per quest (the
   preview currently reuses the static brand image with per-quest
   title/description text; a @vercel/og card with the stop list would pop
   more in WhatsApp).
2. ~~**Creator-named quests.**~~ **DONE (15 Jul 2026, see item 10 above).**
3. ~~**Pure-veg filter.**~~ Shipped 15 Jul 2026, **removed Nov 2026** (see
   item 11 above for why and what a rebuild should key on).

### Tier 2 — engagement
4. **"Free right now" mode** — one tap: geolocation + current time as day
   part → instant quest, zero questions.
5. **Completion streaks/badges** — journal already records completions;
   surface streaks ("3 quests done 🔥"). Cheap retention for an IG-native
   audience; pairs with the variety feature.

### Tier 3 — ops hardening (cheap, mostly one-time)
6. **GitHub Actions CI** — pytest + frontend build/lint on every PR (owner
   now merges PRs; nothing gates them today).
7. **Schedule `backend/scripts/verify_curated.py`** weekly (GitHub Action)
   so closed/degraded curated venues get flagged before users or Google
   notice. It had silently stopped working (legacy API) and one curated
   stop had closed by the time anyone looked — worth doing now that there
   are 55 stops across three cities.
8. **Google Cloud billing alert** (owner action, ~5 min, no code).
9. **Uptime monitoring** on the Cloud Run backend (UptimeRobot free tier).

### Deliberately NOT doing (gates from ROADMAP.md still apply)
- A fourth curated city before the three live ones show demand
  (`curated_city_shown` / `curated_quest_tapped` by city). Curated content
  doesn't copy-paste. (The original one-city gate was lifted by the owner
  in Nov 2026.)
- Accounts/cross-device sync before users ask; localStorage is fine.
- Paid ads before the share loop proves out organically.
- Stop-type composition UI (works against the one-tap pitch).

---

## 5. Working conventions this project expects

- **Verify before claiming.** This owner checks. Test against production
  when local is broken; state exactly what was and wasn't verified.
- **Quality bar**: every change lands with backend tests + clean
  `npm run lint` + a real browser walkthrough of the affected flow
  (screenshots/text-dump proof). 61 tests passing and 0 lint problems is
  the baseline — don't regress it.
- **Fail-open for enrichments**: weather, price data, hours — a missing
  signal must never block or empty a plan. Follow the existing last-resort
  fallback patterns in `_pick_viable_candidate`.
- **Protect the one-tap pitch** (from ROADMAP.md): every new builder input
  must justify itself; prefer smart defaults over questions.
- **Commit style**: imperative subject, body explains the why, trailer
  `Co-Authored-By: Claude <model> <noreply@anthropic.com>` when
  agent-authored. Commit directly to `main` (owner's convention), rebase on
  `origin/main` before pushing (the owner merges PRs from GitHub too).
- **Frontend/backend must stay in lockstep on shared math**: the travel
  model in `lib/questBuild.ts` mirrors `quest_generator.py` constants
  (walk 80 m/min, drive 350 m/min, 1.4 km walk threshold, dwell minutes per
  category, day-part start times, INR level bands). Change one → change both.
