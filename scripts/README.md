# Scripts

Run these with the project's Python 3.12 environment (`.venv/bin/python`). They target the local loopback stack only and never print credentials.

| Script | When to run it |
|---|---|
| `setup_local.py` | Once, before the first `docker compose up`. Generates private local secrets into the gitignored `.env.local`, and never overwrites an existing file. |
| `initialize_services.py` | Run automatically by the Compose `initialize` service: applies `services/jobs/jobs_service/schema.sql` and creates the storage buckets. You don't normally run it by hand. |
| `verify_local.py` | With the stack up. Checks every service, sends 50 concurrent identical job submissions with one cookie, and confirms they produce one job with a stored result. Writes a report to `artifacts/verification/`. |
| `verify_local.py --restart-worker` | Also checks that the APIs keep answering while the worker restarts |
| `verify_local.py --kill-worker` | **Destructive drill** on the local worker: kills it mid-job and checks the job retries with the same seed |
| `verify_streams.py` | Opens the public ephemeris WebSocket and checks that it streams positions |
| `fetch_ephemeris.py` | Legacy monolith only (`src/`, `docker-compose.legacy.yml`). The service stack uses the ephemeris loader instead. |
