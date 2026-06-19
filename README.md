# Idle Fantasy Save Viewer

A web viewer for backups of the Android game **Idle Fantasy**. Parses `fantasyidler_save.json` and displays skills, inventory, quests, and combat stats in a dark dashboard — with filters, item grouping, and history comparison via SQLite.

## Features

- **Dashboard** with character, coins, skills, inventory, equipment, quests, and combat
- **Inventory** with text search, category filters, sorting, and grouped tables
- **SQLite history** — import multiple backups, compare snapshots, coins/level charts
- **Import** via CLI or browser upload
- **Multi-user** without login — each player gets their own viewer via a secret link
- **Docker** — ready to run behind nginx Proxy Manager
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

Runs behind **nginx Proxy Manager**. By default the container publishes port **5000** on the host so NPM can forward to `http://<docker-host>:5000` (e.g. `http://172.16.10.20:5000`).

```powershell
docker compose up -d --build
```

1. In NPM: Proxy Host → `http://<docker-host-ip>:5000`, enable SSL, Force SSL.
2. Open your public URL → **Create my viewer**
3. Save the personal link (bookmark) — **without the link, data cannot be recovered** (no login)
4. Import backups in the browser

**Alternative:** If NPM runs on the **same Docker host**, you can remove the `ports` mapping, attach the `viewer` service to the NPM network (see `docker-compose.yml` comments), and proxy to `http://viewer:5000` instead.

Data is stored in the Docker volume `viewer-data` (`/data/viewers/<id>.db`).

```powershell
# Logs
docker compose logs -f

# Stop
docker compose down
```

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

Local CLI usage defaults to the `local` viewer (`/v/local/`). In Docker/production, `/v/local/` is disabled (`DISABLE_LOCAL_VIEWER=1`).

## Security

The app uses **secret-link access** (no accounts). Suitable for sharing with trusted players when deployed behind HTTPS.

### Built-in protections

| Measure | Default (Docker) |
|---------|------------------|
| Upload size limit | 10 MB (`MAX_UPLOAD_MB`) |
| Viewer creation rate limit | 5 / minute per IP |
| Import rate limit | 20 / hour per IP |
| Path-based import | **Removed** (upload only) |
| `/v/local/` in production | Disabled |
| Reverse-proxy headers | `TRUST_PROXY=1` (ProxyFix) |
| HTTPS links | `PREFERRED_URL_SCHEME=https` |
| Security headers | CSP, `X-Frame-Options`, `nosniff`, `Referrer-Policy` |
| Chart.js | Bundled locally (no CDN) |
| Container user | Non-root (`appuser`, uid 1000) |

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_DIR` | `./data` | SQLite and upload storage |
| `TRUST_PROXY` | `1` in Docker | Trust `X-Forwarded-*` from nginx |
| `PREFERRED_URL_SCHEME` | `https` in Docker | Scheme for generated viewer URLs |
| `DISABLE_LOCAL_VIEWER` | `1` in Docker | Block predictable `/v/local/` |
| `MAX_UPLOAD_MB` | `10` | Max upload body size |
| `RATE_LIMIT_VIEWER_CREATE` | `5 per minute` | Limit for `POST /api/viewers` |
| `RATE_LIMIT_IMPORT` | `20 per hour` | Limit for `POST .../import` |

### nginx Proxy Manager

Recommended NPM settings:

- **SSL** with Force SSL
- **Block Common Exploits** enabled
- Forward headers: `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Real-IP` (default)
- Optional **Advanced** config:

```nginx
client_max_body_size 10m;

limit_req_zone $binary_remote_addr zone=viewer_create:10m rate=5r/m;
limit_req_zone $binary_remote_addr zone=viewer_api:10m rate=30r/s;

location /api/viewers {
    limit_req zone=viewer_create burst=2 nodelay;
    proxy_pass http://viewer:5000;
}

location / {
    limit_req zone=viewer_api burst=50 nodelay;
    proxy_pass http://viewer:5000;
}
```

Bind port `5000` only on your internal network (firewall), not on the public internet — NPM terminates TLS and proxies internally.

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
├── security.py         # Rate limits, headers, proxy trust
├── viewers.py          # Viewer IDs and isolation
├── parser.py           # Parse and normalize saves
├── categories.py       # Item categories (heuristics)
├── db.py               # SQLite snapshots, diff, timeline
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── static/
│   ├── vendor/           # chart.umd.min.js (bundled)
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
| `POST /api/viewers` | Create a new viewer (rate limited) |
| `GET /v/<id>/api/snapshot/latest` | Latest save for the viewer |
| `GET /v/<id>/api/snapshots` | All snapshots |
| `GET /v/<id>/api/snapshots/<older>/diff/<newer>` | Compare two snapshots |
| `GET /v/<id>/api/timeline` | Time series for charts |
| `POST /v/<id>/api/import` | JSON file upload (`.json` only, rate limited) |

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
