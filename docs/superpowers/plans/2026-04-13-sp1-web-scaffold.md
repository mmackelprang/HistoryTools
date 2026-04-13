# SP-1: Web Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the HyperPersonalWeb repository at `D:\prj\HyperPersonalWeb` with a working React + FastAPI scaffold, progressive navigation sidebar, and a live dashboard displaying real archive statistics.

**Architecture:** Two-process dev setup — Vite serves the React frontend on :5173 and proxies `/api/*` to FastAPI on :8000. FastAPI imports `familyarchive` (pip-installed from HistoryTools) to query the archive database. A root `Procfile` + `honcho` starts both with a single `npm run dev` command. TanStack Router provides file-based routing; TanStack Query manages server state.

**Tech Stack:** React 19, TypeScript, Vite, TanStack Router, TanStack Query, Tailwind CSS 4, shadcn/ui, Lucide icons, FastAPI, uvicorn, Pydantic, familyarchive, honcho, openapi-typescript

**New repo location:** `D:\prj\HyperPersonalWeb`

---

## File Structure

### Frontend (`frontend/`)

| File | Responsibility |
|------|---------------|
| `frontend/package.json` | Frontend dependencies and scripts |
| `frontend/index.html` | HTML entry point |
| `frontend/vite.config.ts` | Vite config with API proxy to :8000 |
| `frontend/tailwind.config.ts` | Tailwind dark theme config |
| `frontend/tsconfig.json` | TypeScript configuration |
| `frontend/components.json` | shadcn/ui configuration |
| `frontend/src/main.tsx` | React entry point, mounts app |
| `frontend/src/router.tsx` | TanStack Router config + nav items definition |
| `frontend/src/routes/__root.tsx` | App shell layout (sidebar + header + outlet) |
| `frontend/src/routes/index.tsx` | Redirect `/` → `/dashboard` |
| `frontend/src/routes/dashboard.tsx` | Live stats dashboard page |
| `frontend/src/routes/browse.tsx` | Placeholder → SP-2 |
| `frontend/src/routes/search.tsx` | Placeholder → SP-2 |
| `frontend/src/routes/proposals.tsx` | Placeholder → SP-3 |
| `frontend/src/routes/entities.tsx` | Placeholder → SP-5 |
| `frontend/src/routes/pipelines.tsx` | Placeholder → SP-4 |
| `frontend/src/routes/settings.tsx` | Placeholder → future |
| `frontend/src/components/layout/app-shell.tsx` | Composes sidebar + header + content |
| `frontend/src/components/layout/sidebar.tsx` | Progressive navigation sidebar |
| `frontend/src/components/layout/header.tsx` | Top bar with breadcrumb + archive status |
| `frontend/src/components/dashboard/stat-card.tsx` | Reusable stat card component |
| `frontend/src/lib/api.ts` | Typed fetch wrapper for /api/* calls |

### Backend (`backend/`)

| File | Responsibility |
|------|---------------|
| `backend/app/__init__.py` | Package marker |
| `backend/app/main.py` | FastAPI app factory, CORS, lifespan |
| `backend/app/config.py` | Settings from .env (archive_path, deploy_mode) |
| `backend/app/deps.py` | Dependency injection (db connection) |
| `backend/app/routers/__init__.py` | Package marker |
| `backend/app/routers/archive.py` | /api/health, /api/stats, /api/config, /api/costs |
| `backend/requirements.txt` | Python dependencies |
| `backend/tests/__init__.py` | Package marker |
| `backend/tests/conftest.py` | Test fixtures (mock archive db) |
| `backend/tests/test_archive.py` | Tests for archive endpoints |

### Root

| File | Responsibility |
|------|---------------|
| `package.json` | Root scripts: `npm run dev` starts both |
| `Procfile` | honcho process definitions |
| `.env.example` | Template for environment variables |
| `.gitignore` | Standard ignores for both stacks |
| `README.md` | Setup instructions |
| `shared/generate-types.sh` | OpenAPI → TypeScript codegen |

---

## Task 1: Initialize repository and root configuration

**Files:**
- Create: `D:\prj\HyperPersonalWeb\` (new directory + git init)
- Create: `package.json`, `Procfile`, `.env.example`, `.gitignore`, `README.md`

- [ ] **Step 1: Create directory and initialize git**

```bash
mkdir -p D:/prj/HyperPersonalWeb
cd D:/prj/HyperPersonalWeb
git init
```

- [ ] **Step 2: Create .gitignore**

Create `.gitignore`:

```gitignore
# Dependencies
node_modules/
frontend/node_modules/

# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
backend/.venv/

# Environment
.env

# Build
frontend/dist/
*.tsbuildinfo

# IDE
.idea/
.vscode/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Generated
frontend/src/lib/types.ts

# Superpowers
.superpowers/
```

- [ ] **Step 3: Create .env.example**

Create `.env.example`:

```bash
# Path to your archive root directory (where .archive.db lives)
ARCHIVE_PATH=F:\Archive\Organized

# Deploy mode: local (no auth, SQLite) or cloud (auth, Postgres)
DEPLOY_MODE=local
```

- [ ] **Step 4: Create root package.json**

Create `package.json`:

```json
{
  "name": "hyperpersonalweb",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "honcho start",
    "frontend": "cd frontend && npm run dev",
    "backend": "cd backend && ../.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000",
    "gen-types": "bash shared/generate-types.sh",
    "setup": "echo 'Run: cd backend && python -m venv .venv && .venv/Scripts/activate && pip install -r requirements.txt && cd ../frontend && npm install'"
  }
}
```

- [ ] **Step 5: Create Procfile**

Create `Procfile`:

```
frontend: cd frontend && npm run dev
backend: cd backend && ../.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 6: Create shared/generate-types.sh**

```bash
mkdir -p shared
```

Create `shared/generate-types.sh`:

```bash
#!/bin/bash
# Generate TypeScript types from FastAPI OpenAPI spec
# Requires: backend server running on port 8000
# Run: npm run gen-types

set -e

echo "Fetching OpenAPI spec from backend..."
curl -sf http://localhost:8000/api/openapi.json -o /tmp/openapi.json

echo "Generating TypeScript types..."
cd frontend
npx openapi-typescript /tmp/openapi.json -o src/lib/types.ts

echo "Done! Types written to frontend/src/lib/types.ts"
```

- [ ] **Step 7: Create README.md**

Create `README.md`:

```markdown
# HyperPersonalWeb

Web UI for [HistoryTools](https://github.com/mmackelprang/HistoryTools) — a toolkit for digitizing, organizing, transcribing, and searching family archives.

## Setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- An existing archive processed by HistoryTools (with `.archive.db`)

### Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

### Frontend
```bash
cd frontend
npm install
```

### Configuration
```bash
cp .env.example .env
# Edit .env: set ARCHIVE_PATH to your archive directory
```

### Run
```bash
npm run dev
# Open http://localhost:5173
```

This starts both the Vite dev server (port 5173) and the FastAPI backend (port 8000).
```

- [ ] **Step 8: Commit**

```bash
cd D:/prj/HyperPersonalWeb
git add -A
git commit -m "chore: initialize HyperPersonalWeb repository

- Root package.json with dev/setup scripts
- Procfile for honcho (single-command startup)
- .env.example for archive path configuration
- .gitignore for Node + Python + IDE files
- OpenAPI type generation script
- README with setup instructions"
```

---

## Task 2: Backend — FastAPI scaffold with archive endpoints

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`, `main.py`, `config.py`, `deps.py`
- Create: `backend/app/routers/__init__.py`, `archive.py`
- Create: `backend/tests/__init__.py`, `conftest.py`, `test_archive.py`

- [ ] **Step 1: Create backend directory structure**

```bash
cd D:/prj/HyperPersonalWeb
mkdir -p backend/app/routers backend/tests
```

- [ ] **Step 2: Create requirements.txt**

Create `backend/requirements.txt`:

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
python-dotenv>=1.0.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
httpx>=0.27.0
pytest>=8.0.0
familyarchive @ git+https://github.com/mmackelprang/HistoryTools.git@master
```

- [ ] **Step 3: Create package markers**

Create `backend/app/__init__.py`:

```python
```

Create `backend/app/routers/__init__.py`:

```python
```

Create `backend/tests/__init__.py`:

```python
```

- [ ] **Step 4: Create config.py**

Create `backend/app/config.py`:

```python
"""Application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settings loaded from .env file or environment variables."""

    archive_path: str = ""
    deploy_mode: str = "local"
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = {"env_file": "../.env", "env_file_encoding": "utf-8"}

    @property
    def archive_exists(self) -> bool:
        """Check if archive path is set and contains a database."""
        if not self.archive_path:
            return False
        return Path(self.archive_path).exists()


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 5: Create deps.py**

Create `backend/app/deps.py`:

```python
"""FastAPI dependency injection for shared resources."""

from typing import Generator
import sqlite3

from familyarchive.core.db import get_db, close_db

from .config import get_settings


def get_archive_db() -> Generator[sqlite3.Connection, None, None]:
    """Yield a database connection to the archive, closing it after the request."""
    settings = get_settings()
    if not settings.archive_exists:
        raise FileNotFoundError(
            f"Archive not found at: {settings.archive_path!r}. "
            "Set ARCHIVE_PATH in .env to your archive directory."
        )
    conn = get_db(settings.archive_path)
    try:
        yield conn
    finally:
        close_db(conn)
```

- [ ] **Step 6: Create archive router**

Create `backend/app/routers/archive.py`:

```python
"""Archive API endpoints — health, stats, config, costs."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from familyarchive.core.db import get_stats

from ..config import get_settings, Settings
from ..deps import get_archive_db

router = APIRouter(prefix="/api", tags=["archive"])


# ── Response Models ──────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    mode: str
    archive_connected: bool


class StatsResponse(BaseModel):
    total_files: int
    transcripts: int
    total_words: int
    by_type: dict[str, int]
    by_confidence: dict[str, int]
    avg_confidence: float


class CostStep(BaseModel):
    cost: float
    calls: int


class CostsResponse(BaseModel):
    total_cost: float
    total_calls: int
    by_step: dict[str, CostStep]


class ConfigResponse(BaseModel):
    archive_path: str
    mode: str
    features: dict[str, bool]


# ── Endpoints ────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)):
    return HealthResponse(
        status="ok",
        version="0.1.0",
        mode=settings.deploy_mode,
        archive_connected=settings.archive_exists,
    )


@router.get("/stats", response_model=StatsResponse)
def stats(db=Depends(get_archive_db)):
    raw = get_stats(db)

    by_type: dict[str, int] = {}
    by_confidence: dict[str, int] = {}
    total_files = 0
    transcripts = 0
    total_words = 0
    avg_confidence = 0.0

    if raw:
        total_files = raw.get("total_files", 0)
        transcripts = raw.get("total_transcripts", 0)
        total_words = raw.get("total_words", 0)
        by_type = raw.get("by_type", {})
        by_confidence = raw.get("by_confidence", {})
        avg_confidence = raw.get("avg_confidence", 0.0)

    return StatsResponse(
        total_files=total_files,
        transcripts=transcripts,
        total_words=total_words,
        by_type=by_type,
        by_confidence=by_confidence,
        avg_confidence=avg_confidence,
    )


@router.get("/config", response_model=ConfigResponse)
def config(settings: Settings = Depends(get_settings)):
    return ConfigResponse(
        archive_path=settings.archive_path,
        mode=settings.deploy_mode,
        features={
            "browse": False,
            "search": False,
            "proposals": False,
            "entities": False,
            "pipelines": False,
            "settings": False,
        },
    )


@router.get("/costs", response_model=CostsResponse)
def costs(settings: Settings = Depends(get_settings)):
    costs_path = Path(settings.archive_path) / "_costs.json"
    if not costs_path.exists():
        return CostsResponse(total_cost=0.0, total_calls=0, by_step={})

    try:
        data = json.loads(costs_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return CostsResponse(total_cost=0.0, total_calls=0, by_step={})

    # Aggregate from cost tracker format (list of session entries)
    total_cost = 0.0
    total_calls = 0
    by_step: dict[str, dict[str, float]] = {}

    entries = data if isinstance(data, list) else [data]
    for entry in entries:
        for record in entry.get("records", []):
            step = record.get("pipeline_step", "other")
            cost = record.get("estimated_cost", 0.0)
            total_cost += cost
            total_calls += 1
            if step not in by_step:
                by_step[step] = {"cost": 0.0, "calls": 0}
            by_step[step]["cost"] += cost
            by_step[step]["calls"] += 1

    return CostsResponse(
        total_cost=round(total_cost, 4),
        total_calls=total_calls,
        by_step={k: CostStep(**v) for k, v in by_step.items()},
    )
```

- [ ] **Step 7: Create main.py**

Create `backend/app/main.py`:

```python
"""FastAPI application for HyperPersonalWeb."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import archive


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="HyperPersonalWeb",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(archive.router)

    return app


app = create_app()
```

- [ ] **Step 8: Write backend tests**

Create `backend/tests/conftest.py`:

```python
"""Test fixtures for backend tests."""

import json
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app
from app.config import Settings, get_settings


@pytest.fixture()
def archive_dir(tmp_path):
    """Create a minimal archive with a database for testing."""
    archive = tmp_path / "archive"
    archive.mkdir()

    # Create a minimal .archive.db with schema
    db_path = archive / ".archive.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE,
            filename TEXT,
            folder TEXT,
            subfolder TEXT,
            file_type TEXT,
            size_bytes INTEGER,
            date_prefix TEXT,
            md5_hash TEXT,
            indexed_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transcripts (
            file_id INTEGER PRIMARY KEY,
            summary TEXT,
            confidence TEXT,
            method TEXT,
            word_count INTEGER,
            formatting TEXT,
            transcription_date TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transcripts_content (
            rowid INTEGER PRIMARY KEY,
            file_id INTEGER,
            path TEXT,
            body TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER
        )
    """)
    conn.execute("INSERT OR REPLACE INTO schema_version VALUES (3)")

    # Insert sample data
    conn.execute(
        "INSERT INTO files (path, filename, folder, file_type, size_bytes) "
        "VALUES (?, ?, ?, ?, ?)",
        ("Letters/letter.pdf", "letter.pdf", "Letters", "document", 1024),
    )
    conn.execute(
        "INSERT INTO files (path, filename, folder, file_type, size_bytes) "
        "VALUES (?, ?, ?, ?, ?)",
        ("Photos/photo.jpg", "photo.jpg", "Photos", "photo", 2048),
    )
    conn.execute(
        "INSERT INTO transcripts (file_id, confidence, method, word_count) "
        "VALUES (?, ?, ?, ?)",
        (1, "high", "gemini", 500),
    )
    conn.commit()
    conn.close()

    return archive


@pytest.fixture()
def test_settings(archive_dir):
    """Settings pointing to the test archive."""
    return Settings(
        archive_path=str(archive_dir),
        deploy_mode="local",
    )


@pytest.fixture()
def client(test_settings):
    """FastAPI test client with mocked settings."""
    def override_settings():
        return test_settings

    app = create_app()
    app.dependency_overrides[get_settings] = override_settings
    return TestClient(app)
```

Create `backend/tests/test_archive.py`:

```python
"""Tests for archive API endpoints."""

import json
from pathlib import Path


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert data["mode"] == "local"
    assert data["archive_connected"] is True


def test_stats(client):
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_files"] == 2
    assert data["transcripts"] == 1
    assert isinstance(data["by_type"], dict)
    assert isinstance(data["by_confidence"], dict)


def test_config(client):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "local"
    assert isinstance(data["features"], dict)
    assert data["features"]["browse"] is False
    assert data["features"]["search"] is False


def test_costs_no_file(client):
    """Costs endpoint returns zeros when _costs.json doesn't exist."""
    resp = client.get("/api/costs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_cost"] == 0.0
    assert data["total_calls"] == 0
    assert data["by_step"] == {}


def test_costs_with_data(client, archive_dir):
    """Costs endpoint aggregates from _costs.json."""
    costs_data = [{
        "records": [
            {"pipeline_step": "transcribe", "estimated_cost": 0.05},
            {"pipeline_step": "transcribe", "estimated_cost": 0.03},
            {"pipeline_step": "format", "estimated_cost": 0.01},
        ]
    }]
    costs_path = Path(archive_dir) / "_costs.json"
    costs_path.write_text(json.dumps(costs_data), encoding="utf-8")

    resp = client.get("/api/costs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_cost"] == 0.09
    assert data["total_calls"] == 3
    assert "transcribe" in data["by_step"]
    assert data["by_step"]["transcribe"]["calls"] == 2


def test_health_no_archive(client, test_settings):
    """Health reports archive_connected=false when path is invalid."""
    test_settings.archive_path = "/nonexistent/path"
    resp = client.get("/api/health")
    data = resp.json()
    assert data["archive_connected"] is False
```

- [ ] **Step 9: Set up backend virtual environment and run tests**

```bash
cd D:/prj/HyperPersonalWeb/backend
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
python -m pytest tests/ -v
```

Expected: All 6 tests PASS.

- [ ] **Step 10: Verify backend starts and responds**

```bash
cd D:/prj/HyperPersonalWeb/backend
.venv/Scripts/activate
uvicorn app.main:app --port 8000 &
# Wait a moment for startup
curl http://localhost:8000/api/health
# Kill the server
```

Expected: `{"status":"ok","version":"0.1.0","mode":"local","archive_connected":...}`

- [ ] **Step 11: Commit**

```bash
cd D:/prj/HyperPersonalWeb
git add -A
git commit -m "feat: add FastAPI backend with archive endpoints

- FastAPI app with CORS, lifespan, auto OpenAPI spec
- Settings from .env: ARCHIVE_PATH, DEPLOY_MODE
- Dependency injection for archive db connection
- Endpoints: GET /api/health, /api/stats, /api/config, /api/costs
- Pydantic response models for type safety
- Test suite with mock archive db (6 tests)
- familyarchive imported as pip dependency"
```

---

## Task 3: Frontend — React + Vite + TanStack scaffold

**Files:**
- Create: `frontend/` (Vite scaffold + configuration)

- [ ] **Step 1: Scaffold Vite project**

```bash
cd D:/prj/HyperPersonalWeb
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
```

- [ ] **Step 2: Install dependencies**

```bash
cd D:/prj/HyperPersonalWeb/frontend
npm install @tanstack/react-router @tanstack/react-query
npm install tailwindcss @tailwindcss/vite
npm install lucide-react
npm install -D @tanstack/router-devtools openapi-typescript
```

- [ ] **Step 3: Configure Vite with API proxy and Tailwind**

Replace `frontend/vite.config.ts`:

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
```

- [ ] **Step 4: Configure Tailwind**

Replace `frontend/src/index.css` with:

```css
@import "tailwindcss";
```

- [ ] **Step 5: Create API client**

Create `frontend/src/lib/api.ts`:

```typescript
/**
 * Typed API client for HyperPersonalWeb backend.
 * All requests go through Vite's proxy (/api → localhost:8000).
 */

export interface HealthResponse {
  status: string;
  version: string;
  mode: string;
  archive_connected: boolean;
}

export interface StatsResponse {
  total_files: number;
  transcripts: number;
  total_words: number;
  by_type: Record<string, number>;
  by_confidence: Record<string, number>;
  avg_confidence: number;
}

export interface CostStep {
  cost: number;
  calls: number;
}

export interface CostsResponse {
  total_cost: number;
  total_calls: number;
  by_step: Record<string, CostStep>;
}

export interface ConfigResponse {
  archive_path: string;
  mode: string;
  features: Record<string, boolean>;
}

async function fetchApi<T>(path: string): Promise<T> {
  const resp = await fetch(path);
  if (!resp.ok) {
    throw new Error(`API error: ${resp.status} ${resp.statusText}`);
  }
  return resp.json();
}

export const api = {
  health: () => fetchApi<HealthResponse>("/api/health"),
  stats: () => fetchApi<StatsResponse>("/api/stats"),
  config: () => fetchApi<ConfigResponse>("/api/config"),
  costs: () => fetchApi<CostsResponse>("/api/costs"),
};
```

- [ ] **Step 6: Create router configuration with nav items**

Create `frontend/src/router.tsx`:

```typescript
import {
  createRouter,
  createRootRoute,
  createRoute,
} from "@tanstack/react-router";
import {
  BarChart3,
  FolderOpen,
  Search,
  FileCheck,
  Users,
  Activity,
  Settings,
  type LucideIcon,
} from "lucide-react";

import { RootLayout } from "./routes/__root";
import { DashboardPage } from "./routes/dashboard";
import { PlaceholderPage } from "./routes/placeholder";

export interface NavItem {
  path: string;
  label: string;
  icon: LucideIcon;
  enabled: boolean;
}

export const navItems: NavItem[] = [
  { path: "/dashboard", label: "Dashboard", icon: BarChart3, enabled: true },
  { path: "/browse", label: "Browse", icon: FolderOpen, enabled: false },
  { path: "/search", label: "Search", icon: Search, enabled: false },
  { path: "/proposals", label: "Proposals", icon: FileCheck, enabled: false },
  { path: "/entities", label: "Entities", icon: Users, enabled: false },
  { path: "/pipelines", label: "Pipelines", icon: Activity, enabled: false },
  { path: "/settings", label: "Settings", icon: Settings, enabled: false },
];

// Route tree
const rootRoute = createRootRoute({ component: RootLayout });

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: () => {
    window.location.replace("/dashboard");
    return null;
  },
});

const dashboardRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/dashboard",
  component: DashboardPage,
});

const browseRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/browse",
  component: () => PlaceholderPage({ title: "Browse", description: "File browser coming in a future update." }),
});

const searchRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/search",
  component: () => PlaceholderPage({ title: "Search", description: "Full-text search coming in a future update." }),
});

const proposalsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/proposals",
  component: () => PlaceholderPage({ title: "Proposals", description: "Proposal management coming in a future update." }),
});

const entitiesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/entities",
  component: () => PlaceholderPage({ title: "Entities", description: "People, places, and events coming in a future update." }),
});

const pipelinesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/pipelines",
  component: () => PlaceholderPage({ title: "Pipelines", description: "Pipeline monitoring coming in a future update." }),
});

const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings",
  component: () => PlaceholderPage({ title: "Settings", description: "Settings coming in a future update." }),
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  dashboardRoute,
  browseRoute,
  searchRoute,
  proposalsRoute,
  entitiesRoute,
  pipelinesRoute,
  settingsRoute,
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
```

- [ ] **Step 7: Commit frontend scaffold**

```bash
cd D:/prj/HyperPersonalWeb
git add -A
git commit -m "feat: add React + Vite + TanStack frontend scaffold

- Vite with React 19, TypeScript, Tailwind CSS 4
- TanStack Router with file-based route definitions
- TanStack Query for server state management
- API proxy: /api/* → localhost:8000
- Typed API client (api.ts) for all backend endpoints
- Progressive nav items config with enabled flag
- Lucide icons for navigation"
```

---

## Task 4: Frontend — App shell, sidebar, and header components

**Files:**
- Create: `frontend/src/components/layout/sidebar.tsx`
- Create: `frontend/src/components/layout/header.tsx`
- Create: `frontend/src/components/layout/app-shell.tsx`
- Create: `frontend/src/routes/__root.tsx`
- Create: `frontend/src/routes/placeholder.tsx`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Create sidebar component**

Create `frontend/src/components/layout/sidebar.tsx`:

```typescript
import { Link, useRouterState } from "@tanstack/react-router";
import { navItems, type NavItem } from "../../router";

function NavLink({ item }: { item: NavItem }) {
  const router = useRouterState();
  const isActive = router.location.pathname === item.path;
  const Icon = item.icon;

  if (!item.enabled) {
    return (
      <div className="flex items-center gap-3 px-3 py-2 rounded-md text-slate-500 cursor-default">
        <Icon size={18} className="opacity-50" />
        <span className="opacity-50 text-sm">{item.label}</span>
        <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded-full border border-slate-700 text-slate-600">
          Soon
        </span>
      </div>
    );
  }

  return (
    <Link
      to={item.path}
      className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
        isActive
          ? "bg-slate-700/50 text-slate-50"
          : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
      }`}
    >
      <Icon size={18} />
      <span>{item.label}</span>
    </Link>
  );
}

export function Sidebar() {
  return (
    <aside className="w-56 bg-slate-900 border-r border-slate-800 flex flex-col h-screen fixed left-0 top-0">
      {/* Logo */}
      <div className="px-4 py-5 border-b border-slate-800">
        <div className="text-slate-50 font-bold text-base">HyperPersonal</div>
        <div className="text-slate-500 text-xs mt-0.5">Family Archive</div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 py-3 space-y-0.5">
        {navItems.map((item) => (
          <NavLink key={item.path} item={item} />
        ))}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-slate-800">
        <div className="text-slate-600 text-xs">v0.1.0 · Local Mode</div>
      </div>
    </aside>
  );
}
```

- [ ] **Step 2: Create header component**

Create `frontend/src/components/layout/header.tsx`:

```typescript
import { useRouterState } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";

export function Header() {
  const router = useRouterState();
  const pageName =
    router.location.pathname.replace("/", "").replace(/^\w/, (c) =>
      c.toUpperCase()
    ) || "Dashboard";

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 30000,
  });

  const connected = health?.archive_connected ?? false;

  return (
    <header className="h-12 border-b border-slate-800 flex items-center px-6 bg-slate-950">
      <span className="text-slate-400 text-sm">{pageName}</span>

      <div className="ml-auto flex items-center gap-2">
        <span
          className={`w-2 h-2 rounded-full ${
            connected ? "bg-green-500" : "bg-red-500"
          }`}
        />
        <span className="text-slate-400 text-xs">
          {health?.archive_connected
            ? "Archive connected"
            : "Archive not connected"}
        </span>
      </div>
    </header>
  );
}
```

- [ ] **Step 3: Create app shell**

Create `frontend/src/components/layout/app-shell.tsx`:

```typescript
import { Sidebar } from "./sidebar";
import { Header } from "./header";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-50">
      <Sidebar />
      <div className="ml-56 flex flex-col min-h-screen">
        <Header />
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create root layout**

Create `frontend/src/routes/__root.tsx`:

```typescript
import { Outlet } from "@tanstack/react-router";
import { AppShell } from "../components/layout/app-shell";

export function RootLayout() {
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}
```

- [ ] **Step 5: Create placeholder page component**

Create `frontend/src/routes/placeholder.tsx`:

```typescript
interface PlaceholderProps {
  title: string;
  description: string;
}

export function PlaceholderPage({ title, description }: PlaceholderProps) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
      <h1 className="text-2xl font-bold text-slate-300 mb-2">{title}</h1>
      <p className="text-slate-500">{description}</p>
    </div>
  );
}
```

- [ ] **Step 6: Update main.tsx entry point**

Replace `frontend/src/main.tsx`:

```typescript
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "@tanstack/react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { router } from "./router";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: true,
      retry: 1,
      staleTime: 30_000,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>
);
```

- [ ] **Step 7: Clean up default Vite files**

Delete these default files that Vite created:
```bash
cd D:/prj/HyperPersonalWeb/frontend
rm -f src/App.tsx src/App.css src/assets/react.svg
```

- [ ] **Step 8: Commit**

```bash
cd D:/prj/HyperPersonalWeb
git add -A
git commit -m "feat: add app shell with sidebar, header, and placeholder routes

- Sidebar with progressive nav (enabled items clickable, disabled greyed)
- Header with breadcrumb and archive connection indicator
- AppShell composing sidebar + header + content outlet
- Root layout wrapping all routes in AppShell
- Placeholder component for unimplemented routes
- QueryClient configured with refetch-on-focus and 30s stale time
- Dark slate theme throughout"
```

---

## Task 5: Frontend — Dashboard page with live stats

**Files:**
- Create: `frontend/src/components/dashboard/stat-card.tsx`
- Create: `frontend/src/routes/dashboard.tsx`

- [ ] **Step 1: Create stat card component**

Create `frontend/src/components/dashboard/stat-card.tsx`:

```typescript
interface StatCardProps {
  label: string;
  value: string | number;
  subtitle?: string;
}

export function StatCard({ label, value, subtitle }: StatCardProps) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
      <div className="text-slate-400 text-xs uppercase tracking-wider">
        {label}
      </div>
      <div className="text-slate-50 text-2xl font-bold mt-1">
        {typeof value === "number" ? value.toLocaleString() : value}
      </div>
      {subtitle && (
        <div className="text-slate-500 text-xs mt-1">{subtitle}</div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create dashboard page**

Create `frontend/src/routes/dashboard.tsx`:

```typescript
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { StatCard } from "../components/dashboard/stat-card";

function formatCost(cost: number): string {
  return `$${cost.toFixed(2)}`;
}

function formatWords(words: number): string {
  if (words >= 1_000_000) return `${(words / 1_000_000).toFixed(1)}M`;
  if (words >= 1_000) return `${(words / 1_000).toFixed(0)}K`;
  return words.toString();
}

export function DashboardPage() {
  const {
    data: stats,
    isLoading: statsLoading,
    error: statsError,
  } = useQuery({
    queryKey: ["stats"],
    queryFn: api.stats,
  });

  const { data: costs, isLoading: costsLoading } = useQuery({
    queryKey: ["costs"],
    queryFn: api.costs,
  });

  if (statsError) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh]">
        <h1 className="text-xl font-bold text-red-400 mb-2">
          Cannot connect to archive
        </h1>
        <p className="text-slate-400 text-sm">
          Check that ARCHIVE_PATH in .env points to a valid archive directory.
        </p>
      </div>
    );
  }

  if (statsLoading || costsLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-slate-400">Loading archive data...</div>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-xl font-bold text-slate-50 mb-6">
        Archive Overview
      </h1>

      {/* Top stat cards */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <StatCard label="Total Files" value={stats?.total_files ?? 0} />
        <StatCard label="Transcripts" value={stats?.transcripts ?? 0} />
        <StatCard
          label="Total Words"
          value={formatWords(stats?.total_words ?? 0)}
        />
        <StatCard
          label="Est. AI Costs"
          value={formatCost(costs?.total_cost ?? 0)}
          subtitle={`${costs?.total_calls ?? 0} API calls`}
        />
      </div>

      {/* Detail cards */}
      <div className="grid grid-cols-2 gap-4">
        {/* Files by type */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-slate-50 mb-3">
            Files by Type
          </h2>
          <div className="flex gap-6 flex-wrap">
            {Object.entries(stats?.by_type ?? {}).map(([type, count]) => (
              <div key={type}>
                <div className="text-slate-400 text-xs capitalize">{type}</div>
                <div className="text-slate-50 font-bold">
                  {count.toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Transcript confidence */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-slate-50 mb-3">
            Transcript Confidence
          </h2>
          <div className="flex gap-6 flex-wrap">
            {Object.entries(stats?.by_confidence ?? {}).map(
              ([level, count]) => (
                <div key={level}>
                  <div
                    className={`text-xs capitalize ${
                      level === "high"
                        ? "text-green-400"
                        : level === "medium"
                          ? "text-yellow-400"
                          : "text-red-400"
                    }`}
                  >
                    {level}
                  </div>
                  <div className="text-slate-50 font-bold">
                    {count.toLocaleString()}
                  </div>
                </div>
              )
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
cd D:/prj/HyperPersonalWeb
git add -A
git commit -m "feat: add live dashboard with archive stats

- StatCard reusable component for metric display
- Dashboard fetches real data from /api/stats and /api/costs
- Top row: total files, transcripts, total words, est. AI costs
- Detail cards: files by type breakdown, transcript confidence
- Loading state while fetching data
- Error state when archive is not connected
- Numbers formatted with locale separators (1,247) and abbreviations (428K)"
```

---

## Task 6: Install honcho and verify end-to-end

**Files:**
- No new files — integration verification

- [ ] **Step 1: Install honcho**

```bash
cd D:/prj/HyperPersonalWeb/backend
.venv/Scripts/activate
pip install honcho
```

- [ ] **Step 2: Create .env with real archive path**

```bash
cd D:/prj/HyperPersonalWeb
cp .env.example .env
```

Edit `.env` to set `ARCHIVE_PATH` to a real archive (e.g., `F:\Archive\Organized`).

- [ ] **Step 3: Start both servers with npm run dev**

```bash
cd D:/prj/HyperPersonalWeb
npm run dev
```

Expected: Both `frontend` and `backend` processes start. Vite on :5173, FastAPI on :8000.

- [ ] **Step 4: Verify in browser**

Open `http://localhost:5173` and verify:
- App shell renders with sidebar and header
- Dashboard shows real stats from your archive
- Sidebar shows "Dashboard" as active, other items greyed with "Soon"
- Header shows green dot with "Archive connected"
- Stat cards show real numbers (not zeros)

- [ ] **Step 5: Verify API directly**

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/stats
curl http://localhost:8000/api/config
curl http://localhost:8000/api/costs
```

All should return valid JSON responses.

- [ ] **Step 6: Run backend tests**

```bash
cd D:/prj/HyperPersonalWeb/backend
.venv/Scripts/activate
python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 7: Final commit**

```bash
cd D:/prj/HyperPersonalWeb
git add -A
git commit -m "chore: verify end-to-end stack — both servers, live dashboard, tests pass"
```

Only commit if there were fixes needed. If everything worked clean, skip.

---

## Task 7: Create GitHub repo and push

**Files:**
- No new files — git remote setup

- [ ] **Step 1: Create private GitHub repo**

```bash
cd D:/prj/HyperPersonalWeb
gh repo create mmackelprang/HyperPersonalWeb --private --source=. --push
```

- [ ] **Step 2: Verify repo on GitHub**

```bash
gh repo view mmackelprang/HyperPersonalWeb --web
```

Expected: Private repo with all commits visible.

---

## Summary

| Task | What it does | Key files |
|------|-------------|-----------|
| 1 | Repo init + root config | package.json, Procfile, .env.example, .gitignore, README |
| 2 | FastAPI backend + tests | backend/app/*.py, backend/tests/*.py |
| 3 | React + Vite + TanStack scaffold | frontend/src/router.tsx, lib/api.ts, vite.config.ts |
| 4 | App shell + sidebar + header | components/layout/*.tsx, routes/__root.tsx |
| 5 | Dashboard with live stats | routes/dashboard.tsx, components/dashboard/stat-card.tsx |
| 6 | End-to-end verification | honcho startup, browser check, API check |
| 7 | GitHub repo creation | git remote, gh repo create |

After SP-1 is complete:
- `npm run dev` starts both servers with one command
- `http://localhost:5173` shows the app shell with live dashboard
- Dashboard displays real archive stats from familyarchive
- All placeholder routes are defined and render
- Backend tests pass
- Repo is live on GitHub as `mmackelprang/HyperPersonalWeb`
