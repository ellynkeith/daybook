# Running it

## Deploy (Render + Neon, both free)

1. Create a Postgres database on [Neon](https://neon.tech) and copy its connection string.
2. Create a web service on [Render](https://render.com) from this repo. `render.yaml` sets the build, start and health-check commands.
3. Set the environment variables below, then deploy. Tables are created on first start.

Free Render services sleep when idle, so the first request after a while takes up to a minute. Neon's free tier doesn't expire (Render's own free Postgres does, after 30 days).

## Environment variables

| Variable | Needed | What it does |
|---|---|---|
| `DATABASE_URL` | yes | Neon connection string. Without it the app still starts (only the demo works). |
| `APP_PASSWORD` | yes | The household login's password. Unset = every request is refused with a clear error, never an open app. |
| `APP_USERNAME` | no | Household username, default `family`. |
| `VIEWER_PASSWORD` | no | Turns on the read-only login. The server refuses every non-GET request from it. |
| `VIEWER_USERNAME` | no | Default `viewer`. |
| `DEMO_PASSWORD` | no | Turns on the demo login (in-memory sample data, never touches the database). |
| `DEMO_USERNAME` | no | Default `demo`. |
| `ANALYSIS_OVERRIDES` | no | Record-specific analysis rules: the contents of `overrides.json` (see [analysis/README.md](../analysis/README.md)). Unset = generic rules only. |
| `PYTHON_VERSION` | set in `render.yaml` | 3.12.7 |

**Changing settings on Render:** the app reads them once at startup, so use **Save and deploy**, not "Save only". The change shows as its own row in the service's Events.

**`ANALYSIS_OVERRIDES` specifically:** overrides only change what Insights counts, never the log itself (History always shows what was logged). Unknown keys are rejected, and then *no* overrides apply (the Insights tab shows a warning). So when a code change adds a new override key, deploy the code first, then the new value.

## Run locally

```
pip install -r requirements.txt
APP_PASSWORD=pick-one DEMO_PASSWORD=demo uvicorn main:app --reload
```

Open http://localhost:8000 and log in as `demo` / `demo`; no database needed. For the real login, also set `DATABASE_URL`.

## Tests

```
cd analysis
python3 -m unittest discover tests
```

Synthetic data only: the repo is public, so never put real export rows in a test.

## Where things live

| Path | What |
|---|---|
| `main.py` | App wiring |
| `auth.py` | The three logins (basic auth middleware) |
| `routes.py` | Every API endpoint, including `/api/export` and `/api/insights` |
| `db.py` | Connection and table creation |
| `models.py` | Request validation and the starter category, situation and event lists |
| `demo_store.py`, `demo_backdrop.py` | Demo data: a hand-written recent week, plus about two months generated from a fixed seed |
| `static/index.html` | The whole frontend |
| `analysis/` | Export → tidy tables, and the Insights calculations |
| `Claude outputs/` | Gitignored: real exports, private overrides, notebooks |
