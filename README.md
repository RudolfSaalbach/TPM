# Chronos Engine v2.1.0

Chronos Engine is an async FastAPI service that keeps calendars, templates, email workflows, and external command queues in sync with a SQLite datastore. The scheduler ingests calendar events, normalises and enriches them through plugins, persists the result, and exposes the aggregated data through a modern API and a lightweight admin dashboard.

---

## Table of Contents
1. [Feature Highlights](#feature-highlights)
2. [Architecture Overview](#architecture-overview)
3. [Getting Started](#getting-started)
4. [Configuration](#configuration)
5. [Persistence & Data Model](#persistence--data-model)
6. [Scheduler & Plugin Pipeline](#scheduler--plugin-pipeline)
7. [API Surface](#api-surface)
8. [Dashboard & Frontend](#dashboard--frontend)
9. [Operations & Observability](#operations--observability)
10. [Target Architecture Blueprint](#target-architecture-blueprint)
11. [Production Readiness Assessment](#production-readiness-assessment)
12. [Testing](#testing)
13. [Project Layout](#project-layout)
14. [Troubleshooting](#troubleshooting)

---

## Feature Highlights
- **FastAPI + Async SQLAlchemy** – fully asynchronous API backed by SQLite (`data/chronos.db`) with UTC-indexed columns for fast range queries.
- **Pluggable scheduler** – periodically fetches external events, parses and runs plugins (command handler, analytics, wellness, …), and persists the results.
- **Advanced event queries** – `/api/v1/events` supports pagination, time-window filtering, full-text search, calendar scoping, and analytics projections.
- **Template & command workflow** – manage reusable templates, record template usage, and deliver commands to external systems via a queue with completion/failure callbacks.
- **Operations ready** – `/health` verifies database access, FTS availability, and scheduler state; API key protection is enabled for all mutating and sensitive endpoints.
- **HTML mail delivery** – SMTP-backed sender supports HTML + text bodies, attachments, templating, and per-message audit logging.

---

## Architecture Overview
1. **Scheduler (`src/core/scheduler.py`)** pulls calendar events, invokes the plugin pipeline, and persists every event (including UTC timestamps) through the `DatabaseService`.
2. **Database layer (`src/core/database.py`)** provides async sessions and schema creation for events, templates, analytics data, commands, notes, and audit entries.
3. **API routers (`src/api/*.py`)** expose CRUD endpoints for events, templates, commands, manual synchronisation, health checks, and operational tooling.
4. **Plugins (`plugins/custom/…`)** extend the system – the command handler translates calendar entries into actionable commands and removes them once consumed.
5. **Dashboard assets (`templates/`, `static/`)** deliver the admin UI that interacts with the API without additional backend glue.

---

## Getting Started
1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
2. **Configure environment**
   - Copy `config/chronos.example.yaml` to `config/chronos.yaml` and adjust API keys, scheduler frequency, calendar credentials, mail settings, and command whitelists.
   - Set optional overrides via environment variables (see [Configuration](#configuration)).
3. **Initialise the database**
   ```bash
   alembic upgrade head
   ```
   or run `python -m src.main --init-db` for a lightweight bootstrap.
4. **Run the app**
   ```bash
   uvicorn src.main:app --reload
   ```
   Visit `http://localhost:8000` for the dashboard and `http://localhost:8000/docs` for the OpenAPI UI.
5. **Docker**
   ```bash
   docker compose up --build
   ```
   The compose setup enables the health check, scheduler worker, and exposes the API on port `8000`.

---

## Configuration
- **File-based** – `config/chronos.yaml` contains scheduler cadence, API key definitions, command whitelists, template defaults, SMTP credentials, Telegram/n8n integration keys, and backup rotation policies.
- **Environment variables** – every config entry can be overridden with `CHRONOS__SECTION__KEY=value`. Example: `CHRONOS__scheduler__poll_interval=120`.
- **Secrets** – store API keys, SMTP passwords, and webhook secrets in environment variables or secrets managers; the application never logs raw secrets.
- **Validation** – configuration is validated at startup; invalid entries abort boot with actionable error messages.

---

## Persistence & Data Model
Chronos relies on SQLite with Write-Ahead Logging (WAL) enabled for safe concurrent reads.

| Table | Purpose | Notable Columns |
|-------|---------|-----------------|
| `events` | Normalised calendar entries | `start_utc`, `end_utc`, `mode`, `sub_tasks_json`, `all_done`, metadata hashes |
| `event_links` | Relations between events | `source_event_id`, `target_event_id`, `link_type` |
| `external_commands` | Queue for outbound actions | `target_system`, `params_json`, `status`, `retries`, `timeout_at`, `idempotency_key` |
| `templates` | Email / webhook / event templates | `type`, `body`, `variables_json` |
| `whitelists` | Allowed systems + parameters | `system`, `action`, `allowed_params_json` |
| `workflows` | Declarative follow-up rules | `trigger_action`, `follow_action`, `params_template_json` |
| `audit_log` | Immutable change log | `actor`, `scope`, `entity`, `change_json`, `ip` |

Data access is wrapped in async transactions; all writes happen through a dedicated writer pathway to avoid `database is locked` errors. Backups capture the SQLite db, WAL file, configuration, and template assets.

---

## Scheduler & Plugin Pipeline
- **Source adapters** ingest events from Google Calendar (real OAuth or mocked for testing).
- **Normalisation** ensures all timestamps are stored in UTC, all-day markers are derived, and tags/templates are extracted.
- **Plugins** run sequentially within a transaction-safe pipeline:
  - *Command Handler* – converts `ACTION:` events into queue entries, enforces the whitelist, and deletes consumed calendar items.
  - *Analytics* – computes activity breakdowns and time allocation statistics.
  - *Wellness / AI helpers* – optional enrichments that label events or suggest follow-ups.
- **Modes** – events support `free` (allow overlap) and `auto-plan` (detect and propose conflict-free slots); conflicts surface in the dashboard and via webhook notifications.

---

## API Surface
Key endpoints (API key required unless noted):
- `GET /health` – readiness probe checking DB connectivity, FTS5 availability, and scheduler heartbeat.
- `GET /api/v1/events` – advanced querying with pagination, filters (`from`, `to`, `calendar_id`, `direction`, `text`, `include_completed`), and analytics payload.
- `POST /api/v1/events/sync` – trigger a scheduler sync run.
- `GET /api/v1/templates` / `POST /api/v1/templates` – CRUD for email, webhook, and event templates.
- `GET /api/v1/commands/{system_id}` – poll queued commands for an integration client.
- `POST /api/v1/commands/{command_id}/complete` – idempotent completion/failure callbacks.
- `POST /api/v1/mail/send` – send templated HTML+text emails with attachments.
- `GET /api/v1/backups` / `POST /api/v1/backups` – list and trigger snapshot archives.

All endpoints emit structured JSON responses and raise standard HTTP exceptions on validation errors.

---

## Dashboard & Frontend
The admin UI lives in `templates/chronos_gui_client.html` and ships with:
- Live event grid with filtering, checklist management, and conflict hints.
- Command queue monitor with manual retry, completion, and failure flows.
- Template editor with HTML preview, placeholder cheat-sheet, and test send action.
- Whitelist, workflow, integration, and backup management panels.

> **Note:** The frontend is intentionally monolithic today for simplicity. A future refactor will split HTML, CSS, and JavaScript into dedicated bundles (`static/js`, `static/css`) to ease maintenance.

---

## Operations & Observability
- **Health checks** – `/health` performs database round-trips, validates FTS5 modules, and ensures the scheduler heartbeat timestamp is fresh.
- **Logging** – structured logs (JSON) expose request IDs, plugin actions, command transitions, and email delivery events.
- **Security** – API keys with scopes (`events.read`, `events.write`, `commands.manage`, `admin`) protect sensitive endpoints. HMAC signatures (`X-Signature`, `X-Timestamp`) secure inbound/outbound webhooks.
- **Backups** – manual "Backup now" action and scheduled jobs create zip archives with DB, config, and template assets; retention policies rotate daily/weekly/monthly snapshots.

---

## Target Architecture Blueprint
To keep the platform *einfach, praktisch, wartbar*, the roadmap follows these principles:
1. **Security & Traceability** – scoped API keys, immutable audit log, signed webhooks, idempotent outbox pattern.
2. **SQLite Stability** – WAL mode, `busy_timeout`, single-writer channel, deterministic migrations.
3. **Scheduling Modes** – `frei` allows overlaps, `auto-plan` proposes conflict-free alternatives and honours free/busy data.
4. **CRUD without Code** – admin UI for checklists, actions, templates, whitelists, workflows with import/export support.
5. **Email as a First-Class Resource** – HTML/text bodies, attachments, template binding, detailed delivery logs.
6. **Integrations via Outbox** – Telegram, n8n, Slack, etc. consume the same outbox queue with retries and dead-letter inspection.
7. **Batch Backups** – one-click/manual backups and scheduled jobs with clear restore instructions.
8. **Declarative Workflows** – simple "Action X completed ⇒ enqueue Action Y" rules without custom code execution.
9. **Lean Scope** – no arbitrary code execution, no heuristics/AI magic, no soft deletes (audit log holds history).

---

## Production Readiness Assessment
A recent review rated Chronos Engine v2.1.0 as **Conditionally Production-Ready**:

### Strengths
- Robust modular architecture (`core`, `api`, `database`, `plugins`) with clean separation of concerns.
- Secure command handling via non-negotiable whitelist and scoped API keys.
- Flexible API layer with performant filtering and pagination.
- Containerised deployment with docker-compose, health checks, and externalised configuration.

### Gaps & Risks
- **Testing gap (critical):** integration tests for `GET /api/v1/events`, command polling, and completion flows are required to cover new async behaviour.
- **Frontend maintainability:** the single-file dashboard must be decomposed into dedicated JS/CSS bundles as features grow.
- **Polling resilience:** introduce per-client API keys and stalled-command recovery to harden long-running integrations.

### Next Steps
1. Build unit tests for `CommandHandlerPlugin` covering `NOTIZ`, `URL`, and `ACTION` flows plus whitelist enforcement.
2. Add integration tests for advanced event filters, command polling lifecycle, and email/template CRUD endpoints.
3. Refine the frontend build pipeline (e.g. Vite/Rollup) and migrate inline assets into modular bundles.

---

## Testing
Run the full suite before committing changes:
```bash
pytest -q
```
Targeted runs are available via `pytest tests/integration/test_enhanced_routes.py` or `pytest tests/unit/test_command_handler_plugin.py` for focused verification.

---

## Project Layout
```
├── README.md
├── docker-compose.yml
├── requirements.txt
├── src/
│   ├── api/
│   ├── core/
│   ├── main.py
│   └── ...
├── plugins/
├── templates/
├── static/
├── tests/
│   ├── unit/
│   └── integration/
└── config/
```

---

## Troubleshooting
- **Database is locked** – ensure the app runs a single writer process; enable WAL (`PRAGMA journal_mode=WAL`).
- **Health endpoint fails** – verify SQLite has FTS5 enabled and that migrations ran successfully.
- **Command queue stuck** – check for stalled clients; the API exposes endpoints to reset and retry commands.
- **Email delivery issues** – confirm SMTP credentials, review delivery logs, and validate template placeholders.

For additional support or architecture discussions, open an issue or contact the maintainers listed in `FINAL_STATUS.md`.
