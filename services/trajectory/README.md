# Trajectory service

Runs bounded, synchronous trajectory calculations for the browser: Lambert transfers, multi-leg routes, launch-date assessments and orbital elements. Anything that takes longer, such as route search, launch-window grids and optimization, goes through the jobs service instead.

- **Port (local):** `8002`. Interactive docs at http://localhost:8002/docs.
- **Image:** `services/Dockerfile`, target `trajectory`, tagged `tars/trajectory:local`. Includes Numba.
- **Owns:** no data. It reads pinned datasets from the ephemeris service.

## Endpoints

| Path | Body |
|---|---|
| `POST /api/v1/trajectory/lambert` | `{"origin":"earth","target":"mars","departure_date":"2026-11-17T00:00:00Z","tof_days":270}` |
| `POST /api/v1/trajectory/multileg` | Body sequence, departure date, per-leg times of flight |
| `POST /api/v1/trajectory/assess` | A candidate departure date and time of flight |
| `POST /api/v1/trajectory/orbit-info` | State vector → classical orbital elements |
| `/livez`, `/health`, `/readyz` | Health. `/readyz` reports the active dataset ID. |

Legacy aliases without the `/api/v1/trajectory` prefix (`/lambert`, `/multileg`, `/assess`, `/orbit-info`) still exist. Body names are strings (`"earth"`), not NAIF numbers.

## Load behaviour

- Each process runs at most **2 calculations at once**. A third gets `429` with `Retry-After: 1`. This is deliberate backpressure: a burst can't queue up unbounded work in one process.
- Datasets are fetched once and held in memory. The active manifest is reused for 60 s (`EphemerisClient(active_ttl=60)` in `tars_contracts`), so a request does not call the ephemeris service. Measured locally: 20 Lambert requests went from 20 internal ephemeris calls to 0, and a warm request averages about 8.5 ms.
- Infeasible results are rejected, never returned as a cheap fake answer: a Lambert leg that didn't converge, or non-finite values.

## Configuration

| Variable | Purpose |
|---|---|
| `EPHEMERIS_URL`, `SERVICE_TOKEN` | Internal ephemeris API |
| `CORS_ORIGINS` | Allowed browser origins |
| `NUMBA_CACHE_DIR` | Writable Numba cache, set to `/tmp/numba` in the image |

## Scaling

The service is CPU-bound and stateless. Scale replicas on CPU. Each replica keeps its own in-memory dataset snapshot, so memory per replica is roughly the size of one dataset.
