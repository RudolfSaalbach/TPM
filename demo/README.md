# Demo Scripts für Chronos Engine

Dieser Ordner enthält Demo-Skripte und Hilfsprogramme für die Chronos Engine.

## Scripts

### `create_test_events.py`
Erstellt Test-Events in allen konfigurierten Radicale-Kalendern.

**Verwendung:**
```bash
cd /path/to/chronos-engine
python demo/create_test_events.py
```

**Was das Script tut:**
- Lädt die Konfiguration aus `config/chronos.yaml`
- Identifiziert alle konfigurierten CalDAV/Radicale-Kalender
- Erstellt für jeden Kalender einen spezifischen Test-Event:
  - **Automation**: 🤖 System Check (09:00-10:00, morgen)
  - **Dates**: 📅 Wichtiger Termin (14:30-15:30, übermorgen)
  - **Special**: ⭐ Besonderes Event (18:00-19:00, in 3 Tagen)

**Voraussetzungen:**
- Radicale-Server muss erreichbar sein
- Konfiguration in `config/chronos.yaml` muss korrekt sein
- `RADICALE_PASSWORD` Umgebungsvariable muss gesetzt sein

## Installation auf aktuellem System beibehalten

Die Installation bleibt auf dem aktuellen Rechner bestehen. Diese Demo-Scripts nutzen die bestehende Infrastruktur und Konfiguration.