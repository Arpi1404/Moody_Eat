---
name: Speed Up Places Calls
overview: Reduce end-to-end latency for `/api/places/nearby` by removing avoidable serial waits, limiting expensive pagination, and improving cache hit behavior while respecting Google API constraints.
todos:
  - id: parallelize-categories
    content: Fetch category Nearby calls concurrently with bounded semaphore
    status: pending
  - id: cap-pagination
    content: Add config-driven max page limit and early stop when limit reached
    status: pending
  - id: tune-timeouts
    content: Lower interactive timeout/retry defaults to reduce tail latency
    status: pending
  - id: cache-ux
    content: Increase cache hit ratio and keep blurbs non-blocking
    status: pending
isProject: false
---

# Speed Up Google Places Calls

## What is currently limiting speed
- `backend/services/nearby_places_service.py` performs category lookups sequentially (`for cat in categories: await ...`), so latency scales with number of categories.
- `backend/services/google_places.py` fetches up to 3 pages per category and must wait ~2s before each `next_page_token` page. This is a Google API behavior and cannot be bypassed.
- Retries/timeouts can amplify tail latency.

## Constraints (what is and is not possible)
- Getting exactly 20 results in one Nearby Search response is not possible; each page returns up to ~20 and additional pages require token delay.
- Faster first response is possible by reducing or deferring page 2/3 fetches and parallelizing independent category calls.
- Google-side network latency cannot be eliminated, only hidden/reduced via architecture and caching.

## Recommended strategy (in order)
1. Parallelize category fetches with bounded concurrency in `backend/services/nearby_places_service.py`.
   - Use `asyncio.gather` with a semaphore (e.g., 2-4 concurrent categories) to avoid quota spikes.
   - Keep dedupe/ranking logic unchanged.
2. Add early-stop pagination in `backend/services/google_places.py`.
   - Stop after page 1 once enough candidates are collected for requested `limit`.
   - Optionally make page 2/3 opt-in via config (e.g., `PLACES_MAX_PAGES`, default 1 for low latency).
3. Tune request/retry policy in `backend/config.py`.
   - Lower timeout and retries for interactive UX (e.g., timeout 4-6s, retries 0-1).
   - Keep conservative values for background jobs if needed.
4. Improve cache effectiveness in `backend/services/nearby_places_service.py`.
   - Keep TTL cache but normalize request keys consistently and consider per-query warm cache for hot searches.
5. Frontend UX optimization in `frontend/src/pages/ResultsPage.tsx`.
   - Render first-page nearby results immediately; keep blurbs enrichment non-blocking and optional.

## Optional advanced improvements
- Replace multi-category Nearby fan-out with Text Search where category semantics allow fewer calls.
- Precompute/store popular query-area results server-side (scheduled warmups).
- Use geohash/cell-level cache keys so nearby coordinates reuse results.

## Expected impact
- Parallel category fetch + page cap to 1 typically yields the largest perceived speedup (often multiple seconds saved).
- Full 3-page exhaustive results will remain slower due to mandatory token wait.

## Decision point
- Decide whether your product goal is **fast first results** or **maximum completeness**. This drives `max_pages` and concurrency defaults.