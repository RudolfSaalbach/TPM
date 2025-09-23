# DATABASE FIELD MAPPING RULES

## FUNDAMENTALE REGEL
**Niemals blind DB-Felder verwenden - immer Typ + Constraint Validierung!**

## SYSTEMATISCHES VORGEHEN

### 1. FELD-ANALYSE (vor Code-Änderung)
```python
# Immer zuerst analysieren:
db_field_name = "tags_json"
db_field_type = "VARCHAR(500)"  # String
api_expected_type = "List[str]"  # Liste
conversion_needed = True  # JSON.parse erforderlich
```

### 2. TYP-MAPPING TABELLE
| DB-Typ | Python-Typ | Konvertierung | Validierung |
|--------|-------------|---------------|-------------|
| VARCHAR(n) | str | direkter Zugriff | len() <= n |
| TEXT | str | direkter Zugriff | optional maxlen |
| INTEGER | int | direkter Zugriff | range prüfen |
| JSON/TEXT | List/Dict | json.loads() | JSON-Validierung |
| BOOLEAN/INT | bool | bool(value) | 0/1 erwarten |

### 3. SICHERE FELD-ZUGRIFFS-PATTERN
```python
# FALSCH - blind getattr()
value = getattr(obj, 'field', 'fallback')

# RICHTIG - type-safe conversion
def safe_get_json_list(obj, field_name, fallback=None):
    raw_value = getattr(obj, field_name, None)
    if not raw_value:
        return fallback or []
    try:
        return json.loads(raw_value)
    except (json.JSONDecodeError, TypeError):
        return fallback or []

# Verwendung:
tags = safe_get_json_list(template, 'tags_json', [])
```

### 4. CONSTRAINT-VALIDIERUNG
```python
# String-Längen prüfen
def validate_string_field(value, max_length, field_name):
    if len(value) > max_length:
        raise ValueError(f"{field_name} too long: {len(value)} > {max_length}")
    return value

# Nullable vs Required
def safe_get_required(obj, field_name, field_type):
    value = getattr(obj, field_name, None)
    if value is None:
        raise ValueError(f"Required field {field_name} is None")
    return field_type(value)
```

### 5. ANTI-PATTERNS VERMEIDEN
❌ `getattr(obj, 'field', 'fallback')` ohne Typprüfung
❌ Direkte Zugriffe ohne Constraint-Validierung
❌ JSON-Strings als Listen behandeln
❌ INT-Felder als BOOL ohne Konvertierung

✅ Type-safe Konvertierungsfunktionen
✅ Constraint-Validierung vor Verwendung
✅ Explizite Fehlerbehandlung
✅ Dokumentierte Typ-Mappings

## IMPLEMENTIERUNGS-CHECKLISTE
1. [ ] DB-Schema analysieren (Feldname + Typ + Constraints)
2. [ ] API-Schema analysieren (erwarteter Typ)
3. [ ] Konvertierungs-Funktion schreiben
4. [ ] Constraint-Validierung implementieren
5. [ ] Error-Handling für Type-Mismatches
6. [ ] Tests für alle Konvertierungen

**MERKSATZ: Erst Schema verstehen, dann Code anpassen - nie umgekehrt!**