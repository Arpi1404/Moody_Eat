# Travel Planner – React + FastAPI starter

This is a minimal starter for a Travel Planner style app with:

- **Backend**: FastAPI
- **Frontend**: React (loaded from CDNs, no build step)

The current behavior is simple: the frontend shows a **pretty card** saying **Hello name**, where the `name` value is fetched from the FastAPI backend.

---

## Backend (FastAPI)

**Location**: `backend/`

### Install dependencies

From the project root:

```bash
cd backend
pip install -r requirements.txt
```

### Run the backend

```bash
cd backend
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

The API will be available at `http://127.0.0.1:8000`.

- Test in a browser or with curl:

```bash
curl http://127.0.0.1:8000/name
```

You should see:

```json
{"name": "Traveler"}
```

---

## Frontend (React)

**Location**: `frontend/index.html`

The frontend is a single HTML file that:

- Loads **React 18** and **ReactDOM** from CDNs.
- Renders a modern-looking card.
- Calls `http://127.0.0.1:8000/name` to get the `name`.

### Run the frontend

You can open the frontend directly or via a simple static server.

#### Option 1 – Open directly

1. Start the FastAPI backend (see above).
2. Open `frontend/index.html` in your browser (double-click or `Ctrl+O` → select file).

#### Option 2 – Simple static server (recommended)

From the project root:

```bash
cd frontend
python -m http.server 5500

```

Then open:

- `http://127.0.0.1:5500/index.html`

The card will display:

- **Hello Traveler** (with `Traveler` coming from the backend).

---

## Next steps

- Replace the `/name` endpoint to return real user data.
- Extend the frontend to show trips, destinations, and itineraries.
- Convert the frontend into a full React project (Vite, CRA, etc.) if you want a full build toolchain.

