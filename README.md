# Chronos Engine v2.1.0

Chronos Engine is an async FastAPI service that keeps calendars, templates and command workflows in sync with a SQLite database.  
The project ships with a scheduler that can pull data from Google Calendar (real OAuth or mocked), normalize it into the local store, run it through plugins (including the command handler), and expose the result through a modern API and dashboard.

---

## 🚀 Highlights
- **FastAPI + Async SQLAlchemy** – non-blocking API backed by SQLite (`data/chronos.db`) with UTC-indexed columns for fast range queries.
- **Pluggable scheduler** – fetches external events, parses them, runs plugins (command handler, analytics, wellness, …) and persists results.
- **Advanced event queries** – `/api/v1/events` supports pagination, time-window filtering, text search and calendar scoping.
- **Template & command workflow** – manage reusable templates, record template usage, and deliver commands to external systems via a queue with completion/failure callbacks.
- **Operations ready** – `/health` verifies database access, FTS availability and scheduler state; API key protection is enabled for all mutating and sensitive endpoints.

---

## 🏗️ Architecture Overview
1. **Scheduler (`src/core/scheduler.py`)** pulls calendar events, invokes the plugin pipeline and persists every event (including UTC timestamps) through the `DatabaseService`.
2. **Database layer (`src/core/database.py`)** provides async sessions and schema creation for events, templates, analytics data, commands and notes.
3. **API routers (`src/api/…`)** expose CRUD endpoints for events, templates, commands and manual synchronization. The enhanced router contains the advanced filtering logic and command lifecycle endpoints.
4. **Plugins (`plugins/custom/…`)** extend the system – the command handler translates calendar entries into actionable commands and removes them once consumed.
5. **Dashboard & client** assets live in `templates/` and `static/` and can be served from the running FastAPI app.

---

## 🎯 Zielarchitektur: Einfach, praktisch, wartbar

Danke für die klare Ansage. Ich pack’s in **einfach, praktisch, wartbar** – ohne Overengineering. Unten bekommst du eine schlanke, sichere Ziel-Architektur plus ganz konkrete Bausteine, die genau deine Wünsche abdecken (CRUD ohne Programmierung, parallele Termine je nach Modus, nachvollziehbare Persistenz, Batch-Backups, HTML-Mails, Integrationen).

---

# 1) Was du bekommst (Kurzüberblick)

* **Sicher & simpel:** API-Keys mit Rechten (Scopes), Audit-Log, Signaturen für Webhooks. Kein OAuth-Monster.
* **Stabile Persistenz (SQLite):** WAL-Modus, klare Transaktionen, nachvollziehbare Historie.
* **Parallele Termine:** Zwei Modi – **„frei“** (Parallelität erlaubt) & **„Auto-Plan“** (Konflikte werden aktiv vermieden/vorgeschlagen).
* **CRUD ohne Code:** Admin-UI für **Checklisten, Actions, Templates, Whitelists, Workflows**, alles per Formular.
* **Ressourcenzugriff E-Mail:** Versand von **HTML + Anhängen**, mit **Vorlagen** (Templates).
* **Integrationen ohne Magie:** Telegram & n8n/Automation via Webhooks (rein & raus), sauber entkoppelt.
* **Batch-Backups:** Ein Button + geplanter Job (Dumps & Restore-Anleitung).

---

# 2) Sicherheit & Nachvollziehbarkeit (ohne Komplexität)

* **API-Keys mit Scopes:** z. B. `events.read`, `events.write`, `commands.manage`, `admin`. Keys rotierbar, Ablaufdatum, nur gehashte Ablage.
* **Audit-Log (unveränderbar):** Jede Änderung an Events, Checklisten, Actions, Templates, Whitelists → ein Eintrag (wer, was, wann, alt→neu).
* **Signaturen (HMAC):** Für **eingehende** (Telegram/n8n) und **ausgehende** Webhooks (zu n8n/Slack): Header `X-Signature` + Zeitstempel → Schutz vor Replay.
* **Transaktionen & Idempotenz:** Schreibvorgänge immer atomar; externe Aufrufe nur über einen **Outbox-Eintrag** mit **Idempotency-Key**. So gibt’s keine Doppel-Sends.

---

# 3) SQLite stabil betreiben (ohne DB-Wechsel)

* **WAL-Modus** + `busy_timeout`, Foreign Keys an.
* **Ein „Writer-Kanal“** im Prozess: Alle Schreibvorgänge laufen sequenziell. Lesen bleibt parallel. So vermeidest du „database is locked“.
* **Backups**: Siehe Abschnitt 8.

---

# 4) Termin-Logik: Parallel vs. Auto-Plan

* **Modus „Frei“ (Default):** Termine dürfen überlappen. Du bekommst nur einen visuellen Hinweis „Kollision“.
* **Modus „Auto-Plan“ (pro Kalender/Termin wählbar):**

  * Bei Kollision: Vorschlag der nächsten freien Slots (auch für mehrere Teilnehmer via Free/Busy).
  * Bestätigen → Termin wird verschoben. Ablehnen → bleibt wie er ist.

---

# 5) CRUD-Bausteine, die der User pflegt (ohne Programmierung)

Alle Bausteine bekommen **eigene Seiten** in der Admin-UI: Liste, Suchen/Filtern, Neu, Bearbeiten, Löschen.

1. **Checklisten**

   * Pro Event: To-Dos (Häkchen), Reihenfolge, Notizen.
   * Optionales Autocomplete: „Wenn Endzeit erreicht **und** alles abgehakt → Status COMPLETED.“

2. **Actions**

   * Whitelist von Befehlen (Name, Zielsystem, erlaubte Parameter).
   * Aus einem Kalendereintrag `ACTION: …` wird ein **Command-Datensatz** (wird **nicht** im Backend ausgeführt; nur über Integrationen ausgeliefert).
   * **Statusfluss:** PENDING → PROCESSING → COMPLETED/FAILED (alles im UI änderbar & nachvollziehbar).

3. **Templates**

   * **E-Mail-Templates (HTML/Text)** mit Platzhaltern (`{{event.title}}`, `{{user.name}}`), Vorschau & Testversand.
   * **Event-Vorlagen** (z. B. Standard-Dauer, Teilnehmer, Standard-Checkliste).
   * **Webhook-Payload-Templates** (JSON), streng ohne Code, nur Platzhalter.

4. **Whitelists**

   * Zielsysteme (z. B. `TELEGRAM`, `N8N`, `SMTP`), erlaubte Actions, erlaubte Parameter/Typen (z. B. `int`, `string`, `email`).
   * Alles klickbar pflegbar, inkl. Export/Import (YAML/JSON).

5. **Workflows (einfach)**

   * „Wenn **Action X** COMPLETED → erzeuge **Action Y** (mit Param-Vorlage)“.
   * Auch als Liste/CRUD in der UI (Name, Trigger, Folge-Action, Parameter-Template).
   * Kein Code, kein KI-Teil – nur deklarativ.

---

# 6) E-Mail als Ressource (HTML + Attachments)

* **Mail-Service integriert** (SMTP):

  * Versand: **HTML + Text + Anhänge**.
  * Absender & Empfänger (To/Cc/Bcc), Reply-To, Priorität.
  * **Vorlagen** aus Punkt 5 (Templates).
  * Logs pro Versand (Message-ID, Zustellstatus, Fehler).
* **Nutzung:**

  * direkt aus einem `ACTION: SEND_EMAIL …` (wird über Whitelist geprüft),
  * oder manuell aus der UI („Testversand“ / „Newsletter an Teilnehmer“).

---

# 7) Integrationen (Telegram, n8n & Co.) – ohne „Magie“

**Prinzip:** Alles läuft über eine **einheitliche Outbox** (Ausgangswarteschlange). Nie direkte Sofort-Calls im kritischen Pfad.

* **Telegram (Inbound):**

  * Bot-Webhook nimmt Nachrichten an → mapt auf Note/Action/Event (nach Regeln/Whitelist).
  * Auth via Telegram-Signaturprüfung + optional erlaubte Chat-IDs.

* **Telegram (Outbound):**

  * Notifications bei Statuswechseln (z. B. Action SUCCESS/FAIL). Text aus Template.

* **n8n (Outbound):**

  * `ACTION:` erzeugt Outbox-Eintrag → HTTP-POST an n8n-Workflow (mit Signatur).
  * **Retry** bei Fehlern (Backoff). **DLQ** (Fehlerkorb) mit Einsicht & Retry-Button.

* **n8n (Inbound/Callback):**

  * n8n ruft `/commands/{id}/complete` auf → wir setzen Status + lösen ggf. Folge-Workflow aus.

*(Später erweiterbar: Slack, Mattermost, Teams – alles über dieselbe Outbox/Template-Schiene.)*

---

# 8) Batch-Backup (ein Button & planbar)

* **Was:** DB-Datei (SQLite), WAL, Konfig (`chronos.yaml`), Templates/Assets → ZIP mit Zeitstempel.
* **Wie:**

  * Knopf „Backup jetzt“ in der UI.
  * Geplante Backups (täglich/weekly) per Scheduler-Job, Rotationsregeln (z. B. 7 täglich, 4 wöchentlich, 12 monatlich).
* **Restore-Anleitung:** einfache Seite mit Schritt-für-Schritt (App stoppen → Files ersetzen → `integrity_check` → App starten).

---

# 9) Datenmodell (einfach & robust)

* `events` (id, title, start, end, mode, …, **sub_tasks_json TEXT**, **all_done BOOL**)
* `event_links` (id, source_event_id, target_event_id, link_type, created_at, **UNIQUE(source,target,link_type)**, **CHECK(source!=target)**)
* `external_commands` (id, command, target_system, params_json, status, retries, timeout_at, last_error, created_at, updated_at, **idempotency_key**, **indexes(status,target_system)**)
* `templates` (id, name, type: email/html/text/webhook, body, variables_json)
* `whitelists` (id, system, action, allowed_params_json)
* `workflows` (id, name, trigger_action, follow_action, follow_target, params_template_json)
* `audit_log` (id, ts, actor, scope, entity, entity_id, change_json, ip)

*(JSON als TEXT – gut mit SQLite; „ableitbare“ Flags wie `all_done` als Spalte für schnelle Filter.)*

---

# 10) Bedienoberfläche (nur das, was du brauchst)

* **Events:** Liste, Filter, Details, Checklisten mit Häkchen (speichern live), Modus-Schalter „Frei/Auto-Plan“.
* **Actions/Commands:** Liste mit Status, Details, „erneut senden“, manuelles Complete/Fail (mit Grund).
* **Templates:** E-Mail-Editor (HTML/Text, Platzhalter-Hilfe, Vorschau, Testversand).
* **Whitelists:** Systeme/Aktionen/Parameter – Formular mit Typenprüfung.
* **Workflows:** If-this-then-that Maske.
* **Integrationen:** Telegram-Bot-Daten, n8n-Webhook-URLs, Signaturschlüssel.
* **Backups:** Jetzt-Button + Planer, Download-Liste.
* **Protokolle:** Audit-Log & Versand-/Webhook-Logs.

---

# 11) Was wir explizit **nicht** tun (damit’s schlank bleibt)

* Keine Ausführung fremden Codes.
* Keine „schlauen“ Heuristiken/KI – alles deklarativ/konfigurierbar.
* Keine Soft-Deleletes: echte Historie im Audit-Log, aber echte Deletes in den Tabellen (wo sinnvoll).

---

# 12) Minimaler, konkreter Umsetzungs-Schnitt (Startpaket)

1. **Sicherheitsbasis:** API-Keys mit Scopes, HMAC-Signaturen, Audit-Log.
2. **SQLite-Stabilisierung:** WAL + Writer-Kanal, Transaktions-Disziplin.
3. **CRUD-UI:** Templates, Whitelists, Workflows (einfach), Checklisten.
4. **Outbox + Integrationen:** Outbox-Tabellen, n8n-Adapter (Outbound + Callback), Telegram-Adapter (in/out).
5. **E-Mail-Service:** HTML/Text, Anhang, Template-Binder, Logs.
6. **Backups:** Button & Planer.

---

## Reality-Marker

**Spec/Design.** Das ist eine bewusst vereinfachte, robuste Architektur mit klaren, pflegbaren Bausteinen und ohne „Magie“. Sie erfüllt deine Forderungen nach **Sicherheit**, **Nachvollziehbarkeit**, **Parallel-Modus/Auto-Plan**, **CRUD-Pflege** aller User-Bausteine, **Batch-Backups** und **HTML-Mails** – und bleibt SQLite-tauglich.

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
- `api.api_key` – bearer token required for most endpoints (default: `development-key-change-in-production`).
- `calendar.credentials_file` / `token_file` – point to Google OAuth/service-account credentials. If the files are missing the client falls back to the mock calendar implementation.
- `plugins` – enable/disable plugins and set the custom directory (defaults to `plugins/custom`).
- `command_handler.action_whitelist` – allow-listed command keywords that the command plugin can emit.

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
1. Fetch events from Google Calendar (real API when configured, mock data otherwise).
2. Parse raw events into `ChronosEvent` domain objects.
3. Run each event through the plugin pipeline. The command handler can turn specially formatted events into actionable commands; when a plugin consumes an event it is removed from SQLite and the external calendar.
4. Persist remaining events with UTC-normalized timestamps and analytics metadata.
5. Background tasks (timeboxing, re-planning, analytics) leverage the stored data via async sessions.

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
- **Google Calendar authentication** – add OAuth or service account credentials; without them the client runs in mock mode and serves sample events.
- **Database issues** – delete `data/chronos.db` for a clean slate, then restart the API to recreate tables.
- **Static assets missing** – confirm the `templates/` and `static/` directories are present before launching the app.

---

**Chronos Engine** – production-ready calendar orchestration with plugin-driven automation.
