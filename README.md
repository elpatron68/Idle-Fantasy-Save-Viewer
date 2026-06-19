# Idle Fantasy Save Viewer

A web viewer for backups of the Android game **Idle Fantasy**. Parses `fantasyidler_save.json` and displays skills, inventory, quests, and combat stats in a dark dashboard — with filters, item grouping, and history comparison via SQLite.

## Features

- **Dashboard** with character, coins, skills, inventory, equipment, quests, and combat
- **Inventory** with text search, category filters, sorting, and grouped tables
- **SQLite history** — import multiple backups, compare snapshots, coins/level charts
- **Import** via CLI or browser upload
- **Multi-user** without login — each player gets their own viewer via a secret link
- **Docker** — ready to run on a server
- **i18n** — English as default/fallback, German optional; automatic browser language or manual selection in the sidebar

## Requirements

- Python 3.11+
- An Idle Fantasy backup (`fantasyidler_save.json` from the in-game export)

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Usage

### Start server and import a backup

```powershell
python app.py fantasyidler_save.json
```

The browser opens automatically at `http://127.0.0.1:5000/v/local/`.

### Docker (host for other players)

```powershell
docker compose up -d --build
```

The viewer is then available at `http://localhost:5000`:

1. Landing page → **Create my viewer**
2. Save the personal link (bookmark) — **without the link, data cannot be recovered** (no login)
3. Import backups in the browser

Data is stored in the Docker volume `viewer-data` (`/data/viewers/<id>.db`).

```powershell
# Logs
docker compose logs -f

# Stop
docker compose down
```

The `DATA_DIR` environment variable (default in Docker: `/data`) sets the storage location.

### More options

```powershell
# Import only, no server
python app.py --import backup2.json

# Different port, don't open browser
python app.py fantasyidler_save.json --port 8080 --no-browser

# Custom SQLite database (legacy single-file mode)
python app.py --db data\my_history.db fantasyidler_save.json

# Bind server for network/Docker
python app.py --host 0.0.0.0 --no-browser
```

### Import backups in the browser

Sidebar at the bottom: **Import backup** — selects a `.json` file. Duplicates (same file hash) are skipped.

## Multi-user (no login)

Each viewer has its own SQLite database at `data/viewers/<viewer_id>.db`.

| Route | Description |
|-------|-------------|
| `GET /` | Landing page — create a new viewer |
| `POST /api/viewers` | Creates a viewer, returns `{ viewer_id, url }` |
| `GET /v/<viewer_id>/` | Personal dashboard |
| `GET /v/<viewer_id>/api/...` | API for this viewer |

The `viewer_id` is a random URL-safe token. Anyone with the link has access — there is no password and no recovery if the link is lost.

Local CLI usage defaults to the `local` viewer (`/v/local/`).

## Language / i18n

- **Default:** English (`en`) — also the fallback when a translation key is missing
- **Automatic:** Sidebar → Language → *Auto (browser)* — uses `navigator.language` (`de` → German, otherwise English)
- **Manual:** *English* or *Deutsch* — preference is stored in `localStorage`
- Translation files: `static/locales/en.json`, `static/locales/de.json`
- Import warnings from the server are coded in English (`code` + `params`); the UI translates them client-side

## Project structure

```
idle-fantasy-viewer/
├── app.py              # Flask server and CLI
├── viewers.py          # Viewer IDs and isolation
├── parser.py           # Parse and normalize saves
├── categories.py       # Item categories (heuristics)
├── db.py               # SQLite snapshots, diff, timeline
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── static/
│   ├── i18n.js           # Locale loading, t(), en fallback
│   ├── locales/          # en.json, de.json
│   ├── landing.js        # Landing page
│   └── app.js            # Dashboard UI
├── templates/          # HTML
└── data/               # viewers/*.db (gitignored)
```

## API

| Endpoint | Description |
|----------|-------------|
| `GET /` | Landing page |
| `POST /api/viewers` | Create a new viewer |
| `GET /v/<id>/api/snapshot/latest` | Latest save for the viewer |
| `GET /v/<id>/api/snapshots` | All snapshots |
| `GET /v/<id>/api/snapshots/<older>/diff/<newer>` | Compare two snapshots |
| `GET /v/<id>/api/timeline` | Time series for charts |
| `POST /v/<id>/api/import` | JSON upload |

## Save format

The backup file contains doubly JSON-encoded fields (`skillLevels`, `inventory`, `flags`, …). The parser decodes these automatically.

## Notes

- `data/viewers/` stores one SQLite file per player; do not commit to the repo (listed in `.gitignore`).
- This viewer is an unofficial helper tool, not affiliated with the game.

## Robustness for game updates

The game is actively developed — save files may contain new fields, items, or quest types. The viewer:

- **Parses tolerantly:** unknown top-level fields are passed through in `extensions` and reported as info
- **Skips broken entries** (e.g. individual quests/sessions) instead of aborting
- **Reports warnings** for missing core fields, unreadable JSON in nested fields, or invalid numbers
- **Blocks import** only for serious issues (invalid JSON file, empty object)

After import, errors and warnings appear as a banner in the dashboard; in the CLI on stderr.

## License

Private project — use at your own risk.
