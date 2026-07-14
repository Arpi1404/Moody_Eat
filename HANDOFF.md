# MoodyEat — Engineering Handoff

_Written 14 July 2026. Context document for any agent/developer picking up this
project. Read this together with `ROADMAP.md` (marketing plan + product gates)
and `README.md` (setup + env vars)._

---

## 1. What this product is

**MoodyEat** (https://www.moodyeat.in) plans an evening out in Hyderabad:
pick an occasion (date / friends / solo / family), a time of day, a budget,
and 1–4 stops — the engine returns a "quest": real Google Places venues,
scheduled with travel legs and time blocks, with ₹ per-person estimates, a
map, and a shareable link/story card. Users can also hand-assemble a quest
at `/create`. India-only, IG-native audience, no signup.

**North-star metric:** shares per completed quest (see `ROADMAP.md`).
Instrumented via Plausible.

### Stack & deploys
| Layer | Tech | Deploy |
|---|---|---|
| Frontend | React 19 + TypeScript + Vite 6 + React Router 7 | Vercel, auto-deploys `main` → www.moodyeat.in |
| Backend | FastAPI + Pydantic v2 + httpx (Python 3.11) | Railway, auto-deploys `main` → moodyeat-production-f1b5.up.railway.app |
| Places data | Google Places API (New) `places:searchNearby` + legacy Details for hours/photos | key in Railway env |
| Weather | Open-Meteo (free, keyless) | — |
| Analytics | Plausible (`frontend/src/lib/analytics.ts`) | — |
| Errors | Sentry SDK installed, **opt-in**: activates only when `SENTRY_DSN` env is set on Railway | — |

### Repo map (the parts that matter)
```
backend/
  quest_generator.py        # the engine: scoring, viability, scheduling, weather gating
  quest_templates.py        # stop-sequence templates per occasion (ordered type fallbacks)
  price_inference.py        # price signal chain + INR band tables
  curated_quests.py         # 12 hand-authored Hyderabad quests (3 per occasion)
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
  lib/questBuild.ts         # SHARED schedule math (mirrors backend travel model) + custom-quest assembly
  lib/questHistory.ts       # recent-places memory for repeat-visitor variety
  lib/budget.ts             # ₹ formatting (incl. "under ₹X" / "Free" clamps)
  lib/questShare.ts         # #q= fragment share encoding (whole Quest object, deflate+base64url)
frontend/scripts/
  generate-guides.mjs       # postbuild: static SEO pages under dist/guides/ + sitemap + robots
  curated-snapshot.json     # checked-in data for deterministic guide builds
frontend/api/quest-og       # Vercel function: OG preview for crawlers hitting /quest/* (from share-card PR)
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
   Plausible event, one vote per quest via localStorage); Sentry opt-in;
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

Also merged during this period (by the owner, not this engagement):
**`51645a2`** — dark editorial share-card redesign PR + `/api/quest-og`
crawler preview function.

### Analytics events added (Plausible)
`quest_generated` (occasion, budget, day_part, stops_requested, stop_count),
`quest_reshuffled`, `quest_feedback` (vote), `custom_quest_created`,
`build_own_tapped`, `stops_reordered`, `quest_shared` (share_method now
includes `whatsapp`). Pre-existing funnel events unchanged.

---

## 3. Current state & known quirks (verify, don't assume)

- **Production is healthy** (last verified 14 Jul 2026): budget changes
  picks, day-part shifts schedules, quality filters active, guides live.
- **Local dev is broken**: the Google key in `backend/.env` (untouched since
  May) returns "You must enable Billing" for ALL Places calls. The owner
  believes this was fixed — as of 14 Jul it was not. Workaround used for
  browser QA: a tiny local FastAPI proxy on :8000 forwarding to the Railway
  backend with permissive CORS (prod's `ALLOWED_ORIGINS` doesn't include
  localhost). Rebuild it in a scratch dir if needed, or fix the key.
- **Search Console**: domain property verified, sitemap submitted 14 Jul,
  status "Couldn't fetch" = normal first-crawl lag. Sitemap confirmed live
  (200) at https://www.moodyeat.in/sitemap.xml.
- **Sentry**: code ships ready; activates only when `SENTRY_DSN` is set on
  Railway. Unknown whether the owner has set it.
- **Google billing**: `priceRange` in the field mask may bill searchNearby
  at a higher SKU tier — watch the first weeks. A billing alert is
  recommended (see next steps).
- **Curated snapshot**: `frontend/scripts/curated-snapshot.json` must be
  refreshed after editing `backend/curated_quests.py` (command in the
  script header), or guide pages go stale.
- **12 backend test warnings** are just `datetime.utcnow()` deprecation in
  models — known, harmless, fix opportunistically.

### Commands
```
# backend tests (61)          # frontend
cd backend                     cd frontend
venv\Scripts\python -m pytest  npm run build   # also generates dist/guides/
                               npm run lint    # must stay at 0 problems
```

---

## 4. Next steps (agreed with the owner — do these)

### Tier 1 — highest value
1. **Short links + quest store + per-quest OG previews.**
   Decision made: **SQLite on a Railway volume** (~$0.25–0.50/mo), NOT
   Postgres, NOT free external DBs (they pause on inactivity). Waiting on
   the owner to attach a volume (Railway → service → Settings → Volumes,
   e.g. mount `/data`) and share the mount path. Then build:
   `POST /api/quest/store` → `moodyeat.in/q/<shortid>`; extend the existing
   `/api/quest-og` crawler function (or backend equivalent) so each shared
   quest renders its own title/stops/image in WhatsApp; count views —
   this finally measures the receiving side of the share loop. Replaces the
   800-char `#q=` URLs (keep them working as fallback for old links).
2. **Creator-named quests.** Optional "made by" name on `/create`, shown on
   quest page + share card. Turns the influencer program self-serve
   ("Priya's Old City Crawl"). ~1 day.
3. **Pure-veg filter.** Places API (New) exposes `servesVegetarianFood` —
   add to the field mask (check SKU impact), a "Pure veg" toggle in the
   builder filtering food stops. Deeply India-relevant, no competitor does
   it well.

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
   notice.
8. **Google Cloud billing alert** (owner action, ~5 min, no code).
9. **Uptime monitoring** on the Railway backend (UptimeRobot free tier).

### Deliberately NOT doing (gates from ROADMAP.md still apply)
- Second city before Hyderabad shows ≥100 weekly quest creations and ≥25%
  creator retention. Curated content doesn't copy-paste.
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
