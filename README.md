# Idle Fantasy Save Viewer

Lokaler Web-Viewer für Backups des Android-Spiels **Idle Fantasy**. Parst `fantasyidler_save.json`, zeigt Skills, Inventar, Quests und Kampfstatistiken in einem dunklen Dashboard – inklusive Filter, Item-Gruppierung und Verlaufsvergleich über SQLite.

## Features

- **Dashboard** mit Charakter, Coins, Skills, Inventar, Ausrüstung, Quests und Kampf
- **Inventar** mit Textsuche, Kategorie-Filtern, Sortierung und gruppierten Tabellen
- **SQLite-Verlauf** – mehrere Backups importieren, Snapshots vergleichen, Coins-/Level-Charts
- **Import** per CLI oder Upload im Browser
- **Multi-User** ohne Login – jeder Spieler erhält einen eigenen Viewer über einen geheimen Link
- **Docker** – für Betrieb auf einem Server
- **i18n** – Englisch als Standard/Fallback, Deutsch optional; automatische Browser-Sprache oder manuelle Auswahl in der Sidebar

## Voraussetzungen

- Python 3.11+
- Ein Idle-Fantasy-Backup (`fantasyidler_save.json` vom Spielexport)

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Nutzung

### Server starten und Backup importieren

```powershell
python app.py fantasyidler_save.json
```

Der Browser öffnet sich automatisch unter `http://127.0.0.1:5000/v/local/`.

### Docker (für andere Spieler hosten)

```powershell
docker compose up -d --build
```

Der Viewer ist dann unter `http://localhost:5000` erreichbar:

1. Startseite → **Meinen Viewer erstellen**
2. Persönlichen Link speichern (Bookmark) – **ohne Link sind die Daten nicht wiederherstellbar** (kein Login)
3. Backups im Browser importieren

Daten liegen im Docker-Volume `viewer-data` (`/data/viewers/<id>.db`).

```powershell
# Logs
docker compose logs -f

# Stoppen
docker compose down
```

Umgebungsvariable `DATA_DIR` (Standard in Docker: `/data`) legt den Speicherort fest.

### Weitere Optionen

```powershell
# Nur importieren, kein Server
python app.py --import backup2.json

# Anderen Port, Browser nicht öffnen
python app.py fantasyidler_save.json --port 8080 --no-browser

# Eigene SQLite-Datenbank (Legacy, ein Datei-Modus)
python app.py --db data\meine_history.db fantasyidler_save.json

# Server für Netzwerk/Docker binden
python app.py --host 0.0.0.0 --no-browser
```

### Backups im Browser importieren

Sidebar unten: **Backup importieren** – wählt eine `.json`-Datei. Duplikate (gleicher Datei-Hash) werden übersprungen.

## Multi-User (ohne Login)

Jeder Viewer hat eine eigene SQLite-Datenbank unter `data/viewers/<viewer_id>.db`.

| Route | Beschreibung |
|-------|--------------|
| `GET /` | Startseite – neuen Viewer anlegen |
| `POST /api/viewers` | Erstellt Viewer, liefert `{ viewer_id, url }` |
| `GET /v/<viewer_id>/` | Persönliches Dashboard |
| `GET /v/<viewer_id>/api/...` | API für diesen Viewer |

Die `viewer_id` ist ein zufälliges Token (URL-safe). Wer den Link kennt, hat Zugriff – es gibt kein Passwort und keine Wiederherstellung bei verlorenem Link.

Lokale CLI-Nutzung nutzt standardmäßig den Viewer `local` (`/v/local/`).

## Sprache / i18n

- **Standard:** Englisch (`en`) – auch Fallback, wenn ein Übersetzungsschlüssel fehlt
- **Automatisch:** Sidebar → Sprache → *Automatisch (Browser)* – nutzt `navigator.language` (`de` → Deutsch, sonst Englisch)
- **Manuell:** *English* oder *Deutsch* – Einstellung wird in `localStorage` gespeichert
- Übersetzungsdateien: `static/locales/en.json`, `static/locales/de.json`
- Import-Warnungen vom Server sind auf Englisch codiert (`code` + `params`); die UI übersetzt sie clientseitig

## Projektstruktur

```
idle-fantasy-viewer/
├── app.py              # Flask-Server und CLI
├── viewers.py          # Viewer-IDs und Isolation
├── parser.py           # Save parsen und normalisieren
├── categories.py       # Item-Kategorien (Heuristiken)
├── db.py               # SQLite Snapshots, Diff, Timeline
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── static/
│   ├── i18n.js           # Locale-Laden, t(), Fallback en
│   ├── locales/          # en.json, de.json
│   ├── landing.js        # Startseite
│   └── app.js            # Dashboard-UI
├── templates/          # HTML
└── data/               # viewers/*.db (gitignored)
```

## API

| Endpunkt | Beschreibung |
|----------|--------------|
| `GET /` | Startseite |
| `POST /api/viewers` | Neuen Viewer erstellen |
| `GET /v/<id>/api/snapshot/latest` | Neuester Save des Viewers |
| `GET /v/<id>/api/snapshots` | Alle Snapshots |
| `GET /v/<id>/api/snapshots/<älter>/diff/<neuer>` | Vergleich |
| `GET /v/<id>/api/timeline` | Zeitreihe für Charts |
| `POST /v/<id>/api/import` | JSON-Upload |

## Save-Format

Die Backup-Datei enthält u. a. doppelt JSON-kodierte Felder (`skillLevels`, `inventory`, `flags`, …). Der Parser löst diese automatisch auf.

## Hinweise

- `data/viewers/` speichert pro Spieler eine SQLite-Datei; nicht mit ins Repo committen (steht in `.gitignore`).
- Der Viewer ist ein inoffizielles Hilfstool, nicht mit dem Spiel verbunden.

## Robustheit bei Spiel-Updates

Das Spiel wird aktiv weiterentwickelt – Save-Dateien können neue Felder, Items oder Quest-Typen enthalten. Der Viewer:

- **Parst tolerant:** unbekannte Top-Level-Felder werden in `extensions` durchgereicht und als Info gemeldet
- **Überspringt defekte Einträge** (z. B. einzelne Quests/Sessions) statt abzubrechen
- **Meldet Warnungen** bei fehlenden Kernfeldern, nicht lesbarem JSON in verschachtelten Feldern oder ungültigen Zahlen
- **Blockiert den Import** nur bei schwerwiegenden Problemen (keine gültige JSON-Datei, leeres Objekt)

Nach dem Import erscheinen Fehler und Warnungen als Banner im Dashboard; in der CLI unter stderr.

## Lizenz

Privates Projekt – Nutzung auf eigene Verantwortung.
