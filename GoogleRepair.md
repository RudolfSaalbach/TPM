# Reality-Marker

**Spec/Design** — concise, implementation-ready requirements; code-free (except minimal YAML schema).

# Chronos “Calendar Repairer” — Requirements

## Goal

Allow users to enter rough, keyword-prefixed events anywhere (Google Calendar). Chronos repairs them **first** (write-back to Google so titles look nice), then enriches and persists them. Keywords disappear from visible titles (except reserved like `ACTION:`). Identical **German and English keywords** trigger the same rules.

---

## Scope

- Supported types: **Birthdays**, **Birthday warnings**, **Memorials (death anniversaries)**, **Anniversaries (generic)**, with matching DE/EN keywords.

- Repairer runs **before** any other Chronos processing.

- Google Calendar is the source of truth; Chronos writes back via patch if permitted.

---

## Pipeline Order (must)

`UndefinedGuard` → **CalendarRepairer (Write-Back)** → `KeywordEnricher` → `command_handler` → remaining plugins.

- **UndefinedGuard:** catches malformed prefixes (case, colon, typos).

- **CalendarRepairer:** parses, formats, and patches Google events; sets idempotency markers.

- **KeywordEnricher:** adds `event_type`, `tags`, `sub_tasks`, links, etc.

- **command_handler:** handles `ACTION:` and other commands (never rewritten).

---

## Keywords (EN ⇄ DE)

- **Birthday:** `BDAY`, `BIRTHDAY` ⇄ `GEB`, `GEBURTSTAG`

- **Birthday warning:** `BDAYWARN`, `BIRTHDAYWARN` ⇄ `GEBWARN`, `GEBURTSTAGWARN`

- **Memorial (death):** `RIP`, `DEATH`, `MEMORIAL` ⇄ `RIP`, `TOD`, `GEDENKEN`

- **Memorial warning:** `RIPWARN`, `MEMORIALWARN` ⇄ `RIPWARN`, `TODWARN`, `GEDENKWARN`

- **Anniversary (generic):** `ANNIV`, `ANNIVERSARY` ⇄ `JUBI`, `JUBILÄUM`

- **Anniversary warning:** `ANNIVWARN`, `ANNIVERSARYWARN` ⇄ `JUBIWARN`, `JUBILÄUMWARN`

- **Reserved (never rewritten):** `ACTION`, `MEETING`, `CALL` (configurable)

> Case-insensitive; exact match before colon.

---

## Input Pattern (user entry)

```
<KEYWORD> : <payload>
payload := free text with an optional date
date formats accepted (configurable): dd.mm.yyyy | dd.mm. | dd-mm-yyyy | dd/mm/yyyy
```

### Parsing extraction

- **name/label**: greedy until a trailing date token.

- **date**: day-first by default; year optional.

- Ambiguous date (e.g., `03/07/1982`) obeys `day_first`; if `strict_when_ambiguous = true`, do not patch, mark `needs_review`.

---

## Write-Back (Google Calendar)

- API: `events.patch` with `If-Match: <etag>` and `sendUpdates=none`.

- Edit **series master** if keyword is on master; edit **instance** if on instance.

- Never edit past instances (`start < today`) unless explicitly allowed.

- On insufficient permissions (read-only): **skip patch**, continue internal enrich, tag `source_readonly`.

### Idempotency markers (extendedProperties.private)

```
chronos.cleaned = "v1"
chronos.rule_id = "<rule-id>"
chronos.signature = SHA256(<original_summary|start|recurrence>)
chronos.original_summary = "<original text>"
chronos.payload = JSON { name, date_iso?, locale }
```

- Patch only if `chronos.cleaned != "v1"` **or** signature changed.

---

## Title Templates (short, English)

- **Birthday:** `🎉 Birthday: {name} ({date_display}){age_suffix}`

- **Birthday warn:** `⏰ {name}'s birthday in {warn_abs_days} days ({date_day_month})`

- **Memorial:** `🕯️ In memory of {name} († {date_display}){years_since_suffix}`

- **Anniversary:** `🎖️ {label}: {name_or_label} since {date_display}{years_since_suffix}`

> `{age_suffix}` e.g., `– turns {age}.` only if year present.  
> `{years_since_suffix}` e.g., `– {years_since}th.` only if year present.  
> Keep titles English; German keywords still map to these English titles (by requirement).

---

## Recurrence / Time

- All supported types default **All-day** in calendar timezone (e.g., Europe/Berlin).

- RRULE: `FREQ=YEARLY;BYMONTH=<m>;BYMONTHDAY=<d>`.

- Leap-day policy configurable: `FEB_28` or `MAR_01`.

---

## Warning Events

- Support both **manual** `…WARN` entries (treated like primary types) **and** optional **auto-generated** warnings from a primary event.

- Auto-warning settings: offset (e.g., −4 days), linkage to source event, duplicate protection.

- Deleting a primary event deletes only **auto-generated** warnings (not manual ones).

---

## Configuration Schema (YAML skeleton)

```yaml
version: 1
pipeline:
  order: ["UndefinedGuard","CalendarRepairer","KeywordEnricher","command_handler"]
calendar_repairer:
  enabled: true
  reserved_prefixes: ["ACTION","MEETING","CALL"]
  readonly_fallback: "internal_enrich_only"
  google_patch:
    send_updates: "none"
    use_if_match: true
  idempotency:
    marker_key: "chronos.cleaned"
    marker_value: "v1"
    signature_fields: ["original_summary","start","recurrence"]
  series_policy:
    edit_master_if_keyword_on_master: true
    edit_instance_if_keyword_on_instance: true
    do_not_edit_past_instances: true
parsing:
  accept_date_separators: [".","-","/"]
  day_first: true
  year_optional: true
  strict_when_ambiguous: true
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
auto_warning:
  enabled: false
  offset_days: -4
  link_bi_directional: true
```

### Provided placeholders

`{name}`, `{label}`, `{name_or_label}`, `{date_display}`, `{date_day_month}`, `{date_iso}`, `{age}`, `{years_since}`, `{age_suffix}`, `{years_since_suffix}`, `{warn_abs_days}`.

---

## Functional Rules

1. **Repair-first:** CalendarRepairer must execute and succeed/skip before any enrichment or command handling.

2. **Keyword removal:** After repair, visible titles **contain no keyword prefixes** (except `reserved_prefixes`).

3. **Locale:** Titles remain in **English**; parsing accepts both EN/DE keywords.

4. **Consistency:** Manual `…WARN` events remain independent; auto-generated warnings do not duplicate manual ones.

5. **Deletion semantics:** Deleting a primary event deletes only auto-generated warnings linked to it.

---

## Non-Functional Requirements

- **Idempotent:** Re-syncs must not duplicate subtasks/tags or re-patch unchanged events.

- **No spam:** Google updates must not notify attendees (`sendUpdates=none`).

- **Performance:** Repair pass ≤ 5ms/event average on 10k events; batch-friendly.

- **Observability:** Metrics and structured logs.

### Metrics (examples)

- `repair_attempt_total{rule_id}`

- `repair_success_total{rule_id}`

- `repair_conflict_total{reason}`

- `readonly_skip_total`

- `enrich_applied_total{rule_id}`

### Logs (context)

`calendarId, eventId, rule_id, etag_before/after, signature_hash, elapsed_ms, outcome`.

---

## Error Handling

- **Ambiguous parse:** do not patch; mark `needs_review`; keep original title.

- **ETag 412:** re-fetch once; if content diverged, skip and log conflict.

- **Read-only:** skip patch; continue internal enrich; tag `source_readonly`.

- **Template error:** disable rule at runtime; log and alert.

---

## Acceptance Criteria

1. CalendarRepairer runs before all other plugins and removes keyword prefixes from titles (except reserved).

2. Repaired titles match templates; payload (name/date) preserved and correctly formatted.

3. RRULE and all-day behavior correct; leap-day policy honored.

4. Idempotency markers prevent double patching and duplicate enrichments.

5. Manual vs. auto-warning logic behaves as specified; no duplicates.

6. No attendee emails generated during repair.

7. Read-only calendars fall back without errors and with internal enrichment.

8. Metrics/logs expose success, skip, conflict, and readonly counts.

---

## Test Outline

- **Parsing matrix:** spacing, different separators, missing year, emojis, mixed case, German/English keywords.

- **Ambiguity:** `03/07/1982` under `day_first=true/false`.

- **Series:** master vs. instance edits; past-instance protection.

- **Idempotency:** unchanged event → no second patch; changed payload → single patch.

- **Warn offsets:** −4/−3/−7 day scenarios; manual + auto coexistence.

- **Read-only:** verify fallback and tagging.

- **Reserved prefixes:** `ACTION:` preserved.

---

.
