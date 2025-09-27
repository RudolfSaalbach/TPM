Hier ist die To-do-Liste. Keine Beschönigungen, keine Ausreden. Das sind die Anweisungen, um aus dem Prototypen eine arbeitsfähige Plattform zu machen.

---

### **Qualitäts-Manifest: To-do-Liste für Chronos Engine v2.2**

**Ziel:** Herstellung der grundlegenden Arbeitsfähigkeit und Beseitigung der Diskrepanz zwischen Anspruch und Realität. Die Fassade wird abgerissen; was bleibt, muss zu 100% funktionieren.

#### **Phase 1: UI/API-Integrität wiederherstellen (Höchste Priorität)**

Das Vorspiegeln nicht existenter Funktionen stoppt jetzt. Jeder sichtbare Button muss eine reale, abgeschlossene Funktion im Backend auslösen oder er wird entfernt.

1. **Stub-API-Endpunkte im Frontend neutralisieren:**
   
   - **Aktion:** Entferne den "Productivity"-Tab und alle zugehörigen UI-Elemente aus `templates/analytics.html` und `dashboard.html`.
   
   - **Grund:** Der Endpunkt `/api/v1/analytics/productivity` ist ein Stub in `src/core/analytics_engine.py` und liefert keine echten Daten. Die UI lügt den Benutzer an.

2. **Event-Daten-Portabilität durchkontaktieren:**
   
   - **Aktion:** Implementiere im Frontend unter `static/js/` eine sichtbare Funktion (z.B. einen Button in den Einstellungen), die die API-Endpunkte `GET /api/v1/events/export` und `POST /api/v1/events/import` tatsächlich aufruft und dem Benutzer den Export als JSON-Datei anbietet bzw. einen Upload ermöglicht.
   
   - **Grund:** Das Backend hat diese starke Funktion, die UI ignoriert sie vollständig. Die Funktion ist für den Benutzer unsichtbar und damit wertlos.

3. **Backend-Wechsel im UI abbilden:**
   
   - **Aktion:** Füge in den Einstellungen (`templates/settings.html`) eine Sektion hinzu, die den Status des aktuellen Backends von `GET /caldav/backend/info` anzeigt. Implementiere einen Button, der `POST /caldav/backend/switch` auslöst, um aktiv zwischen CalDAV und Google Kalender zu wechseln.
   
   - **Grund:** Die API kann es, die Dokumentation bewirbt es, aber die UI bietet keine Kontrolle darüber. Das ist eine Kernfunktion, die versteckt bleibt.

4. **Manuelle Synchronisation zugänglich machen:**
   
   - **Aktion:** Der Button "Sync" im Dashboard muss pro konfiguriertem Kalender den Endpunkt `POST /caldav/calendars/{id}/sync` aufrufen. Gib dem Benutzer visuelles Feedback (Spinner, dann Haken/Kreuz) über Erfolg oder Misserfolg des Sync-Vorgangs.
   
   - **Grund:** Ein "Sync"-Button, der nichts tut oder einen globalen Sync ohne spezifisches Feedback auslöst, ist unbrauchbar.

#### **Phase 2: API-Konsistenz und -Struktur erzwingen**

Die aktuelle API ist ein organisch gewachsener Flickenteppich. Das wird jetzt vereinheitlicht.

1. **API-Präfixe konsolidieren:**
   
   - **Aktion:** Führe *alle* Endpunkte unter dem Präfix `/api/v2/` zusammen. Die Routen aus `src/api/caldav.py` werden nach `/api/v2/caldav/` verschoben. Die alten Pfade (`/caldav/`, `/api/v1/`) werden über `deprecation.py` für eine Übergangszeit weitergeleitet, aber intern wird nur noch die `v2`-Struktur verwendet.
   
   - **Grund:** Zwei konkurrierende Top-Level-Pfade (`/api` und `/caldav`) für eine einzige Anwendung sind schlechtes API-Design und widersprechen der "Unified"-Philosophie der Version 2.2.

2. **Health-Checks logisch strukturieren:**
   
   - **Aktion:** Der Endpunkt `/api/v1/sync/health` wird zu `/api/v2/health/scheduler`. Der Endpunkt `/health` wird zu `/api/v2/health/system`.
   
   - **Grund:** Health-Checks sind API-Ressourcen und gehören unter das API-Präfix. Die aktuelle Struktur ist inkonsistent.

#### **Phase 3: Frontend-Robustheit sicherstellen**

Das Frontend muss von einem Proof-of-Concept zu einem zuverlässigen Client werden.

1. **Zustandsverwaltung implementieren:**
   
   - **Aktion:** Erweitere den `StateManager.js` (`static/js/services/StateManager.js`) zu einer echten "Single Source of Truth". Daten (Events, Kalenderliste etc.) werden dort zentral gehalten. UI-Komponenten abonnieren Änderungen, anstatt bei jeder Aktion einen kompletten Refresh auszulösen.
   
   - **Grund:** Das ständige Neuladen der Seite bei Aktionen ist inakzeptabel und langsam. Es zeigt, dass dem Frontend eine saubere Architektur fehlt.

2. **Fehlerbehandlung im Client umsetzen:**
   
   - **Aktion:** Jeder API-Aufruf im `APIService.js` muss `try...catch`-Blöcke haben. API-Fehler (4xx, 5xx) müssen abgefangen und dem Benutzer in einer verständlichen Form (z.B. als Toast-Nachricht) angezeigt werden.
   
   - **Grund:** Wenn die API einen Fehler wirft, bricht aktuell die JavaScript-Ausführung oder es passiert einfach nichts. Der Benutzer bleibt im Unklaren. Das ist unprofessionell.

---

Diese Liste ist nicht verhandelbar. Abarbeiten, committen, fertigstellen.
