# Jobs service

Runs long calculations reliably: route search (`plan`), launch-window grids (`porkchop`) and single-transfer or multi-planet optimization. One image provides four processes:

| Process | Compose service | Command | Role |
|---|---|---|---|
| API | `jobs` (port `8003`) | `uvicorn jobs_service.app:create_app` | Admission, status, results, history |
| Outbox publisher | `outbox` | `python -m jobs_service.outbox` | Moves committed jobs onto the Redis queue; re-sends lost or abandoned work |
| Worker | `worker` | `arq jobs_service.worker.WorkerSettings` | Runs one CPU calculation at a time in a child process |
| Bootstrap | `initialize` | `scripts/initialize_services.py` | Applies `schema.sql`; runs once |

**Images:** `services/Dockerfile`. Target `jobs` (`tars/jobs:local`) serves the API, outbox and bootstrap. Target `worker` (`tars/worker:local`) adds Numba.

## Identity: no accounts

- **Cookie:** each browser gets an anonymous `tars_uid` cookie: 128-bit random, `HttpOnly; SameSite=Lax; Path=/api/v1/jobs; Max-Age=30 days`, refreshed on every response. `Secure` is set when `COOKIE_SECURE=1`.
- **Owner:** stored as `anon:` plus the first 32 hex characters of `sha256(cookie)`. The owner never comes from a request body or header.
- **Other owners' jobs:** return `404`.

## API

| Path | Purpose |
|---|---|
| `POST /api/v1/jobs` | Submit `{kind, payload}` with an `Idempotency-Key` header (16–128 characters). Returns `202 {job_id, status, status_url}`. |
| `GET /api/v1/jobs?limit=20` | Your history ("Your missions"), newest first |
| `GET /api/v1/jobs/{id}` | Status and progress |
| `GET /api/v1/jobs/{id}/result` | Stored result once the job succeeds |
| `DELETE /api/v1/jobs/session` | "Start fresh": expires the cookie. Old rows age out after 30 days. |

## Reliability guarantees

- **No duplicate jobs:** the same cookie and the same key return the same job. A changed payload under the same key returns `409`.
- **No lost jobs:**
  - The job row and its outbox row commit in one PostgreSQL transaction.
  - The outbox publisher sends job IDs only.
  - A 30-second reconciliation loop re-sends anything unstarted or abandoned.
- **Crash recovery:**
  - A worker claims a job with a 90 s lease, renewed every 15 s, and a fencing token. A stale worker can't overwrite progress or results.
  - Retries keep the original seed and dataset. There are at most 3 attempts, each up to 600 s.
- **Results:** uploaded to `attempts/` first, copied to `results/`, then committed under the fencing token.

## Abuse limits (needed because there's no sign-in)

| Limit | Default | Response |
|---|---|---|
| Per cookie | 3 queued, 2 running, 50 per day | `429` |
| Per IP (`RATE_LIMIT_PER_MIN`, `RATE_LIMIT_PER_DAY`) | 5 per minute, 30 per day, counted only when a new job is created | `429` |
| Global queue cap (`GLOBAL_QUEUE_CAP`) | 25 queued | `503` |
| Limiter Redis unavailable | Fails closed | `503` |

Client IP comes from `TRUSTED_PROXY_HOPS`. `0` uses the socket address. `N` takes the Nth entry from the right of `X-Forwarded-For`; anything further left is client-supplied and ignored. Expected values: local 0, one reverse proxy 1, CloudFront + ALB 2.

## Configuration

`DATABASE_URL`, `DATABASE_SCHEMA`, `QUEUE_REDIS_URL`, `CACHE_REDIS_URL`, `RESULT_BUCKET`, `AWS_*`, `EPHEMERIS_URL`, `SERVICE_TOKEN`, `CORS_ORIGINS`, plus the cookie and limit variables above. Admission reuses the active dataset manifest for 60 s (`EphemerisClient`), so submitting a job doesn't call the ephemeris service.

## Scaling

- **API:** light database and Redis I/O. Run at least two replicas.
- **Outbox:** one or two replicas. Row leases make extra replicas safe.
- **Worker:** CPU-heavy, with `max_jobs=1` per process. Scale on queue depth and the age of the oldest queued job. The queue is what absorbs spikes.
