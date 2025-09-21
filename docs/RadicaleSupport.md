 hier ist das **komplette, KI-fertige Anforderungspaket** für den nahtlosen Wechsel von **Google → Radicale (CalDAV)**, mit **Radicale als Default**, **ohne Rückbau**. Verarbeitung ist **für alle Kalender identisch**; die Aufteilung in „Automation / Dates / Special“ dient nur der **User-Sicht** (Alias), nicht der Logik.

# 

**Spec/Design** – vollständig, implementierungsleitend, code-frei (nur YAML/ENV). Keine Hintergrundarbeit offen.

---

# 1) Zielbild (kurz)

- **Standard-Backend:** Radicale/CalDAV.

- **Optionales Backend:** Google Calendar (weiterhin nutzbar via Umschalter).

- **Gleichbehandlung aller Kalender:** Alle Collections werden identisch repariert und angereichert (kein Routing nach Kalendertyp). Aliase sind rein visuell/organisatorisch.

- **Repair-First:** CalendarRepairer (Write-Back) läuft **vor** jedem Enrichment/Command.

- **Umschalten per Config:** `calendar_source.type: caldav|google`.

---

# 2) Architekturänderungen (minimal, stabil)

## 2.1 SourceAdapter-Schnittstelle (neu/vereinheitlicht)

Einführen/angleichen einer internen Schnittstelle, die der Scheduler und der CalendarRepairer nutzen:

```
interface SourceAdapter:
  capabilities() -> { name, can_write: bool, supports_sync_token: bool, timezone: str }
  list_calendars() -> [CalendarRef{id, alias, url, read_only, timezone}]
  list_events(cal: CalendarRef, since, until, page_token?) -> {events, next_page_token?}
  get_event(cal, id) -> Event
  patch_event(cal, id, patch, if_match_etag) -> new_etag
  create_override(cal, master_id, recurrence_id, patch) -> new_event_id
  get_series_master(cal, id) -> Event
```

- **GoogleAdapter** (bestehend) und **CalDAVAdapter** (neu) implementieren diese Schnittstelle.

- **Event-Normalisierung bleibt gleich:** UTC + `tz`, `all_day`, `rrule`, `etag`, `uid`, `is_series_master`, `recurrence_id`, `extended/meta`.

## 2.2 Idempotenz-Marker (vereinheitlicht)

- Internes Modell: `meta.enrichment.cleaned=v1`, `meta.enrichment.rule_id`, `meta.enrichment.signature`, `meta.original_summary`, `meta.payload`.

- **Adapter-Mapping:**
  
  - **CalDAV:** schreibe/lese `X-CHRONOS-*` Properties in `VEVENT`.
  
  - **Google:** nutze `extendedProperties.private.*`.

- **Signature:** `SHA256(original_summary|start|recurrence)`.

## 2.3 Pipeline-Order (fix)

`UndefinedGuard` → **CalendarRepairer (Write-Back)** → `KeywordEnricher` → `command_handler` → Rest.  
(Keine Sonderpfade je Kalender.)

---

# 3) Konfiguration (Radicale als Default)

## 3.1 `chronos.yaml`

```yaml
version: 1

calendar_source:
  type: "caldav"                       # DEFAULT: Radicale/CalDAV
  timezone_default: "Europe/Berlin"

caldav:
  calendars:                           # identische Verarbeitung aller Collections
    - id: "automation"
      alias: "Automation"
      url: "http://10.210.1.1:5232/radicaleuser/8a04a78f-0785-8dc1-8593-ae54b948b5c5/"
      read_only: false
      timezone: "Europe/Berlin"
    - id: "dates"
      alias: "Dates"
      url: "http://10.210.1.1:5232/radicaleuser/78fad4eb-17fd-a588-bbe6-96c0b615c123/"
      read_only: false
      timezone: "Europe/Berlin"
    - id: "special"
      alias: "Special"
      url: "http://10.210.1.1:5232/radicaleuser/bb4d93ef-f55d-bda2-63b8-82a4962dbed5/"
      read_only: false
      timezone: "Europe/Berlin"

  auth:
    mode: "none"              # "none" | "basic" | "digest"
    username: "radicaleuser"  # nur genutzt, wenn mode ≠ "none"
    password_ref: "env:RADICALE_PASSWORD"

  transport:
    verify_tls: false         # bei http/WireGuard ok; bei https -> true
    connect_timeout_s: 5
    read_timeout_s: 15

  sync:
    use_sync_collection: true # RFC 6578 sync-token bevorzugt
    window_days: 400          # Fallback-Zeitfenster
    parallel_requests: 3

  write:
    if_match: true            # ETag-Schutz
    retry_conflict: 1
    include_vtimezone: true

google:                        # optionaler Alt-Adapter, kein Default
  enabled: false
  # vorhandene Felder (Credentials, calendarIds, ...)

pipeline:
  order: ["UndefinedGuard","CalendarRepairer","KeywordEnricher","command_handler"]

repair_and_enrich:
  reserved_prefixes: ["ACTION","MEETING","CALL"]  # niemals umschreiben
  parsing:
    accept_date_separators: [".","-","/"]
    day_first: true
    year_optional: true
    strict_when_ambiguous: true
  series_policy:
    edit_master_if_keyword_on_master: true
    edit_instance_if_keyword_on_instance: true
    do_not_edit_past_instances: true
  idempotency:
    marker_keys:
      cleaned: "X-CHRONOS-CLEANED"
      rule_id: "X-CHRONOS-RULE-ID"
      signature: "X-CHRONOS-SIGNATURE"
      original_summary: "X-CHRONOS-ORIGINAL-SUMMARY"
      payload: "X-CHRONOS-PAYLOAD"

  # Regeln (gleich für alle Kalender; kurze EN-Titel, DE/EN-Keywords)
  rules:
    - id: "bday"
      keywords: ["BDAY","BIRTHDAY","GEB","GEBURTSTAG"]
      title_template: "🎉 Birthday: {name} ({date_display}){age_suffix}"
      age_suffix_template: " – turns {age}."
      all_day: true
      rrule: "FREQ=YEARLY"
      leap_day_policy: "FEB_28"
      enrich:
        event_type: "birthday"
        tags: ["personal","birthday"]
        sub_tasks:
          - { text: "Buy card", completed: false }
          - { text: "Get gift", completed: false }

    - id: "bdaywarn"
      keywords: ["BDAYWARN","BIRTHDAYWARN","GEBWARN","GEBURTSTAGWARN"]
      title_template: "⏰ {name}'s birthday in {warn_abs_days} days ({date_day_month})"
      all_day: true
      rrule: "FREQ=YEARLY"
      warn_offset_days: -4
      link_to_rule: "bday"
      enrich:
        event_type: "birthday_warning"
        tags: ["personal","reminder"]

    - id: "rip"
      keywords: ["RIP","DEATH","MEMORIAL","TOD","GEDENKEN"]
      title_template: "🕯️ In memory of {name} († {date_display}){years_since_suffix}"
      years_since_suffix_template: " – {years_since}th."
      all_day: true
      rrule: "FREQ=YEARLY"
      enrich:
        event_type: "memorial"
        tags: ["memorial"]
        sub_tasks:
          - { text: "Flowers/visit", completed: false }

    - id: "ripwarn"
      keywords: ["RIPWARN","MEMORIALWARN","TODWARN","GEDENKWARN"]
      title_template: "🕯️ Memorial for {name} in {warn_abs_days} days ({date_day_month})"
      all_day: true
      rrule: "FREQ=YEARLY"
      warn_offset_days: -3
      link_to_rule: "rip"
      enrich:
        event_type: "memorial_warning"
        tags: ["memorial","reminder"]

    - id: "anniv"
      keywords: ["ANNIV","ANNIVERSARY","JUBI","JUBILÄUM"]
      title_template: "🎖️ {label}: {name_or_label} since {date_display}{years_since_suffix}"
      label_from_payload: true
      years_since_suffix_template: " – {years_since}th."
      all_day: true
      rrule: "FREQ=YEARLY"
      enrich:
        event_type: "anniversary"
        tags: ["anniversary"]

    - id: "annivwarn"
      keywords: ["ANNIVWARN","ANNIVERSARYWARN","JUBIWARN","JUBILÄUMWARN"]
      title_template: "⏰ {label}: {name_or_label} in {warn_abs_days} days ({date_day_month})"
      all_day: true
      rrule: "FREQ=YEARLY"
      warn_offset_days: -7
      link_to_rule: "anniv"
      enrich:
        event_type: "anniversary_warning"
        tags: ["anniversary","reminder"]
```

## 3.2 `.env` (Beispiel)

```
RADICALE_PASSWORD=***           # nur falls auth.mode != none
CHRONOS_TZ=Europe/Berlin
```

---

# 4) Verhaltensregeln (backend-agnostisch)

1. **Einheitliche Verarbeitung:** Jede Collection wird gleich behandelt (kein funktionales Routing). Aliase beeinflussen nur Anzeige/Filter im UI/Logs.

2. **Repair-First:** Kalender-Titel werden zuerst im Quellsystem bereinigt (Keywords entfernt; `ACTION:` & Co. ausgenommen), dann intern angereichert.

3. **Idempotent:** Marker + Signature verhindern Doppel-Patch und doppelte Subtasks.

4. **All-Day & RRULE:** Einheitliche Semantik; Schaltjahr-Policy konfigurierbar.

5. **Warn-Events:** Manuelle `…WARN` bleiben eigenständig; optionales Auto-Warnen kann später zugeschaltet werden (Standard: aus).

6. **Auth schaltbar:** `auth.mode: none` sendet keine Credentials (WireGuard-Setup); Wechsel auf `basic|digest` ohne Codeänderung.

---

# 5) Adapter-Details CalDAV (Radicale)

- **Discovery:** entfällt hier (direkte Collection-URLs in Config).

- **Listen:** `REPORT sync-collection` mit `sync-token`, Fallback `REPORT calendar-query` im Zeitfenster.

- **Lesen:** `GET` der `.ics`.

- **Schreiben:** `PUT` des vollständigen `VEVENT` mit `If-Match: <ETag>`; Konflikt‐Handling: 1× re-fetch & retry, sonst „skip with conflict“.

- **Properties-Mapping:**
  
  - Titel ↔ `SUMMARY`
  
  - Beschreibung ↔ `DESCRIPTION`
  
  - Ganztägig ↔ `DTSTART;VALUE=DATE` (+ `DTEND;VALUE=DATE` = Folgetag)
  
  - Serie ↔ `RRULE` (`RDATE`/`EXDATE` respektieren)
  
  - Ausnahme ↔ `RECURRENCE-ID` (eigener `VEVENT`)
  
  - Marker ↔ `X-CHRONOS-*` (s. oben)

- **Benachrichtigungen:** keine Mails; `ORGANIZER/ATTENDEE` weglassen, sofern nicht explizit genutzt.

---

# 6) Änderungen im Scheduler (klein & klar)

- Iterate **über alle `caldav.calendars`** in stabiler Reihenfolge (Konfigreihenfolge).

- Pro Kalender: `since/until` Fenster anwenden (oder `sync-token` nutzen).

- **Abarbeitung „einmal alles“** pro Lauf, keine Abhängigkeit von Alias/Rolle.

- Pro Event: apply Pipeline in fixierter Order (s. 2.3).

---

# 7) Dokumentations-Updates (präzise)

## 7.1 README – Schnellstart

- **Default Backend:** Radicale/CalDAV.

- **Konfiguration:** Abschnitt „CalDAV“ vor „Google“.

- **Auth:** `auth.mode: none` empfohlen in WireGuard-Netzen; für Public/HTTPS: `basic|digest` + `transport.verify_tls: true`.

- **Kalender hinzufügen:** Blaue Box mit Beispiel-URLs (wie deine drei Collections).

- **Umschalten auf Google:** setze `calendar_source.type: google` und `google.enabled: true` (sonst keine Änderungen nötig).

## 7.2 Betrieb/FAQ

- **Warum sehen Titel sofort hübsch aus?** Repair-First schreibt in den Quellkalender.

- **Was, wenn Read-Only?** Kein Patch, nur interne Anreicherung; Marker `source_readonly` im Log.

- **Wie verhindere ich Doppelungen?** Idempotenz-Marker + Signature (sichtbar in Logs).

## 7.3 Entwicklerhandbuch

- **SourceAdapter-Interface** (Signaturen, Mapping-Tabelle Google↔CalDAV).

- **ETag/If-Match Strategie**, **Konfliktmatrix**.

- **X-CHRONOS Properties** Spezifizierung.

- **Testfälle** (siehe unten).

---

# 8) Telemetrie & Logging (einheitlich)

- Metriken (alle mit Labels `{adapter, calendar_id}`):
  
  - `repair_attempt_total`, `repair_success_total`, `repair_conflict_total{reason}`,
  
  - `readonly_skip_total`, `enrich_applied_total{rule_id}`.

- Logs (strukturierte Felder): `adapter`, `calendar_id`, `event_id|uid`, `etag_before/after`, `rule_id`, `signature`, `elapsed_ms`, `outcome`.

---

# 9) Fehlerbehandlung (konsistent)

- **401/403:** Kalender als read_only behandeln → keine Patches, Enrichment läuft weiter.

- **409/412:** einmaliger Re-Fetch + Retry; danach **Skip** mit `conflict`-Log.

- **Ambiges Datum:** kein Patch (`needs_review`), Enrichment optional.

- **Invalid ICS:** Skip mit `validation_error`-Log.

---

# 10) Abnahme-/Akzeptanzkriterien

1. **Radicale ist Default** – ohne weitere Codeänderungen verarbeitet Chronos deine drei Collections und bereinigt Titel sichtbar (Keywords weg, `ACTION` bleibt).

2. **Umschaltbar** auf Google per `calendar_source.type: google` (keine Logikänderung, gleiche Pipeline).

3. **Alle Kalender identisch** verarbeitet; Alias beeinflusst nicht die Logik.

4. **Repair-First** greift immer vor Enrichment/Commands.

5. **Idempotenz** verhindert Doppel-Patches/-Subtasks über mehrere Sync-Läufe.

6. **Keine E-Mails**/Einladungen ausgelöst.

7. **Schaltjahr-Policy** und All-Day/RRULE sind korrekt.

8. **Metriken/Logs** enthalten `adapter` und `calendar_id`.

---

# 11) Testplan (kompakt, erweiterbar für KI)

- **Adapter-Parität:** Gleiches Roh-Event (Google vs. Radicale) → gleicher bereinigter Titel & RRULE.

- **Drei Collections:** Events in *Automation/Dates/Special* werden gleich behandelt; keine Funktions-Unterschiede.

- **Parsing-Matrix:** `BDAY: … 07.03.1982`, `GEB: … 07.03.`, Trennzeichen `. - /`, fehlendes Jahr, gemischte Groß/Klein.

- **Ambiguität:** `03/07/1982` unter `day_first=true/false`.

- **Serie & Ausnahme:** Master vs. Instanz, keine Bearbeitung vergangener Instanzen.

- **ETag-Konflikt:** paralleler Writer → 1× Retry, dann `conflict`.

- **Read-Only-Kalender:** Patch unterbunden, Enrichment ok.

- **Warnlogik:** `BDAYWARN` −4 Tage korrekt; keine Duplikate.

- **Idempotenz:** unverändertes Event → kein erneuter Patch; Payload-Änderung → genau 1 Patch.

---

# 12) Release-Hinweise (friktionslos)

- **Migration ohne Downtime:**
  
  1. `chronos.yaml` wie oben ausrollen (Radicale Default).
  
  2. Dienst neu starten.
  
  3. Optional: `google.enabled: false` lassen (oder später umschalten).

- **Rollback (nicht gefordert):** nicht vorgesehen; Google bleibt nur optional.

- **Sicherheit:** In WireGuard-Setups `auth.mode: none` zulässig; für externe Zugriffe `basic/digest` + TLS aktivieren.

---


