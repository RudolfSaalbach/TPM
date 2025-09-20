# Chronos Engine v2.1.0

Chronos Engine is an async FastAPI service that keeps calendars, templates and command workflows in sync with a SQLite database.
The project ships with a scheduler that can pull data from **CalDAV/Radicale servers** (primary) or Google Calendar (fallback), normalize it into the local store, run it through plugins (including the command handler), and expose the result through a modern API and dashboard.

---

## 🚀 Highlights
- **FastAPI + Async SQLAlchemy** – non-blocking API backed by SQLite (`data/chronos.db`) with UTC-indexed columns for fast range queries.
- **CalDAV/Radicale Integration** – native support for self-hosted CalDAV servers with RFC 6578 sync-collection for efficient updates.
- **Backend-Agnostic Design** – unified SourceAdapter interface supports CalDAV and Google Calendar with seamless switching.
- **Pluggable scheduler** – fetches external events, parses them, runs plugins (command handler, analytics, wellness, …) and persists results.
- **Advanced event queries** – `/api/v1/events` supports pagination, time-window filtering, text search and calendar scoping.
- **Template & command workflow** – manage reusable templates, record template usage, and deliver commands to external systems via a queue with completion/failure callbacks.
- **Operations ready** – `/health` verifies database access, FTS availability and scheduler state; API key protection is enabled for all mutating and sensitive endpoints.

---

## 🏗️ Architecture Overview
1. **CalendarSourceManager (`src/core/calendar_source_manager.py`)** provides unified access to CalDAV and Google Calendar backends via the SourceAdapter interface.
2. **Scheduler (`src/core/scheduler.py`)** pulls calendar events from multiple sources, invokes the plugin pipeline and persists every event (including UTC timestamps) through the `DatabaseService`.
3. **Database layer (`src/core/database.py`)** provides async sessions and schema creation for events, templates, analytics data, commands and notes.
4. **API routers (`src/api/…`)** expose CRUD endpoints for events, templates, commands, CalDAV management and manual synchronization.
5. **Plugins (`plugins/custom/…`)** extend the system – the command handler translates calendar entries into actionable commands and removes them once consumed.
6. **Dashboard & client** assets live in `templates/` and `static/` and can be served from the running FastAPI app.

---

## ⚙️ Getting Started

### Prerequisites
- Python 3.11+
- (Optional) Docker & Docker Compose if you prefer containers

### Local Setup
```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the API (reads config/chronos.yaml)
python -m src.main
```
The server listens on `http://0.0.0.0:8080` by default. Logs are written to `logs/chronos.log` and the SQLite database is stored in `data/chronos.db`.

### Docker
```bash
docker-compose up --build
```
This builds the application image, mounts the project files and exposes the API on port `8080`.

---

## 🔐 Configuration & Secrets
Configuration lives in `config/chronos.yaml`. Important sections:
- `calendar_source.type` – choose between `"caldav"` (default) or `"google"` for the primary backend.
- `caldav.calendars` – list of CalDAV calendar collections with URLs, authentication and sync settings.
- `caldav.auth` – authentication mode: `"none"`, `"basic"`, or `"digest"` with credential references.
- `api.api_key` – bearer token required for most endpoints (default: `development-key-change-in-production`).
- `google.credentials_file` / `token_file` – Google OAuth/service-account credentials (when using Google backend).
- `plugins` – enable/disable plugins and set the custom directory (defaults to `plugins/custom`).

See `config/examples/` for CalDAV setup examples including production, multi-server and hybrid configurations.

Override values via environment variables when running in production (e.g. `export CHRONOS_API_KEY="super-secret"`).

---

## 🌐 API Surface
All protected endpoints expect `Authorization: Bearer <api_key>`.

### Health & status
| Endpoint | Method | Description |
| --- | --- | --- |
| `/health` | GET | Full system check (database connectivity, FTS tables, scheduler health). |
| `/api/v1/sync/health` | GET | Lightweight scheduler heartbeat (no auth required). |

### Events & templates
| Endpoint | Method | Notes |
| --- | --- | --- |
| `/api/v1/events` | GET | Advanced filtering (calendar, anchor date, range, direction, full-text `q`, pagination). |
| `/api/v1/events` | POST | Create an event via the scheduler (runs through plugins and persists to SQLite). |
| `/api/v1/templates` | GET/POST/PUT/DELETE | Manage reusable event templates with ranking and metadata updates. |
| `/api/v1/templates/{template_id}/use` | POST | Record template usage for analytics. |

### CalDAV Management
| Endpoint | Method | Description |
| --- | --- | --- |
| `/caldav/backend/info` | GET | Get current backend information and capabilities. |
| `/caldav/connection/test` | POST | Test CalDAV server connection. |
| `/caldav/backend/switch` | POST | Switch between CalDAV and Google Calendar backends. |
| `/caldav/calendars` | GET | List all available CalDAV calendars. |
| `/caldav/calendars/{id}/sync` | POST | Manually sync a specific calendar. |
| `/caldav/calendars/{id}/events` | POST | Create event in CalDAV calendar. |
| `/caldav/calendars/{id}/events/{event_id}` | GET/PATCH/DELETE | Manage CalDAV events. |

### Command queue
| Endpoint | Method | Description |
| --- | --- | --- |
| `/api/v1/commands/{system_id}` | GET | Poll commands for a target system (resets stale `PROCESSING` items before delivery). |
| `/api/v1/commands/{command_id}/complete` | POST | Mark a command as completed. |
| `/api/v1/commands/{command_id}/fail` | POST | Report a failure with an error message and optional retry instructions. |

### Synchronisation & analytics
| Endpoint | Method | Description |
| --- | --- | --- |
| `/api/v1/sync/calendar` | POST | Trigger a manual calendar sync via the scheduler. |
| `/api/v1/analytics/productivity` | GET | Placeholder productivity metrics (requires analytics engine). |
| `/api/v1/ai/optimize` | POST | Request optimization suggestions from the AI optimizer module. |

Interactive API docs are available at `http://localhost:8080/docs` once the service is running.

---

## 🧠 Scheduler & Plugin Workflow
1. Fetch events from CalDAV/Radicale servers or Google Calendar via the unified SourceAdapter interface.
2. Parse raw events into `ChronosEvent` domain objects with backend-agnostic idempotency markers.
3. Run each event through the plugin pipeline. The command handler can turn specially formatted events into actionable commands; when a plugin consumes an event it is removed from SQLite and the external calendar.
4. Process calendar repair rules (birthday formatting, anniversary detection) that work identically across CalDAV and Google backends.
5. Persist remaining events with UTC-normalized timestamps and analytics metadata.
6. Background tasks (timeboxing, re-planning, analytics) leverage the stored data via async sessions.

Custom plugins can be added under `plugins/custom/` by subclassing `EventPlugin` or `SchedulingPlugin` from `src/core/plugin_manager.py`.

---

## 🗄️ Data & Persistence
- Primary database: SQLite file at `data/chronos.db` (created automatically).
- Tables defined in `src/core/models.py` (events, analytics data, templates, template usage, commands, notes, URL payloads, tasks).
- Async sessions obtained through `db_service.get_session()` to ensure proper cleanup in request handlers and background jobs.

---

## 🧪 Tests
Run the test suite with:
```bash
pytest
```
Use `pytest tests/unit/test_event_parser.py::TestEventParser` (or similar) to execute a single test module.

---

## 📁 Project Layout
```
src/
├── api/             # FastAPI routers, schemas and dashboard handlers
├── core/            # Scheduler, models, plugins, analytics, AI, database helpers
├── database/        # Additional DB models (e.g. pending sync state)
├── config/          # Runtime configuration loading
└── main.py          # FastAPI application factory & lifespan hooks
plugins/custom/      # Built-in plugins (command handler, wellness monitor, ...)
templates/           # Dashboard and GUI client templates
static/              # Front-end assets for the dashboard/client
```

---

## 🛠️ Troubleshooting
- **Authorization errors** – ensure the `Authorization` header matches `api.api_key` in `config/chronos.yaml`.
- **CalDAV connection issues** – verify server URLs, check network connectivity and authentication credentials. Use `/caldav/connection/test` to diagnose.
- **Google Calendar authentication** – add OAuth or service account credentials; without them the client runs in mock mode and serves sample events.
- **Backend switching** – use `/caldav/backend/switch` API or update `calendar_source.type` in config and restart.
- **Database issues** – delete `data/chronos.db` for a clean slate, then restart the API to recreate tables.
- **Static assets missing** – confirm the `templates/` and `static/` directories are present before launching the app.

For CalDAV setup guidance, see `docs/CalDAV_Integration_Guide.md` and configuration examples in `config/examples/`.

---

**Chronos Engine** – production-ready calendar orchestration with plugin-driven automation.
