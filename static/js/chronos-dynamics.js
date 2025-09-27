/*
 * Chronos Dynamics - v1.0
 * Minimalinvasive, leichtgewichtige Skripte für dynamische UI-Anpassungen.
 * - Temporal Ambiance: Passt das Farbthema an die Tageszeit an.
 * - Generative Calendar Hues: Erzeugt prozedurale Farben für Kalender.
*/

document.addEventListener('DOMContentLoaded', () => {
    applyTemporalTheme();
    applyGenerativeCalendarColors();
});

/**
 * Passt das Farbschema der Benutzeroberfläche an die lokale Tageszeit des Benutzers an.
 */
function applyTemporalTheme() {
    const body = document.body;
    if (!body) return;

    const currentHour = new Date().getHours();
    let themeClass = 'theme-day'; // Standard

    if (currentHour >= 5 && currentHour < 9) {
        themeClass = 'theme-morning';
    } else if (currentHour >= 9 && currentHour < 17) {
        themeClass = 'theme-day';
    } else if (currentHour >= 17 && currentHour < 22) {
        themeClass = 'theme-evening';
    } else {
        themeClass = 'theme-night';
    }

    body.classList.remove('theme-morning', 'theme-day', 'theme-evening', 'theme-night');
    body.classList.add(themeClass);
}

/**
 * Findet alle Event-Karten und weist ihnen eine prozedural generierte Farbe zu,
 * die auf dem Kalendernamen basiert. Der Kalendername wird aus einem
 * `data-calendar-name`-Attribut auf dem .event-card Element gelesen.
 */
function applyGenerativeCalendarColors() {
    const eventCards = document.querySelectorAll('.event-card');
    
    eventCards.forEach(card => {
        // Das Backend muss das Attribut 'data-calendar-name' auf jeder Event-Karte rendern.
        // Beispiel: <div class="event-card" data-calendar-name="Projekt Chronos-API">...</div>
        const calendarName = card.dataset.calendarName;

        if (calendarName) {
            const color = stringToHslColor(calendarName);
            // Setzt die CSS-Variable '--cal-color', die vom Stylesheet verwendet wird.
            card.style.setProperty('--cal-color', color);
        }
    });
}

/**
 * Wandelt einen beliebigen String (z.B. einen Kalendernamen) in eine deterministische,
 * ästhetisch ansprechende HSL-Farbe um.
 * @param {string} str - Die Eingabezeichenkette.
 * @param {number} saturation - Die Sättigung der Farbe (0-100).
 * @param {number} lightness - Die Helligkeit der Farbe (0-100).
 * @returns {string} Eine HSL-Farbzeichenkette, z.B. "hsl(195, 70%, 55%)".
 */
function stringToHslColor(str, saturation = 70, lightness = 55) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    const hue = hash % 360;
    return `hsl(${hue}, ${saturation}%, ${lightness}%)`;
}