# HyperPersonalWeb — Architecture Design Spec

**Date:** 2026-04-12
**Status:** Draft
**Scope:** Overall system architecture, tech stack, sub-project decomposition, and build sequencing for the HistoryTools web UI

## 1. Overview

HyperPersonalWeb is a web application that provides a modern UI for the HistoryTools family archive toolkit. It lives in a separate private repository (`mmackelprang/HyperPersonalWeb`) and consumes the HistoryTools core library (`familyarchive`) as a pip-installable dependency.

The system is designed as **local-first with cloud-ready abstractions** — it runs on a user's machine with no auth or billing, but the same codebase can be deployed as a multi-tenant cloud service (`historytools.io`) by changing configuration.

### Goals

- Replace CLI workflows with a visual, interactive experience
- Provide real-time pipeline monitoring (SSE for live progress)
- Add rich metadata management (people, locations, events, tags)
- Enable proposal review through visual UIs instead of JSON editing
- Architect for pluggable external service connectors (Google Photos, FamilySearch, etc.)
- Build toward a subscription SaaS model with managed AI gateway

### Non-Goals (for initial release)

- Mobile-native app (responsive web is fine)
- Offline-first/PWA (local mode assumes the server is running)
- Multi-user collaboration on a single archive (single-tenant locally)
- Public API for third-party integrations

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Browser (React SPA)                   │
│  React 19 + TypeScript + Vite + TanStack + shadcn/ui    │
│  Dashboard │ Browse │ Search │ Proposals │ Entities      │
│  Pipeline Monitor (SSE) │ Settings │ Billing             │
└──────────────────────┬──────────────────────────────────┘
                       │ JSON API + SSE
┌──────────────────────▼──────────────────────────────────┐
│              FastAPI Backend (HyperPersonalWeb)          │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │  API Routes  │  │ Web Services │  │  Config Layer  │ │
│  │ Browse/Search│  │ Auth(pluggable│  │ Deploy mode    │ │
│  │ Proposals    │  │ Billing/Stripe│  │ Storage backend│ │
│  │ Pipelines    │  │ Job Queue    │  │ Auth provider  │ │
│  │ Entities     │  │ Usage Tracking│  │ AI gateway     │ │
│  │ SSE streams  │  │ Spending Caps│  │ Feature flags  │ │
│  └──────┬──────┘  └──────┬───────┘  └────────────────┘ │
│         │                │                               │
│  ┌──────▼──────┐  ┌──────▼───────┐                      │
│  │   web.db    │  │  Connector   │                      │
│  │ Users/Auth  │  │   Manager    │                      │
│  │ Billing     │  │ (registry of │                      │
│  │ Sessions    │  │  external    │                      │
│  │ UI Prefs    │  │  sources)    │                      │
│  └─────────────┘  └──────────────┘                      │
└──────────────────────┬──────────────────────────────────┘
                       │ Python imports
┌──────────────────────▼──────────────────────────────────┐
│           familyarchive (pip package from GitHub)        │
│                                                         │
│  Existing:                    New (Phase 0):            │
│  • config — settings/taxonomy • entities — people/places│
│  • db — SQLite + FTS5        • tags — user labels       │
│  • ai_client — multi-vendor  • storage — local/S3      │
│  • cost_tracker — usage      • pipelines — orchestration│
│  • extract — Office docs     • connectors — base class  │
│  • quality_check — OCR       • progress — callback proto│
│  • rate_limiter — throttle                              │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │              .archive.db (SQLite)                │    │
│  │  files │ transcripts │ FTS5 │ provenance        │    │
│  │  fingerprints │ batches │ quarantine             │    │
│  │  NEW: entities │ tags │ entity_files │ sources   │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### Two-Database Split

| Database | Location | Contents | Scales via |
|----------|----------|----------|------------|
| `.archive.db` | Archive root (per-archive) | Files, transcripts, FTS5, provenance, fingerprints, batches, entities, tags | One per archive; stays SQLite |
| `web.db` | HyperPersonalWeb app directory | User accounts, sessions, billing, usage records, UI preferences, connector credentials | SQLite locally; Postgres for cloud multi-tenant |

### Deploy Modes

Controlled by a single config file (`deploy.toml` or environment variables):

**Local mode (default):**
- No authentication (single user, localhost only)
- No billing (user provides their own API keys)
- Storage: local filesystem
- AI: direct API calls with user keys
- Database: SQLite for both web.db and archive.db

**Cloud mode:**
- Authentication: Google OAuth, Facebook OAuth, email/password
- Billing: Stripe hybrid (subscription + metered overage)
- Storage: S3-compatible (AWS S3, Cloudflare R2, MinIO)
- AI: managed gateway (proxied through our backend)
- Database: Postgres for web.db, SQLite for archive.db (per-tenant)

## 3. Tech Stack

### Frontend (HyperPersonalWeb)

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Framework | React 19 + TypeScript | Best AI coding assistance, largest component ecosystem, no interactivity ceiling |
| Build | Vite | Fast HMR, simple config, ESM-native |
| Routing | TanStack Router | File-based, type-safe, code splitting |
| Server state | TanStack Query | Caching, deduplication, background refetch |
| Styling | Tailwind CSS | Utility-first, consistent, small bundle |
| Components | shadcn/ui (Radix primitives) | Accessible, customizable, copy-paste ownership |
| Tables | TanStack Table | Headless, sortable, filterable, virtual scroll |
| Charts | Recharts or Chart.js | Cost dashboards, usage graphs |
| SSE | Native EventSource + TanStack Query | Pipeline progress streaming |
| Type generation | openapi-typescript | FastAPI OpenAPI spec → TS types, zero drift |

### Backend (HyperPersonalWeb)

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Framework | FastAPI | Async, auto OpenAPI spec, Pydantic validation |
| Auth | fastapi-users + social auth providers | Pluggable, supports OAuth2 + password |
| Billing | stripe-python | Official SDK, webhook handling |
| Task queue | (Phase 2) arq or Celery | Background pipeline jobs |
| SSE | sse-starlette | Server-sent events for progress |
| ORM | SQLAlchemy 2.0 (web.db only) | Type-safe queries for user/billing tables |

### Core Library (HistoryTools → familyarchive)

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Package | pip-installable from GitHub | Clean dependency boundary, semver tags |
| Database | Raw SQLite (existing) | Direct control, FTS5, WAL mode |
| AI | Existing ai_client.py | Multi-vendor abstraction already built |
| New: Progress | Callback protocol | `on_progress(event: ProgressEvent)` |
| New: Storage | Abstract interface | Local filesystem default, S3 adapter for cloud |
| New: Connectors | Base class + registry | Pluggable external service integration |

### Dev Experience

- Vite dev server (port 5173) proxies API calls to FastAPI (port 8000)
- FastAPI hot-reloads with uvicorn `--reload`
- OpenAPI spec auto-generates TypeScript types on change
- Single `make dev` or `npm run dev` starts both servers

## 4. Progress Callback System

The current pipeline runs stages as subprocesses with `print()` output. For the web UI to show live progress via SSE, the core library needs a callback protocol.

### Progress Event Protocol

```python
@dataclass
class ProgressEvent:
    stage: str              # "copy", "transcribe", "format", "rename", etc.
    stage_number: int       # 1-based stage index
    total_stages: int       # Total stages in pipeline
    status: str             # "started", "processing", "completed", "error", "skipped"
    file_path: str | None   # Current file being processed
    current: int | None     # Current item number (1-based)
    total: int | None       # Total items in this stage
    message: str | None     # Human-readable status message
    detail: dict | None     # Stage-specific metadata
```

### Refactoring Required

Each pipeline script's `main()` function must be converted to a library function that accepts an `on_progress` callback:

```python
# Before (subprocess):
def run_script(script_name, extra_args=None):
    result = subprocess.run([sys.executable, str(script_path)])
    return result.returncode == 0

# After (library function):
def transcribe_pdfs(config, on_progress=None):
    for i, pdf in enumerate(pdfs):
        if on_progress:
            on_progress(ProgressEvent(
                stage="transcribe", status="processing",
                file_path=str(pdf), current=i+1, total=len(pdfs)
            ))
        # ... do transcription ...
```

The CLI (`cli.py`) provides a terminal-printing callback. The web backend provides an SSE-emitting callback. Both consume the same library functions.

## 5. Connector Architecture

### Base Class

All external service connectors implement `familyarchive.connectors.Connector`:

```python
class Connector(ABC):
    name: str                   # "google_photos", "familysearch"
    display_name: str           # "Google Photos"
    auth_type: AuthType         # OAUTH2, API_KEY, BROWSER_SESSION, FILE_IMPORT
    data_types: list[DataType]  # PHOTOS, MESSAGES, PEOPLE, DOCUMENTS, ARTIFACTS

    # Auth lifecycle
    def get_auth_url() -> str
    def handle_callback(code) -> Credentials
    def refresh_token(creds) -> Credentials
    def test_connection(creds) -> bool

    # Browse & discover
    def list_collections(creds) -> list[Collection]
    def list_items(creds, collection_id, page_token=None) -> Page[Item]
    def get_item_preview(creds, item_id) -> Preview

    # Import
    def download_items(creds, item_ids, on_progress) -> list[DownloadedItem]

    # Map to archive
    def map_to_entities(item) -> list[Entity]
    def map_to_archive_file(item) -> IngestFile
```

### Connector Registry

Connectors register via decorator (same pattern as `extract.py`):

```python
@register_connector
class GooglePhotosConnector(Connector):
    name = "google_photos"
    ...
```

The web UI queries the registry to show available connectors in the "Add Source" interface. Adding a new connector is one Python file — no UI changes needed.

### Credential Storage

- **Local mode:** OS keyring (via `keyring` library) or encrypted local file
- **Cloud mode:** Secret manager (AWS Secrets Manager, Vault, etc.)
- Interface: `CredentialStore.save(connector_name, user_id, creds)` / `.load()` / `.delete()`
- Connection metadata (connector_name, status, last_sync) lives in `web.db`; actual secrets (tokens, keys) live in the secure credential store, never in the database

### Planned Connectors (Phase 3)

| Connector | Auth | Data Types | Notes |
|-----------|------|------------|-------|
| Contacts/vCard | FILE_IMPORT | People | Parse .vcf + CSV. Simplest — build first. |
| GEDCOM | FILE_IMPORT | People, Events, Locations | Generic genealogy format. Covers Ancestry exports. |
| Google Photos | OAUTH2 | Photos, People, Locations | API is read-only. Face labels for people entities. |
| FamilySearch | OAUTH2 | People, Events, Locations, Documents | Free API. Richest genealogical data. |
| Facebook | FILE_IMPORT | Messages, Photos, People | Data download parsing (JSON). Graph API too restricted. |

### Future Connectors

iCloud Photos, WhatsApp Export, Instagram, Google Drive, Dropbox, FindAGrave, Newspapers.com

## 6. Entity Model

New tables in `.archive.db` (core library):

```sql
-- People (from contacts, genealogy, AI extraction)
CREATE TABLE entities_people (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    alternate_names TEXT,        -- JSON array
    birth_date TEXT,
    death_date TEXT,
    notes TEXT,
    source_connector TEXT,       -- which connector created this
    external_id TEXT,            -- ID in source system
    created_at TEXT,
    updated_at TEXT
);

-- Locations
CREATE TABLE entities_locations (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT,
    city TEXT,
    state TEXT,
    country TEXT,
    latitude REAL,
    longitude REAL,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

-- Events (named events spanning dates)
CREATE TABLE entities_events (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,          -- "1996 Family Reunion"
    event_type TEXT,             -- reunion, wedding, funeral, etc.
    start_date TEXT,
    end_date TEXT,
    location_id INTEGER REFERENCES entities_locations(id),
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

-- Timeframes (date range labels — "7th Grade", "Mission years")
CREATE TABLE entities_timeframes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    person_id INTEGER REFERENCES entities_people(id),  -- optional: whose timeframe
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

-- Tags (user-defined labels)
CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,   -- "Family Reunion", "Scout Camp", "Middle School"
    color TEXT,                  -- optional display color
    created_at TEXT
);

-- Junction: link entities/tags to files (many-to-many)
CREATE TABLE entity_files (
    id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,   -- "person", "location", "event", "timeframe", "tag"
    entity_id INTEGER NOT NULL,
    file_id INTEGER NOT NULL REFERENCES files(id),
    confidence TEXT,             -- "manual", "ai_suggested", "connector_imported"
    created_at TEXT,
    UNIQUE(entity_type, entity_id, file_id)
);

-- Relationships between people
CREATE TABLE people_relationships (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES entities_people(id),
    related_person_id INTEGER NOT NULL REFERENCES entities_people(id),
    relationship_type TEXT NOT NULL,  -- parent, child, spouse, sibling
    created_at TEXT,
    UNIQUE(person_id, related_person_id, relationship_type)
);

-- Connected external sources
CREATE TABLE connected_sources (
    id INTEGER PRIMARY KEY,
    connector_name TEXT NOT NULL,
    display_name TEXT,
    status TEXT DEFAULT 'active',    -- active, expired, disconnected
    last_sync_at TEXT,
    item_count INTEGER DEFAULT 0,
    created_at TEXT
);
```

## 7. Billing Model

### Stripe Hybrid Pricing

- **Free tier:** Local mode only, user provides own API keys, no limits
- **Starter tier ($X/month):** Includes N pages/month of AI processing, cloud storage quota
- **Pro tier ($Y/month):** Higher limits, priority processing, all connectors
- **Overage:** $0.0X/page beyond tier limit (metered billing via Stripe)

### Spending Caps

Users can set a hard monthly spending cap. The system tracks usage against the cap and automatically pauses pipeline jobs when the cap is reached.

```python
class SpendingCap:
    monthly_limit: Decimal       # User-set limit
    current_usage: Decimal       # Tracked from cost_tracker
    auto_pause: bool             # Whether to pause at limit (user toggle)
    notify_at: list[int]         # Percentage thresholds for warnings (e.g., [50, 80, 95])
```

When `current_usage >= monthly_limit` and `auto_pause` is True:
1. All in-progress pipeline jobs complete their current file (don't corrupt mid-process)
2. No new pipeline stages start
3. User receives notification with option to raise cap or wait for reset
4. Cap resets on billing cycle date

## 8. Sub-Project Decomposition

### Phase 0 — Preparation (HistoryTools repo)

| Sub-Project | Scope | Depends On | Parallelizable |
|-------------|-------|------------|----------------|
| **SP-0A: Package Foundation** | `scripts/` → `familyarchive/` rename, pip-installable package, progress callbacks, pipeline orchestration API, storage abstraction, entity schema, connector base class, connector registry | Nothing | No — must complete first |
| **SP-0B: Video Transcription** | ffmpeg audio extraction, feed into AssemblyAI pipeline, video metadata, thumbnails, taxonomy updates | SP-0A | Yes — parallel with 0C, 0D |
| **SP-0C: Email Import** | .eml + .mbox parsing, attachment extraction, thread reconstruction, auto-entity extraction from headers | SP-0A | Yes — parallel with 0B, 0D |
| **SP-0D: Photo AI Descriptions** | AI vision descriptions, date inference from content, scene/setting description, auto-tag suggestions, batch mode | SP-0A | Yes — parallel with 0B, 0C |

### Phase 1 — Web UI MVP (HyperPersonalWeb repo)

| Sub-Project | Scope | Depends On | Parallelizable |
|-------------|-------|------------|----------------|
| **SP-1: Web Scaffold** | Create repo, React + Vite + TS setup, FastAPI scaffold, Tailwind + shadcn/ui, TanStack Router + Query, OpenAPI → TS types, dev environment, CI/CD | SP-0A | Can overlap with SP-0B/0C/0D |
| **SP-2: Browse + Search** | File browser tree, FTS search with filters, transcript viewer, photo/video thumbnails, stats dashboard, cost display, Sources page shell | SP-1 | Yes — parallel with SP-3 |
| **SP-3: Proposal Management** | Rename proposal UI, split proposal preview, duplicate side-by-side compare, ingest plan review, bulk approve/reject, proposal history | SP-1 | Yes — parallel with SP-2 |

### Phase 2 — Full Features (both repos)

| Sub-Project | Scope | Depends On | Parallelizable |
|-------------|-------|------------|----------------|
| **SP-4: Ingest + Pipelines** | Folder/file picker, upload (cloud), SSE progress, job monitoring, pause/resume/retry, background notifications | SP-2 + SP-3 | No — needs UI patterns from MVP |
| **SP-5: Entities + Tags** | People/location/event/timeframe CRUD, tag management, entity ↔ file linking, AI-assisted extraction, relationship editor | SP-2 | Can parallel with SP-4 |
| **SP-6: Auth + Billing** | Google/Facebook OAuth, email/password, Stripe hybrid billing, spending caps, usage dashboard, admin panel | SP-1 | Can start early, deploy last |

### Phase 3 — Connectors (both repos)

| Sub-Project | Scope | Depends On | Parallelizable |
|-------------|-------|------------|----------------|
| **SP-7: Connectors** | Contacts/vCard, GEDCOM, Google Photos, FamilySearch, Facebook data import | SP-5 (entities) + SP-4 (pipeline UI) | Each connector is independent |

### Critical Path

```
SP-0A → SP-0B ∥ SP-0C ∥ SP-0D
SP-0A → SP-1 → SP-2 ∥ SP-3 → SP-4 → SP-7
                              → SP-5 → SP-7
                SP-1 → SP-6
```

### Agent Team Mapping

| Agent | Primary Responsibility | Sub-Projects |
|-------|----------------------|--------------|
| **Architect** | Overall design, interface contracts, code review | All — oversight |
| **Backend** | FastAPI API, core library changes | SP-0A, SP-1 (backend), SP-4, SP-6 |
| **Frontend** | React UI, components, UX | SP-1 (frontend), SP-2, SP-3, SP-5 |
| **Integration** | Pipeline wiring, connectors, core library features | SP-0B, SP-0C, SP-0D, SP-7 |
| **Documentation** | Specs, API docs, user guides, pre-push verification | All — docs for each SP |

## 9. Interface Contract: familyarchive ↔ HyperPersonalWeb

The web backend imports `familyarchive` and calls library functions directly. Key interfaces:

### Config & Setup
```python
from familyarchive.config import load_config, load_taxonomy
from familyarchive.db import get_db, close_db
```

### Search & Browse
```python
from familyarchive.db import search, get_stats, index_file, reindex_all
```

### Pipeline Execution
```python
from familyarchive.pipelines import run_ingest, run_transcribe, run_format
# All accept on_progress callback for SSE
```

### Entities
```python
from familyarchive.entities import create_person, link_entity_to_file, search_entities
```

### Connectors
```python
from familyarchive.connectors import get_connector, list_connectors
```

### Cost Tracking
```python
from familyarchive.cost_tracker import CostTracker
```

## 10. Decisions Log

| Decision | Choice | Rationale | Alternatives Considered |
|----------|--------|-----------|------------------------|
| Repo structure | Separate repos, pip dependency | Clean boundary, independent versioning | Monorepo, git submodule |
| Frontend framework | React + TypeScript | Best AI assistance, largest ecosystem, no interactivity ceiling | htmx (ceiling too low), Svelte (smaller ecosystem), Vue (no winning axis) |
| Deploy model | Local-first → cloud hybrid | Ship useful immediately, cloud when ready | Cloud-only (too much infrastructure upfront), local-only (no revenue path) |
| Entity storage | Core library (archive.db) | Entities are archive metadata, useful for CLI search too | Separate web DB (two databases to query), mixed (complexity) |
| AI gateway | User keys locally, managed gateway in cloud | Zero infrastructure for local, revenue path for cloud | User keys always (no revenue), managed always (complex for local) |
| Billing | Stripe hybrid + spending caps | Industry standard, subscription + metered, auto-pause builds trust | Lemon Squeezy (less control), Paddle (less dev experience) |
| Progress | Callback protocol + SSE | Clean library/UI separation, framework-agnostic | WebSockets (more complex), polling (worse UX) |
| Connector pattern | Base class + registry | One file per connector, auto-discovered, no UI changes needed | Config-driven (less flexible), plugin system (over-engineered) |

## 11. Reference-Only Architecture

The HistoryTools project is moving toward a **reference-only default** (see `project_reference_architecture.md`). This means:

- **Default mode:** Source files stay in place, never copied. Transcripts, metadata, and provenance are stored in SQLite. Source locations are tracked in a registry.
- **Optional `--copy` mode:** Copies originals into an organized folder structure (current behavior).

This affects the web UI in several ways:

- **File browser:** Must resolve file references on-the-fly. In reference mode, clicking a file triggers extraction from the source location (which may be a local path, ZIP, or cloud storage).
- **Storage abstraction:** Must support both "file lives at original path" and "file was copied to archive structure" transparently.
- **Source registry:** The web UI needs a "Sources" view showing registered source locations with reachability status (is the external drive plugged in?).
- **Cloud mode:** Reference-only becomes "reference to S3 object" rather than "reference to local path."

The storage abstraction in SP-0A must accommodate both reference and copy modes. The file browser in SP-2 must handle both transparently.

## 12. Resolved Questions

1. **Archive isolation in cloud mode:** Migrate archive.db to Postgres for multi-tenancy in cloud mode. Local mode stays SQLite. Build local-first, migrate to Postgres as a later phase before cloud launch.
2. **File storage in cloud mode:** Store transcripts in S3 by default. Originals are optionally pushed to S3 via explicit user action or UI configuration. This keeps cloud storage costs low while preserving the reference-only model.
3. **Connector rate limits:** No built-in per-connector rate limiting. Instead, handle 429 responses with incremental backoff and monitor API response headers that signal impending throttling (e.g., `X-RateLimit-Remaining`). This is simpler and adapts to each API's actual behavior.
4. **GEDCOM complexity:** In-memory parser is sufficient for initial use. If a file exceeds a size threshold, prompt the user to break it down by family line before importing.
5. **Video file sizes:** Local files only — no streaming upload/download needed. Additionally, add **video segmentation detection** as a feature: old tape-style videos often contain 20+ "sessions" on a single tape. Detect session boundaries (scene changes, blank segments, timestamp gaps) similarly to how we detect multiple documents in compilation PDFs. This maps to the existing split proposal pattern.
6. **Source reachability in reference mode:** Graceful degradation — when a source is unreachable (drive unplugged, network offline), display cached metadata (file info, transcript, entities, tags) and clearly indicate the source is currently unavailable. No error state, just reduced functionality.

## 13. Open-Source vs Paid Feature Boundary

A clear separation between the free open-source CLI and the paid web service is essential for community trust and a viable business model.

### Open Source (HistoryTools / `familyarchive` package) — Always Free

Everything that runs locally with the user's own resources:

- **All CLI commands** — ingest, transcribe, format, rename, split, duplicates, search, etc.
- **Core library** — config, db, ai_client, cost_tracker, extract, quality_check, rate_limiter
- **Entity schema and local entity management** — people, locations, events, tags (CLI-based)
- **All file format support** — PDF, Office, audio, video, email, photos
- **Progress callback protocol** — library functions emit events (how they're consumed is up to the caller)
- **Connector base class and FILE_IMPORT connectors** — vCard, GEDCOM (file-based imports that don't need a running service)
- **SQLite database and FTS5 search** — local search is free forever
- **Storage abstraction interface** — the interface is open-source; the S3 adapter is open-source; the S3 infrastructure is not

**Principle:** If it processes your files on your machine with your API keys, it's free.

### Paid Web Service (HyperPersonalWeb / historytools.io)

Features that require infrastructure, hosted services, or multi-user coordination:

- **Web UI** — the React frontend and FastAPI backend (the code is in a private repo)
- **Managed AI gateway** — we proxy AI calls, user doesn't need their own API keys
- **Cloud storage** — S3-hosted transcripts and optional original file storage
- **OAuth connectors** — Google Photos, FamilySearch, Facebook (require our OAuth app credentials and callback infrastructure)
- **Multi-tenant hosting** — Postgres, user isolation, account management
- **Sharing and permissions** — cross-user archive sharing (see Section 14)
- **Background job processing** — cloud-hosted pipeline workers
- **Usage dashboards and billing** — Stripe integration, spending caps

**Principle:** If it requires us to run infrastructure or hold credentials on your behalf, it's paid.

### Gray Area: Local Web UI

The web UI runs locally too (local mode). This blurs the line. Options:

- **A) Web UI is always paid** — even running locally requires a subscription. Simple but may feel hostile.
- **B) Local web UI is free, cloud features are paid** — the UI itself is free when self-hosted, but cloud storage, managed AI, sharing, and connectors requiring OAuth infrastructure are paid.
- **C) Local web UI is open-source** — release HyperPersonalWeb as open-source too. Revenue comes purely from hosting.

**Recommendation: Option B.** The local web UI is free (users can run it themselves), but it connects to the paid service for cloud features. This maximizes adoption (free local UI drives CLI usage and community) while reserving infrastructure-dependent features for revenue. The private repo protects the web codebase from competitors standing up a competing hosted service trivially, while users who want to self-host can.

## 14. Sharing and Permissions Layer (Future Phase)

A future phase will add the ability for users to connect their archives with friends and family.

### Concept

Each user has their own archive (their "web"). Sharing creates **read-only views** into selected portions of another user's archive. The owner always controls what's shared.

### Sharing Granularity (to be designed)

Candidates for sharable units:
- **Entire archive** — share everything (unlikely to be the common case)
- **Folders** — share "Letters/Grandma Rose" with a cousin
- **Tags** — share everything tagged "1996 Family Reunion"
- **People** — share all files linked to a specific person
- **Individual files** — share a specific transcript or photo

### Permission Levels (to be designed)

- **View** — read metadata, transcripts, view photos. Cannot download originals.
- **Contribute** — add entities, tags, corrections to shared items. Changes are proposals until approved by owner.
- **Full access** — download originals, bulk export

### Technical Implications

- Requires user identity (Auth must be in place — SP-6)
- Requires cloud hosting (sharing is inherently multi-user)
- Permission checks on every API call (middleware concern)
- Shared items need to be indexed for the recipient's search
- Notifications when shared content changes
- Conflict resolution when two people tag the same file differently

This needs its own brainstorm → spec → plan cycle when the time comes.

## 15. Video Segmentation (SP-0B Enhancement)

Old tape-style videos (VHS digitizations, camcorder tapes) often contain 20+ distinct "sessions" — birthday party, then vacation footage, then a school play — all on one file. This is analogous to compilation PDFs containing multiple documents.

### Detection Approach (to be investigated in SP-0B design)

- **Scene change detection** — ffmpeg `select='gt(scene,0.4)'` identifies visual transitions
- **Black frame detection** — recording start/stop often produces black frames
- **Silent audio gaps** — pauses between recording sessions have no audio
- **Timestamp discontinuities** — if video has embedded timestamps, gaps indicate session boundaries
- **Combination approach** — likely need multiple signals weighted together

### Workflow (mirrors existing split pattern)

1. `family-archive split-video --scan` — detect session boundaries, generate `_video-split-proposals.json`
2. User reviews proposals in web UI (or edits JSON for CLI)
3. `family-archive split-video --apply` — extract segments using ffmpeg, record provenance

### Output

Each segment becomes its own file with provenance linking back to the original tape. Segments are then individually transcribable via the audio pipeline.

## 16. Open Questions

1. **Video segmentation approach:** What signals do we use to detect tape session boundaries? Options include: scene change detection (ffmpeg `select='gt(scene,0.4)'`), silent audio gaps, black frame detection, or a combination. Needs investigation during SP-0B design.
2. **Postgres migration scope:** When migrating archive.db to Postgres for cloud mode, do we use an ORM abstraction that works for both SQLite and Postgres, or maintain separate query layers? SQLAlchemy could unify both, but adds complexity to the core library.
3. **Sharing permissions model:** What granularity? Share an entire archive, specific folders, individual files, or entity-level (share all records about a specific person)? Needs its own brainstorm/spec cycle.

1. **Video segmentation approach:** What signals do we use to detect tape session boundaries? Options include: scene change detection (ffmpeg `select='gt(scene,0.4)'`), silent audio gaps, black frame detection, or a combination. Needs investigation during SP-0B design.
2. **Postgres migration scope:** When migrating archive.db to Postgres for cloud mode, do we use an ORM abstraction that works for both SQLite and Postgres, or maintain separate query layers? SQLAlchemy could unify both, but adds complexity to the core library.
3. **Sharing permissions model:** What granularity? Share an entire archive, specific folders, individual files, or entity-level (share all records about a specific person)? Needs its own brainstorm/spec cycle.

## 17. Success Criteria

- **SP-0A complete:** `pip install git+https://github.com/mmackelprang/HistoryTools.git` works, all existing tests pass, progress callbacks fire
- **Phase 1 MVP:** A user can browse their archive, search transcripts, and approve/reject proposals entirely through the web UI
- **Phase 2 complete:** Full pipeline management, entity tagging, and (optionally) billing through the web UI
- **Phase 3 complete:** At least 3 connectors functional (Contacts, GEDCOM, Google Photos)
