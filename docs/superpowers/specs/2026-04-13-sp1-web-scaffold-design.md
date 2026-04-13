# SP-1: Web Scaffold — Design Spec

**Date:** 2026-04-13
**Status:** Draft
**Scope:** Create the HyperPersonalWeb repository with React + FastAPI scaffold, app shell with progressive navigation, and a live dashboard proving the full stack end-to-end.
**Parent Spec:** `docs/superpowers/specs/2026-04-12-hyperpersonalweb-architecture-design.md`

## 1. Overview

SP-1 creates the HyperPersonalWeb repository at `D:\prj\HyperPersonalWeb` — a new private repo that consumes the `familyarchive` package (pip-installed from HistoryTools) and provides a web UI for managing family archives.

The scaffold includes:
- React 19 + TypeScript frontend with Vite
- FastAPI backend that imports `familyarchive`
- A working dashboard page showing real archive stats
- Progressive navigation sidebar (shows only implemented features)
- Single-command dev environment (`npm run dev`)
- OpenAPI → TypeScript type generation

### What SP-1 Does NOT Include

- File browsing or search (SP-2)
- Proposal management (SP-3)
- Pipeline execution or monitoring (SP-4)
- Entity/tag management (SP-5)
- Authentication or billing (SP-6)
- Any new `familyarchive` library code (SP-0A is complete)

## 2. Repository Structure

```
D:\prj\HyperPersonalWeb/
├── frontend/                       # React + TypeScript (Vite)
│   ├── src/
│   │   ├── routes/                 # TanStack Router file-based routes
│   │   │   ├── __root.tsx          # App shell (sidebar + header + outlet)
│   │   │   ├── index.tsx           # Redirect to /dashboard
│   │   │   ├── dashboard.tsx       # Live stats from familyarchive
│   │   │   ├── browse.tsx          # Placeholder → SP-2
│   │   │   ├── search.tsx          # Placeholder → SP-2
│   │   │   ├── proposals.tsx       # Placeholder → SP-3
│   │   │   ├── entities.tsx        # Placeholder → SP-5
│   │   │   ├── pipelines.tsx       # Placeholder → SP-4
│   │   │   └── settings.tsx        # Placeholder → future
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── sidebar.tsx     # Progressive nav sidebar
│   │   │   │   ├── header.tsx      # Top bar with breadcrumb + archive status
│   │   │   │   └── app-shell.tsx   # Composes sidebar + header + content
│   │   │   └── ui/                 # shadcn/ui components (generated)
│   │   ├── lib/
│   │   │   ├── api.ts              # Typed fetch wrapper for /api/*
│   │   │   └── types.ts            # Auto-generated from OpenAPI spec
│   │   ├── main.tsx                # React entry point
│   │   └── router.tsx              # TanStack Router + nav config
│   ├── index.html
│   ├── vite.config.ts              # API proxy: /api → localhost:8000
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── components.json             # shadcn/ui configuration
│   └── package.json                # Frontend dependencies
│
├── backend/                        # FastAPI + Python
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI app factory, CORS, lifespan
│   │   ├── config.py               # Settings from .env / deploy.toml
│   │   ├── deps.py                 # Dependency injection (db connection)
│   │   └── routers/
│   │       ├── __init__.py
│   │       └── archive.py          # /api/health, /api/stats, /api/config, /api/costs
│   ├── requirements.txt            # FastAPI, uvicorn, familyarchive
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py             # Test fixtures (mock db, test client)
│       └── test_archive.py         # Tests for archive router endpoints
│
├── shared/
│   └── generate-types.sh           # OpenAPI → TypeScript codegen script
│
├── Procfile                        # honcho: frontend + backend processes
├── package.json                    # Root: npm run dev, npm run gen-types
├── .env.example                    # ARCHIVE_PATH, DEPLOY_MODE
├── .gitignore
└── README.md
```

## 3. Frontend Architecture

### Tech Stack

| Layer | Package | Version | Purpose |
|-------|---------|---------|---------|
| Framework | react, react-dom | 19.x | UI rendering |
| Language | typescript | 5.x | Type safety |
| Build | vite | 6.x | Dev server + bundling |
| Routing | @tanstack/react-router | latest | File-based, type-safe routing |
| Server state | @tanstack/react-query | latest | API caching, deduplication, refetch |
| Styling | tailwindcss | 4.x | Utility-first CSS |
| Components | shadcn/ui (radix-ui) | latest | Accessible, customizable primitives |
| Icons | lucide-react | latest | Consistent icon set |
| Type gen | openapi-typescript | latest | OpenAPI spec → TS types |

### App Shell

The root layout (`__root.tsx`) provides:
- **Sidebar** (220px fixed width, dark theme) with progressive navigation
- **Header** (48px height) with breadcrumb and archive connection status
- **Content area** (flexible) rendering the active route via `<Outlet />`

### Progressive Navigation

Navigation items are defined in `router.tsx` with an `enabled` flag:

```typescript
interface NavItem {
  path: string;
  label: string;
  icon: LucideIcon;
  enabled: boolean;
}
```

- `enabled: true` — normal clickable link, active highlighting
- `enabled: false` — greyed out with "Soon" badge, not clickable

Future sub-projects (SP-2, SP-3, etc.) flip their routes to `enabled: true` as they're implemented. No structural changes needed.

### Dashboard Page

The dashboard (`dashboard.tsx`) displays:
- **Stat cards** (4-column grid): Total Files, Transcripts, Total Words, Est. AI Costs
- **Files by Type** breakdown: Documents, Photos, Audio, Video, Other
- **Transcript Confidence** breakdown: High, Medium, Low counts

Data is fetched via TanStack Query from `GET /api/stats`. The query refetches on window focus (standard TanStack Query behavior).

### Placeholder Pages

All non-dashboard routes render a consistent placeholder:
```
[Icon] [Page Name]
"This feature is coming in a future update."
```

These placeholders ensure routing works and provide a clear target for SP-2+ agents.

### Vite Configuration

```typescript
// vite.config.ts
export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
```

## 4. Backend Architecture

### FastAPI App

`backend/app/main.py` creates the FastAPI application:
- CORS middleware allowing `localhost:5173` (dev) and same-origin (production)
- Lifespan handler: opens `familyarchive` db connection on startup, closes on shutdown
- Mounts archive router at `/api`
- Auto-generates OpenAPI spec at `/api/openapi.json`

### Configuration

`backend/app/config.py` reads settings from environment variables (loaded from `.env`):

```python
class Settings:
    archive_path: str          # Path to archive root (where .archive.db lives)
    deploy_mode: str = "local" # "local" or "cloud"
    cors_origins: list[str] = ["http://localhost:5173"]
```

### Dependency Injection

`backend/app/deps.py` provides a `get_db` dependency that yields a database connection:

```python
from familyarchive.core.db import get_db as fa_get_db, close_db

def get_archive_db():
    settings = get_settings()
    conn = fa_get_db(settings.archive_path)
    try:
        yield conn
    finally:
        close_db(conn)
```

### API Endpoints

All endpoints are in `backend/app/routers/archive.py`:

#### `GET /api/health`
Returns application health and version info.
```json
{"status": "ok", "version": "0.1.0", "mode": "local", "archive_connected": true}
```

#### `GET /api/stats`
Returns archive statistics from `familyarchive.core.db.get_stats()`.
```json
{
  "total_files": 1247,
  "transcripts": 892,
  "total_words": 428000,
  "by_type": {"document": 623, "photo": 312, "audio": 187, "video": 48, "other": 77},
  "by_confidence": {"high": 654, "medium": 187, "low": 51},
  "avg_confidence": 0.85
}
```

#### `GET /api/config`
Returns frontend configuration (which features are enabled, archive path, deploy mode).
```json
{
  "archive_path": "F:\\Archive\\Organized",
  "mode": "local",
  "features": {
    "browse": false,
    "search": false,
    "proposals": false,
    "entities": false,
    "pipelines": false,
    "settings": false
  }
}
```

The frontend uses `features` to control which nav items are enabled. As SP-2+ ship, the backend returns `true` for implemented features.

#### `GET /api/costs`
Returns AI cost summary from `{ARCHIVE_PATH}/_costs.json` (written by `familyarchive.core.cost_tracker.CostTracker.save()`).
```json
{
  "total_cost": 4.82,
  "total_calls": 342,
  "by_step": {
    "transcribe": {"cost": 3.21, "calls": 245},
    "format": {"cost": 0.89, "calls": 52},
    "rename": {"cost": 0.72, "calls": 45}
  }
}
```

### Backend Tests

`backend/tests/test_archive.py` tests all four endpoints using FastAPI's `TestClient`:
- Health endpoint returns correct structure
- Stats endpoint returns data matching `get_stats()` output shape
- Config endpoint reflects environment settings
- Costs endpoint handles missing `_costs.json` gracefully
- All endpoints return proper error when archive path is invalid

## 5. Dev Environment

### Single Command Startup

`npm run dev` at the repo root starts both servers via `honcho` (Python process manager, like `foreman`):

**Root `package.json`:**
```json
{
  "scripts": {
    "dev": "honcho start",
    "gen-types": "bash shared/generate-types.sh",
    "frontend": "cd frontend && npm run dev",
    "backend": "cd backend && uvicorn app.main:app --reload --port 8000"
  }
}
```

**`Procfile`:**
```
frontend: cd frontend && npm run dev
backend: cd backend && uvicorn app.main:app --reload --port 8000
```

### Setup Steps (first time)

```bash
cd D:\prj\HyperPersonalWeb

# Backend
cd backend
python -m venv .venv
.venv/Scripts/activate       # Windows
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install

# Config
cp .env.example .env
# Edit .env: set ARCHIVE_PATH=F:\Archive\Organized (or your path)

# Run
cd ..
npm run dev
# Open http://localhost:5173
```

### OpenAPI → TypeScript Type Generation

`shared/generate-types.sh` fetches the OpenAPI spec from the running backend and generates TypeScript types:

```bash
#!/bin/bash
curl -s http://localhost:8000/api/openapi.json | npx openapi-typescript /dev/stdin -o frontend/src/lib/types.ts
```

Run via `npm run gen-types` after changing backend models. The generated `types.ts` provides type-safe API responses in the frontend.

## 6. Configuration

### `.env` (not committed)

```bash
# Required
ARCHIVE_PATH=F:\Archive\Organized

# Optional
DEPLOY_MODE=local              # local | cloud
FAMILYARCHIVE_CONFIG=          # path to familyarchive config.json if non-default
```

### `.env.example` (committed)

```bash
# Path to your archive root directory (where .archive.db lives)
ARCHIVE_PATH=/path/to/your/archive

# Deploy mode: local (no auth, SQLite) or cloud (auth, Postgres)
DEPLOY_MODE=local
```

## 7. Theme and Styling

- **Dark theme** by default (Slate color palette from Tailwind)
- shadcn/ui configured with "slate" base color and dark mode
- Sidebar: `bg-slate-900`, content area: `bg-slate-950`
- Cards: `bg-slate-800` with `border-slate-700`
- Text: `text-slate-50` (headings), `text-slate-400` (secondary)
- Accent: `text-blue-400` for active states, `text-green-500` for success indicators

## 8. What Future Sub-Projects Plug Into

| Sub-Project | What It Does in HyperPersonalWeb |
|-------------|----------------------------------|
| **SP-2: Browse+Search** | Implements `browse.tsx` and `search.tsx`, adds `/api/browse/*` and `/api/search` endpoints, flips `browse` and `search` features to `true` |
| **SP-3: Proposals** | Implements `proposals.tsx`, adds `/api/proposals/*` endpoints with rename/split/duplicate management |
| **SP-4: Pipelines** | Implements `pipelines.tsx`, adds `/api/pipelines/*` with SSE progress endpoints |
| **SP-5: Entities** | Implements `entities.tsx`, adds `/api/entities/*` CRUD endpoints |
| **SP-6: Auth+Billing** | Adds auth middleware, user routes, Stripe integration, switches deploy mode |

Each sub-project:
1. Adds backend endpoints in a new router file
2. Implements the placeholder route with real UI
3. Flips the feature flag to `true` in the config endpoint
4. Adds tests for new endpoints

## 9. Success Criteria

- `npm run dev` starts both Vite and FastAPI with one command
- Opening `http://localhost:5173` shows the app shell with sidebar
- Dashboard displays real stats from the user's archive
- All placeholder routes render without errors
- `GET /api/health` returns ok
- `GET /api/stats` returns real data from `.archive.db`
- Backend tests pass via `pytest backend/tests/`
- OpenAPI type generation produces valid TypeScript
- The repo is a clean, independent Git repository at `D:\prj\HyperPersonalWeb`
