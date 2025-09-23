# SCHEMA-MISMATCH-ANALYSE: DB vs Code

## DB-VERFÜGBARE FELDER (TemplateDB)
```
✅ id                   (int)
✅ title                (str) → wird als 'name' verwendet
✅ description          (str)
✅ default_time         (str)
✅ usage_count          (int)
✅ created_at           (str)
✅ updated_at           (str)
   all_day              (int) → nicht verwendet im Code
   author               (NoneType)
   calendar_id          (NoneType)
   duration_minutes     (int) → wird als 'default_duration_minutes' erwartet
   tags_json            (str) → nicht direkt verwendet
```

## CODE-ERWARTUNGEN (aus events.py:323-335)
```
✅ id                        → template.id (MATCH)
✅ name                      → template.title (REMAPPED)
✅ description               → template.description (MATCH)
❌ category                  → template.category (FEHLT in DB)
❌ template_data             → template.template_data (FEHLT in DB)
🔄 default_duration_minutes  → template.duration_minutes (RENAME nötig)
❌ default_priority          → template.default_priority (FEHLT in DB)
✅ default_time              → template.default_time (MATCH)
❌ ranking                   → template.ranking (FEHLT in DB)
❌ is_active                 → template.is_active (FEHLT in DB)
✅ usage_count               → template.usage_count (MATCH)
✅ created_at                → template.created_at (MATCH)
✅ updated_at                → template.updated_at (MATCH)
```

## GEFUNDENE PROBLEME

### KRITISCHE FELDER FEHLEN IN DB:
- `category` - wird im Code erwartet
- `template_data` - wird im Code erwartet
- `default_priority` - wird im Code erwartet
- `ranking` - wird im Code erwartet
- `is_active` - wird im Code erwartet

### RENAME ERFORDERLICH:
- `duration_minutes` (DB) → `default_duration_minutes` (Code)

## LÖSUNGSANSÄTZE

### Option 1: Code an DB anpassen (SCHNELL)
- Fehlende Felder mit Fallback-Werten verwenden
- `duration_minutes` korrekt mappen
- `template.category = None` etc.

### Option 2: DB-Schema erweitern (LANGSAM)
- Migration schreiben
- Fehlende Spalten hinzufügen
- Daten migrieren

## EMPFEHLUNG: Option 1 - Code anpassen
Für produktionsreife Funktionalität schnell die Code-Erwartungen an das verfügbare DB-Schema anpassen.