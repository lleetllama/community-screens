# Community Screens

Self-hosted digital signage for community activity schedules. Manage events from a phone or computer, then open a display URL on each TV. Built with Flask, SQLite, and plain JavaScript/CSS.

## Features

- Separate display URLs for different rooms or screens
- Assign each activity to one display or all displays
- One-time events and recurring weekly schedules
- Event titles, start/end times, locations, notes, and an enabled toggle
- Per-display name, subtitle, banner heading, empty schedule message, welcome footer, and color theme
- Live clock with seconds in the configured timezone
- Schedule and display text updates every 30 seconds
- Event text and spacing shrink automatically as more rows are added
- Password-protected schedule editor with CSRF protection
- Automatic database creation and starter displays on first run

## Quick start with Docker

Use a Docker-compatible computer or a Raspberry Pi running a 64-bit OS. Install Docker Engine and the Compose plugin before starting.

```sh
git clone https://github.com/lleetllama/community-screens.git
cd community-screens
cp .env.example .env
```

Edit `.env` and replace both secret placeholders. Generate a random secret with:

```sh
openssl rand -hex 32
```

Start the app:

```sh
docker compose up -d --build
```

Open `http://DEVICE_IP:8080` to see the displays, or `http://DEVICE_IP:8080/admin` to manage them. Sign in with `ADMIN_PASSWORD`.

On each TV, open a display such as `http://DEVICE_IP:8080/display/lobby` and enable fullscreen or kiosk mode. Multiple TVs can use the same URL.

### Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `SECRET_KEY` | Secret for signing admin sessions; set a long random value | Required by Compose |
| `ADMIN_PASSWORD` | Password for the schedule editor | Required by Compose |
| `TZ` | Facility timezone for the clock and event dates | `America/New_York` |
| `DATA_DIR` | SQLite storage directory | `./data` locally; `/app/data` in Docker |

Compose reads `.env` and passes the settings to the container. Keep the host clock accurate. After changing `.env`, recreate the service:

```sh
docker compose up -d --force-recreate
```

## First run and storage

The app creates its data directory and `dashboard.sqlite3` automatically at startup. A new database is seeded with three displays:

| Display | URL |
| --- | --- |
| Main Lobby | `/display/lobby` |
| Activities | `/display/activities` |
| Dining | `/display/dining` |

Activities start empty. Restarts preserve saved displays and activities, and startup adds missing schema fields to existing databases. Starter displays are added when the displays table is empty.

Docker stores the database in the persistent `dashboard_data` Compose volume. `.gitignore` and `.dockerignore` exclude local environment files, runtime data, SQLite databases and journals, Python caches, and the virtual environment. `.env.example` is included as the configuration template.

## Manage schedules

1. Open **Manage** and choose **Add activity**.
2. Enter a title, start time, and optional end time, location, and notes.
3. Choose a display or **All displays**.
4. Select a specific date or repeat weekly on selected days.
5. Save the activity. Uncheck **Enabled** to hide it without deleting it.

Under **Displays**, add or edit screens and customize their text and theme. Leaving **Banner heading** or **Empty schedule message** blank restores its default. Reassign activities before deleting their assigned display.

Changes appear on connected TVs within 30 seconds. Event rows share the available space and shrink their text and padding to fit; very large schedules use smaller text.

## Run locally

Use Python 3.12 or later. Docker is the simplest deployment option; for development, create a virtual environment and install dependencies:

```sh
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt tzdata
```

For local Python runs, set environment variables in your shell; the app does not load `.env` itself. For example, in PowerShell:

```powershell
$env:SECRET_KEY = 'your-long-random-secret'
$env:ADMIN_PASSWORD = 'your-unique-admin-password'
$env:TZ = 'America/New_York'
python app.py
```

Open `http://127.0.0.1:8080`. The development entry point listens only on localhost. To serve other devices using Waitress:

```sh
waitress-serve --listen=0.0.0.0:8080 app:app
```

## Tests

With the Python environment active:

```sh
python -m unittest discover -s tests -v
```

For the JavaScript clock and display refresh checks, install Node.js and run:

```sh
node --test tests/test_display.cjs
```

Optional browser layout checks exercise 1, 8, 20, 40, and 80 events across four screen sizes:

```sh
python -m pip install playwright
python -m playwright install chromium
python tests/browser_layout.py
```

Tests use temporary databases rather than your saved schedule.

## Operations and backups

Check status, inspect logs, or restart:

```sh
docker compose ps
docker compose logs -f dashboard
docker compose restart
```

After pulling source changes, rebuild:

```sh
git pull
docker compose up -d --build
```

Back up a running database using SQLite's backup API:

```sh
docker compose exec dashboard python -c "import sqlite3; source=sqlite3.connect('/app/data/dashboard.sqlite3'); target=sqlite3.connect('/app/data/backup.sqlite3'); source.backup(target); target.close(); source.close()"
docker compose cp dashboard:/app/data/backup.sqlite3 ./backup.sqlite3
```

To restore, stop the service and replace the database in its data volume with your backup before starting again. Keep backups outside the device as well. Copying only the live database file can miss data still in SQLite's WAL journal.

## Deployment scope

Designed for a trusted private LAN. The default deployment uses HTTP; use a VPN or an HTTPS reverse proxy for remote access instead of exposing port 8080 directly to the internet.

There is one shared admin password. Calendar imports, multiple user accounts, permissions, media uploads, and scrolling tickers are not included.
