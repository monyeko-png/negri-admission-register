# Negri Primary School — Admission Register (database app)

A small Flask + SQLite web app for the admission register. Unlike the
single-file HTML version, this stores data in a **real shared database**:
everyone who opens the page sees the same records, and edits, additions,
deletions, and custom fields are saved on the server — not just in one
visitor's browser.

## What's included

```
negri_db_app/
├── app.py              Flask backend + API
├── seed_data.json       The 439 transcribed register entries (used to seed the DB on first run)
├── templates/
│   └── index.html       Frontend (search, sort, add/edit/delete, custom fields, import/export)
├── requirements.txt
├── Procfile              For Render / Railway / Heroku-style platforms
└── render.yaml           Optional one-click config for Render.com
```

## Run it locally

```bash
cd negri_db_app
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open **http://localhost:5000** — the database (`negri.db`, SQLite) is
created automatically on first run and seeded with the transcribed
register.

## Deploying so it's reachable on the web

Any host that runs a Python/Flask app works. Three easy free/cheap options:

### Option A — Render.com (recommended, easiest)

1. Push this folder to a GitHub repo.
2. On [render.com](https://render.com), click **New → Web Service**, connect the repo.
3. Render will detect `render.yaml` automatically (or set manually):
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
4. **Important:** SQLite needs a persistent disk, or your data resets on
   every redeploy. The included `render.yaml` already attaches a small
   free-tier-compatible disk mounted at `data/` and points the app at it
   via the `DATABASE_PATH` environment variable. If you set things up
   manually instead of via `render.yaml`, add a disk yourself (Render
   dashboard → your service → **Disks**) and set the environment variable:
   ```
   DATABASE_PATH=/opt/render/project/src/data/negri.db
   ```
5. Deploy. You'll get a URL like `https://negri-admission-register.onrender.com`.

### Option B — Railway.app

1. Push to GitHub, then **New Project → Deploy from GitHub repo** on railway.app.
2. Railway auto-detects Python and uses the `Procfile`.
3. Add a **Volume** (Railway's persistent disk) mounted at e.g. `/data`,
   and set `DATABASE_PATH=/data/negri.db` in the service's variables tab.
4. Deploy — Railway gives you a public URL.

### Option C — Fly.io / a plain VPS

Any place that can run `gunicorn app:app` behind a reverse proxy works.
On a VPS (e.g. a small DigitalOcean/Linode droplet):

```bash
git clone <your-repo>
cd negri_db_app
pip install -r requirements.txt
gunicorn app:app --bind 0.0.0.0:8000
```

Then point Nginx/Caddy at port 8000, and add a systemd service so it
restarts on reboot. Since it's your own disk, SQLite just works — no
special persistence setup needed.

## A note on SQLite + free hosting

SQLite writes to a single file. That's fine and fast for a small
register like this (hundreds to low thousands of rows, modest traffic).
The one thing to watch on managed platforms is that some free tiers wipe
the filesystem on every deploy/restart — that's why Option A/B above
call out attaching a persistent disk/volume. If you outgrow SQLite later
(many simultaneous editors, need for backups/replicas), swapping in
Postgres is a moderate change: mainly rewriting the `sqlite3` calls in
`app.py` to use `psycopg2` or `SQLAlchemy` — the API routes and frontend
wouldn't need to change.

## API reference (if you want to script against it)

| Method | Path                    | Description                          |
|--------|--------------------------|---------------------------------------|
| GET    | `/api/records`           | List all records                      |
| POST   | `/api/records`           | Create a record (JSON body)           |
| PUT    | `/api/records/<no>`      | Update a record                       |
| DELETE | `/api/records/<no>`      | Delete a record                       |
| GET    | `/api/fields`            | List core + custom field definitions  |
| POST   | `/api/fields`            | Add a custom field (`{"label": "..."}`)|
| DELETE | `/api/fields/<key>`      | Remove a custom field                 |
| GET    | `/api/export`            | Export all records + custom fields    |
| POST   | `/api/import`            | Replace all data (accepts export format or a plain array of records) |
| POST   | `/api/reset`             | Reset to the original transcribed register |

## Backups

Even with a real database, it's worth clicking **Export JSON** in the UI
periodically (or hitting `GET /api/export`) to keep a plain-JSON backup
outside the app — cheap insurance against accidental bulk edits or a
lost disk.
