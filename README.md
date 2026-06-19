# Idle Fantasy Save Viewer

Lokaler Web-Viewer für Backups des Android-Spiels **Idle Fantasy**. Parst `fantasyidler_save.json`, zeigt Skills, Inventar, Quests und Kampfstatistiken in einem dunklen Dashboard – inklusive Filter, Item-Gruppierung und Verlaufsvergleich über SQLite.

## Features

- **Dashboard** mit Charakter, Coins, Skills, Inventar, Ausrüstung, Quests und Kampf
- **Inventar** mit Textsuche, Kategorie-Filtern, Sortierung und gruppierten Tabellen
- **SQLite-Verlauf** – mehrere Backups importieren, Snapshots vergleichen, Coins-/Level-Charts
- **Import** per CLI oder Upload im Browser
- Läuft nur lokal (`127.0.0.1`)

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

Der Browser öffnet sich automatisch unter `http://127.0.0.1:5000`.

### Weitere Optionen

```powershell
# Nur importieren, kein Server
python app.py --import backup2.json

# Anderen Port, Browser nicht öffnen
python app.py fantasyidler_save.json --port 8080 --no-browser

# Eigene SQLite-Datenbank
python app.py --db data\meine_history.db fantasyidler_save.json
```

### Backups im Browser importieren

Im Tab **Inventar** (Sidebar unten): **Backup importieren** – wählt eine `.json`-Datei. Duplikate (gleicher Datei-Hash) werden übersprungen.

## Projektstruktur

```
idle-fantasy-viewer/
├── app.py              # Flask-Server und CLI
├── parser.py           # Save parsen und normalisieren
├── categories.py       # Item-Kategorien (Heuristiken)
├── db.py               # SQLite Snapshots, Diff, Timeline
├── requirements.txt
├── static/             # CSS und JavaScript
├── templates/          # HTML
└── data/               # history.db (wird angelegt, gitignored)
```

## API (lokal)

| Endpunkt | Beschreibung |
|----------|--------------|
| `GET /` | Dashboard |
| `GET /api/snapshot/latest` | Neuester normalisierter Save |
| `GET /api/snapshots` | Alle Snapshots |
| `GET /api/snapshots/<älter>/diff/<neuer>` | Vergleich zweier Backups |
| `GET /api/timeline` | Zeitreihe für Charts |
| `POST /api/import` | JSON-Upload oder `{"path": "..."}` |

## Save-Format

Die Backup-Datei enthält u. a. doppelt JSON-kodierte Felder (`skillLevels`, `inventory`, `flags`, …). Der Parser löst diese automatisch auf.

## Hinweise

- `data/history.db` speichert importierte Snapshots lokal; nicht mit ins Repo committen (steht in `.gitignore`).
- Der Viewer ist ein inoffizielles Hilfstool, nicht mit dem Spiel verbunden.

## Lizenz

Privates Projekt – Nutzung auf eigene Verantwortung.
