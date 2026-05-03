# MoodyEat

Mood-driven restaurant discovery — pick a vibe, get a curated shortlist of places nearby.

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, Vite 6, React Router 7, Tailwind CSS 4 |
| Backend | FastAPI, Uvicorn, Pydantic v2, httpx |
| Places data | Google Places API (New) |
| AI blurbs | Anthropic Claude (optional) |

---

## Local setup

### Prerequisites

- Python 3.11+
- Node.js 20.18+

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Copy the example env file and fill in your keys:

```bash
cp .env.example .env
```

Start the server:

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

API root: `http://127.0.0.1:8000`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App: `http://localhost:5173`

---

## Environment variables

Create `backend/.env` (never commit it — it's in `.gitignore`).

### Required

| Variable | Description |
|---|---|
| `GOOGLE_PLACES_API_KEY` | Google Places API (New) key |

### Optional

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Enables AI-generated place blurbs via Claude. Blurbs are skipped when unset. |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | Claude model used for blurb generation |
| `DEFAULT_RADIUS_METERS` | `3000` | Default search radius |
| `MAX_RADIUS_METERS` | `10000` | Hard cap on search radius |
| `MAX_LIMIT` | `20` | Max places returned per request |
| `PLACES_REQUEST_TIMEOUT_SECONDS` | `6.0` | Timeout for Places API calls |
| `PLACES_PROVIDER_MAX_RETRIES` | `1` | Retry attempts on transient errors |
| `PLACES_MAX_NEARBY_PAGES` | `1` | Pages of results fetched per category |
| `PLACES_CATEGORY_CONCURRENCY` | `3` | Parallel category fetches |
| `PLACES_CACHE_TTL_SECONDS` | `600` | In-memory cache lifetime |
| `PLACES_RATE_LIMIT_PER_MINUTE` | `60` | Requests/min cap (0 = disabled) |

---

## What's next

MoodyEat is pivoting to a **quest-based experience**:

- Replace the current filter form on `/plan` with a mood-first quest selector
- Build out the `/` homepage (`MoodyEat home — coming soon`)
- Surface quest results as a narrative card sequence rather than a flat list
- Add user accounts so quests and favourite spots can be saved
