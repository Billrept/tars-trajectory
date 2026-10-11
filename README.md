# Interplanetary Trajectory Optimizer

(Will be)Interactive 3D multi-leg gravity-assist trajectory optimizer for a space science course.
Python microservices for the orbital mechanics and job pipeline, and a Three.js frontend bundled with Bun and served by Elysia.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Three.js 0.164.1 (WebGL, render-on-demand), vanilla ES modules, Noto Sans (headings) / Source Sans 3 (interface) |
| Frontend build and serving | Bun 1.3.14 bundler, Elysia 1.4.30 static server (gzip, cache headers) |
| Services | Python 3.12, FastAPI 0.143, Pydantic 2.14, Uvicorn: separate ephemeris, trajectory and jobs services, plus outbox publisher, CPU worker and dataset loader processes |
| Numerics | NumPy 2.5, SciPy 1.18, Numba 0.68, Astropy 8.0 (UTC/TDB); NSGA-II multi-objective optimizer; heliocentric patched-conic model |
| Ephemeris data | NASA/JPL Horizons, published as immutable NPZ datasets |
| Job pipeline | PostgreSQL 16 (jobs, idempotency, transactional outbox) via SQLAlchemy 2.1 and psycopg 3; ARQ 0.28 on Redis 7 (queue, `noeviction`) |
| Cache and storage | Separate Redis 7 cache (disposable); S3-compatible object storage, SeaweedFS locally, via boto3 |
| Identity | No accounts: anonymous HttpOnly cookie per browser, plus per-IP and global admission limits |
| Local runtime | Docker Compose: non-root, read-only containers with dropped capabilities |
| Tests | pytest against real Postgres, Redis and S3 test containers; `bun test`; Playwright for browser checks |
| Production platform | IBM Cloud: Red Hat OpenShift or IKS (multizone), Databases for PostgreSQL, Databases for Redis ×2, Cloud Object Storage, Key Protect; Terraform + Helm. Written and validated, not yet applied. |

## Repository layout

| Folder | What's inside |
|---|---|
| [`frontend/`](frontend/README.md) | Three.js UI, Bun build, Elysia server |
| [`services/ephemeris/`](services/ephemeris/README.md) | Ephemeris datasets, public reads, live stream, loader |
| [`services/trajectory/`](services/trajectory/README.md) | Synchronous trajectory calculations |
| [`services/jobs/`](services/jobs/README.md) | Job API, outbox publisher, CPU worker, schema |
| `services/Dockerfile` | One multi-target Dockerfile for all Python images |
| `.github/` | CI/CD workflows (`ci.yml`, reusable `deploy.yml`) and Dependabot |
| [`deploy/`](deploy/README.md) | Helm chart for IKS and OpenShift, and the deployment runbook |
| [`infra/terraform/ibm/`](infra/terraform/ibm/README.md) | Terraform: platform (VPC, cluster, databases, storage, keys) and cluster bootstrap (namespace, secrets) |
| [`packages/`](packages/README.md) | `tars_core` (numerical engine) and `tars_contracts` (wire contracts, clients) |
| [`scripts/`](scripts/README.md) | Local setup and end-to-end verification |
| [`tests/`](tests/README.md) | Unit, contract and integration tests |
| `src/` | Legacy monolith, kept for compatibility (`docker-compose.legacy.yml`) |

## Quick Start — independent local services

Requirements: Docker Compose and Python 3.12. No cloud resources are created.

```bash
python3.12 scripts/setup_local.py
docker compose -p tars-local --env-file .env.local up --build -d
```

The first loader run downloads all 12 active bodies from NASA JPL Horizons, validates the complete epoch grid, and atomically publishes an immutable dataset. Download time depends on JPL; check `docker compose -p tars-local --env-file .env.local logs loader`. Data survives container restarts in named volumes.

- Frontend: http://localhost:3000
- Ephemeris API: http://localhost:8001/docs
- Trajectory API: http://localhost:8002/docs
- Jobs API: http://localhost:8003/docs

To run the tests, you also need a Python 3.12 virtual environment:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`setup_local.py` generates credentials into the ignored `.env.local`; keep them private.

## Privacy

There are no user accounts and no tracking or analytics. The app sets one anonymous cookie, `tars_uid`, which stores a random ID only — the server stores a hash of it and nothing else. It exists so your mission history ("Your missions") comes back next time you visit, and it expires after 30 days of inactivity. "Start fresh" clears it. Clearing cookies in your browser also deletes your history, permanently; there is no recovery.

## Architecture

![TARS system architecture: frontend calls ephemeris, trajectory and jobs services; jobs commit admission and outbox to PostgreSQL; the outbox feeds a Redis queue; a CPU worker writes fenced results to PostgreSQL and object storage; a loader publishes JPL Horizons datasets.](docs/architecture/system-architecture.svg)

The diagram merges two pieces for readability. The outbox publisher/reconciler runs as its own jobs-image process; it is drawn inside the jobs node. Before computing, the worker loads one pinned dataset snapshot from the ephemeris service.

Each application has its own image/process and health checks. All Python images build from one multi-target `services/Dockerfile`: the shared scientific dependencies install once (with uv and a persistent download cache), and each target adds only its own service code. Numerical loops use one pinned local snapshot, never a network request per fitness evaluation. `packages/tars_core` owns calculations; `packages/tars_contracts` owns request/wire contracts. `src` retains compatibility imports and the legacy app; `docker-compose.legacy.yml` preserves its former layout.

PostgreSQL commits admission and outbox together. An idempotency key scoped to the browser's anonymous cookie returns one logical job; changing its payload returns 409. Execution leases/generations fence stale workers, retries keep the original seed and dataset, and authorized polling/reconnection reads durable status. Because there is no sign-in, admission is also rate-limited per client IP and by a global queue cap. Redis queue and disposable cache are separate instances.

### Why three APIs, and how each one scales

The services are split by the resource each one strains, so a spike in one part can be scaled, or rejected, without slowing the others:

| Service | Owns | Strained by during a spike | Scale on | Backpressure |
|---|---|---|---|---|
| [Ephemeris](services/ephemeris/README.md) | Immutable datasets, cache | Open WebSocket connections and memory | Connections; CDN for REST reads (`Cache-Control: public, max-age=60`) | — |
| [Trajectory](services/trajectory/README.md) | Nothing (stateless) | CPU | CPU | `429` + `Retry-After` beyond 2 concurrent calculations per process |
| [Jobs API](services/jobs/README.md) | PostgreSQL jobs, idempotency, outbox | Light database I/O | At least two replicas | `429` per cookie and per IP, `503` global queue cap |
| Worker (jobs image) | Leases on running jobs | Heavy CPU, minutes per job | Queue depth | The queue itself |

Splitting only helps if the services don't all wait on one another. Trajectory requests and job admissions used to call the ephemeris service for the active dataset on every request. Datasets are immutable and the active pointer moves rarely, so `EphemerisClient` now reuses it for 60 s. The ephemeris service caches it the same way for its own public reads and stream ticks. Measured locally: 20 Lambert requests went from 20 internal calls to 0, at about 8.5 ms per warm request.

High availability doesn't come from the split itself. It needs multiple replicas, managed PostgreSQL and Redis, and more than one availability zone. That's part of the planned cloud deployment.

Production target: IBM Cloud (OpenShift or IKS) with managed Postgres, Redis and Object Storage. The Terraform, Helm chart and deploy pipeline are written and validated, but nothing has been provisioned yet. See [deploy/README.md](deploy/README.md).

## Verification

```bash
docker compose -p tars-test -f docker-compose.test.yml up -d
.venv/bin/python -m pytest -q
cd frontend && bun install --frozen-lockfile && bun test
```

With the application stack healthy, `scripts/verify_local.py` verifies 50 concurrent submissions, one logical job and a stored result. `--restart-worker` checks API availability during an independent worker restart. `--kill-worker` deliberately kills an active local worker and checks retry/seed preservation; it is a destructive drill for the local demo worker only. Reports go to `artifacts/verification`.

The numerical model is heliocentric patched-conic approximation, not flight-qualified mission design. Powered flybys are approximate; future UTC/TDB conversion uses the installed leap-second table and must be refreshed when leap seconds are announced.

`artifacts/` is gitignored, so links to verification reports in this file refer to locally generated files that are not part of the repository.

## CI/CD

GitHub Actions, in [`.github/workflows/ci.yml`](.github/workflows/ci.yml):

```
pull request ─┬─ Secret scan (gitleaks, full history) ───────────┐
              ├─ Python tests (unit + contract + integration) ───┤
              ├─ Frontend build and tests ───────────────────────┼─► build all 5 images, no push
              └─ Deployment config (Terraform validate, Helm lint/render, kubeconform) ┘
push to main ── same checks ─► push images to GHCR ─► deploy staging
tag v1.2.3   ── same checks ─► push images to GHCR ─► deploy staging ─► deploy production (approval)
```

- **Images:** `ghcr.io/<owner>/<repo>/{ephemeris,trajectory,jobs,worker,frontend}`, tagged `sha-<commit>`, `main`, and the version on tags. Published images carry build provenance and an SBOM. Layer cache is kept in GitHub Actions between runs.
- **Supply chain:** every action is pinned to a commit SHA, and the secret scanner runs as a digest-pinned container. [Dependabot](.github/dependabot.yml) proposes weekly updates for the actions and the Docker base images.
- **Permissions:** the default token is read-only. Only the image job can write packages, and pull requests never log in to the registry.
- **Frontend image:** built `same-origin`, so it calls relative `/api/v1/...` paths and one image serves every environment behind the ingress. Local Compose still bakes in the localhost ports.
- **Deploy stages:** off until the repository variable `DEPLOY_ENABLED=true` is set. They deploy by image digest with `helm upgrade --atomic` (automatic rollback on failure), then run smoke checks. Production runs only for `v*` tags, through a protected GitHub environment. Setup: [deploy/README.md](deploy/README.md).

After creating the GitHub repository:
1. Push `main`.
2. Under **Settings → Branches**, protect `main`: require pull requests, and require the checks *Secret scan*, *Python tests*, *Frontend build and tests* and the five *Image* jobs.
3. Make the GHCR packages public if you want people to pull the images.
4. Release with `git tag v0.1.0 && git push origin v0.1.0`.

## What's been built

All verified on the local Docker stack; nothing is deployed yet.

- **Microservices and durable jobs:** separate ephemeris, trajectory and jobs services; transactional outbox; leased, fenced workers with retries that keep the seed; reproducible results pinned to immutable JPL Horizons datasets.
- **Open source, no accounts:** anonymous `tars_uid` cookie for job ownership and "Your missions" history, plus per-cookie, per-IP and global admission limits. API-derived text is escaped before it reaches the page. MIT licence and third-party notices.
- **3D performance:** render on demand and a pixel-ratio cap. Measured idle: about 1 redraw per second instead of 60, and 44% fewer pixels at dpr 2. A smaller sky texture. Camera flights take about 1.2 s and can be cancelled. No automatic zoom to the Sun on load.
- **Visual polish:** a star-atlas theme with Noto Sans headings; no lens-flare flicker, no spinning while paused, and a near-invisible ecliptic grid; a floating search island with an accessible planet and moon list.
- **Faster builds:** one multi-target Dockerfile with shared uv stages and a persistent download cache. Measured: cold build 62 s → 33 s, warm rebuild 23 s → 4 s, single-service code change 7 s → 3 s.
- **Less coupling between services:** the active dataset manifest is cached for 60 s, and public ephemeris reads are CDN-cacheable.
- **CI/CD:** a GitHub Actions pipeline with a secret scan, the Python and frontend test suites, and all five image builds on every pull request; images with provenance and an SBOM pushed to GHCR from `main` and version tags. Validated locally with `actionlint`, a gitleaks run, and a Linux amd64 install of the locked dependencies; it hasn't run on GitHub yet because there's no remote.
- **IBM Cloud deployment:**
  - Terraform for the platform and cluster bootstrap, validated against the IBM provider schema.
  - A hardened Helm chart for IKS and OpenShift, passing strict kubeconform.
  - Staging and production deploy stages.
  - Redis TLS for managed instances, and the bootstrap packaged in the jobs image.
  - The chart installed on a local `kind` cluster under the `restricted` Pod Security Standard, and the full browser flow worked through an NGINX ingress.

## License

MIT. See [LICENSE](LICENSE).

## Credits

This project uses third-party software, data and assets — Three.js, Elysia, Solar System Scope textures (CC BY 4.0), Google Fonts, and NASA/JPL Horizons ephemeris data. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the full list and required attributions.

## Legacy API reference

The sections below describe the compatibility API. In the service stack, body/range/ephemeris calls use port 8001; synchronous trajectory calls use 8002; asynchronous job admission/status/results use 8003 with no sign-in — jobs are scoped to the anonymous `tars_uid` cookie. The legacy job aliases (`/plan`, `/porkchop`, `/optimize`, `/optimize/multileg`, `/optimize/{id}/status`) have been removed from the jobs service; they are documented here for the legacy deployment only. The original port 8000 is available only in the legacy deployment.

## The Optimization Engine (NSGA-II)

The previous placeholder Grey Wolf Optimizer has been replaced with a full **Non-dominated Sorting Genetic Algorithm II (NSGA-II)** (`src/optimizer/nsga2.py`). 

This evolutionary algorithm computes a true Pareto front by evolving a population of trajectories to explicitly evaluate the physical trade-off between **Time of Flight (Minimum Time)** and **Total Delta-V (Minimum Fuel)**.

### Features
- **Intelligent Insights:** The optimizer records the initial feasible trajectory found in early generations and compares it against the final optimized result, providing natural-language insights (e.g., *"Saved 1.2 km/s by shifting departure 5 days earlier"*).
- **Orbital Elements:** Cartesian state vectors are automatically converted into classical Keplerian elements ($a, e, i, \Omega, \omega, \nu$) at the optimal transfer point.
- **Side-by-Side Comparison:** The API computes and returns the full 3D coordinates for both the initial and optimized orbits, allowing the frontend to render the physical orbital shift in real-time.

---

## For the Nano Role

### Scene coordinate system

Backend returns ecliptic coordinates (km) converted to scene units (1 AU = 1000 units).
Three.js mapping:
```
three.x = ecliptic.x
three.y = ecliptic.z   (ecliptic Z becomes "up")
three.z = -ecliptic.y  (flip for right-handed coords)
```

### Key API interactions

All API calls go to `http://localhost:8000`. See the API Reference section below.

The frontend connects two WebSockets:
1. `/ws/ephemeris/stream` -- real-time planetary positions for animation
2. `/ws/trajectory/{job_id}` -- optimization progress streaming

---

## API Reference

Base URL: `http://localhost:8000`

### GET /health

Health check.

**Response:** `{"status": "ok", "service": "tars"}`

---

### POST /orbit-info

Calculate detailed orbital parameters and 3D paths from classical Keplerian elements.

**Request body:**
```json
{
  "a_km": 189870206.34,
  "e": 0.218,
  "i_deg": 1.01,
  "raan_deg": 38.03,
  "arg_p_deg": 4.08
}
```

**Response:**
```json
{
  "periapsis_distance_km": 148478521.36,
  "apoapsis_distance_km": 231261891.33,
  "period_seconds": 44962294.02,
  "periapsis_point_km": [110120365.69, 99543200.37, 186097.63],
  "apoapsis_point_km": [-171584408.62, -155103563.82, -289968.63],
  "periapsis_point_scene": [736.10, 665.40, 1.24],
  "apoapsis_point_scene": [-1146.97, -1036.80, -1.93],
  "full_orbit_points_scene": [
    [736.10, 665.40, 1.24],
    ... (100 points tracing the full ellipse)
  ]
}
```

---

### GET /epoch-range

Returns the valid date range for all queries (the ephemeris cache window).

**Response:**
```json
{
  "start_jd": 2460676.5,
  "end_jd": 2473459.5,
  "start_iso": "2025-01-01",
  "end_iso": "2060-01-01"
}
```

---

### GET /bodies

List the 12 active celestial bodies.

**Response:** Array of:
```json
{
  "naif_id": 399,
  "name": "Earth",
  "gm": 398600.4418,
  "radius": 6371.0,
  "color": "#6B93D6",
  "parent_id": null
}
```

`parent_id` is set for moons (e.g., `301` Moon has `parent_id: 399` Earth).

---

### GET /bodies/{identifier}/ephemeris

Get position data for a body over a date range. `identifier` can be a name (`"earth"`) or NAIF ID (`"399"`).

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| start | str | "2026-01-01" | Start date (ISO) |
| end | str | "2027-01-01" | End date (ISO) |
| step_days | int | 10 | Sample interval |
| scene_units | bool | true | Convert to scene units |

**Response:**
```json
{
  "body": "Earth",
  "naif_id": 399,
  "n_points": 37,
  "scene_units": true,
  "points": [
    {"epoch_jd": 2461041.5, "epoch_iso": "2026-01-01T00:00:00", "x": -175.2, "y": 0.03, "z": 985.1}
  ]
}
```

---

### POST /assess

Assess whether a specific departure date is a good launch window. Returns a quality rating and an optional suggestion for a better nearby date.

**Request body:**
```json
{
  "origin": "earth",
  "target": "mars",
  "departure_date": "2026-09-01",
  "tof_days": 200
}
```

**Response:**
```json
{
  "origin": "Earth",
  "target": "Mars",
  "departure_date": "2026-09-01",
  "departure_jd": 2461327.5,
  "arrival_date": "2027-03-20",
  "arrival_jd": 2461527.5,
  "tof_days": 200.0,
  "dv_total_km_s": 5.83,
  "dv_departure_km_s": 3.12,
  "dv_arrival_km_s": 2.71,
  "converged": true,
  "rating": "good",
  "suggestion": null
}
```

Rating thresholds: `excellent` (<4), `good` (<6), `moderate` (<8), `poor` (<12), `bad` (>=12 km/s).
When rating is `moderate`, `poor`, or `bad`, nearby dates (+/-7,15,30 days) are tested and a `suggestion` is returned if a better date is found.

---

### POST /lambert

Compute a single Lambert transfer between two bodies.

**Request body:**
```json
{
  "origin": "earth",
  "target": "mars",
  "departure_date": "2028-11-15",
  "tof_days": 259
}
```

**Response:**
```json
{
  "origin": "Earth",
  "target": "Mars",
  "departure_jd": 2462090.5,
  "departure_iso": "2028-11-15T00:00:00",
  "arrival_jd": 2462349.5,
  "arrival_iso": "2029-08-01T00:00:00",
  "tof_days": 259.0,
  "dv_departure_km_s": 3.385,
  "dv_arrival_km_s": 3.970,
  "dv_total_km_s": 7.356,
  "trajectory_points": [{"x": 598.7, "y": 787.3, "z": -0.05}, ...],
  "trajectory_epochs": [2462090.5, ...]
}
```

`dv_departure_km_s` = |v_transfer - v_planet| at departure = hyperbolic excess velocity.
So `C3 = dv_departure_km_s^2`.

---

### POST /multileg

Compute a multi-leg trajectory with gravity assists.

**Request body:**
```json
{
  "body_sequence": ["earth", "venus", "earth", "jupiter"],
  "departure_date": "2030-01-15",
  "leg_tof_days": [140, 340, 580]
}
```

**Response:**
```json
{
  "body_sequence": ["Earth", "Venus", "Earth", "Jupiter"],
  "n_legs": 3,
  "total_dv_km_s": 64.37,
  "departure_dv_km_s": 5.99,
  "arrival_dv_km_s": 9.38,
  "flyby_dv_km_s": 0.47,
  "total_tof_days": 1060.0,
  "departure_jd": 2462516.5,
  "arrival_jd": 2463576.5,
  "departure_iso": "2030-01-15T00:00:00",
  "arrival_iso": "2032-12-10T00:00:00",
  "legs": [
    {
      "leg_index": 0,
      "origin": "Earth",
      "target": "Venus",
      "departure_jd": 2462516.5,
      "arrival_jd": 2462656.5,
      "departure_iso": "2030-01-15T00:00:00",
      "arrival_iso": "2030-06-04T00:00:00",
      "tof_days": 140.0,
      "dv_departure_km_s": 5.99,
      "dv_arrival_km_s": 8.66,
      "trajectory_points": [{"x": ..., "y": ..., "z": ..., "epoch_jd": ...}, ...],
      "converged": true
    }
  ],
  "flybys": [
    {
      "body": "Venus",
      "naif_id": 299,
      "epoch_jd": 2462656.5,
      "epoch_iso": "2030-06-04T00:00:00",
      "v_inf_in_km_s": 8.66,
      "v_inf_out_km_s": 6.38,
      "turning_angle_deg": 42.1,
      "flyby_periapsis_km": 12500.0,
      "flyby_altitude_km": 6448.2,
      "powered_dv_km_s": 0.0,
      "feasible_unpowered": true
    }
  ]
}
```

---

### POST /porkchop

Generate a porkchop plot grid (departure date vs TOF vs delta-v).

**Request body:**
```json
{
  "origin": "earth",
  "target": "mars",
  "dep_start": "2028-01-01",
  "dep_end": "2029-01-01",
  "tof_min_days": 150,
  "tof_max_days": 350,
  "dep_steps": 80,
  "tof_steps": 80,
  "binary": false
}
```

**Response:**
```json
{
  "origin": "Earth",
  "target": "Mars",
  "departure_jds": [2461941.5, ...],
  "departure_isos": ["2028-01-01T00:00:00", ...],
  "tof_days": [150.0, 152.5, ...],
  "dv_grid": [[7.2, 8.1, null, ...], ...],
  "dep_steps": 80,
  "tof_steps": 80
}
```

`dv_grid[i][j]` = total delta-v for departure `i`, TOF `j`. `null` = did not converge.
Set `binary: true` to get protobuf encoding instead.

---

### POST /optimize

Submit a single-leg optimization job. Returns immediately with a `job_id`.

**Mode options:** `"min_dv"` (minimize delta-v), `"min_tof"` (minimize time of flight), `"pareto"` (build Pareto front of dv vs tof). Default: `"pareto"`.

**Request body:**
```json
{
  "origin": "earth",
  "target": "mars",
  "dep_start": "2028-01-01",
  "dep_end": "2029-01-01",
  "tof_min_days": 150,
  "tof_max_days": 350,
  "population_size": 30,
  "max_iterations": 200,
  "mode": "pareto"
}
```

**Response:**
```json
{
  "job_id": "uuid-string",
  "status": "queued",
  "origin": "Earth",
  "target": "Mars",
  "message": "Optimization job submitted. Connect to WS /ws/trajectory/{job_id} for live updates."
}
```

---

### POST /optimize/multileg

Submit a multi-leg optimization job.

**Mode options:** `"min_dv"` (minimize delta-v), `"min_tof"` (minimize time of flight), `"pareto"` (build Pareto front). Default: `"pareto"`.

**Request body:**
```json
{
  "body_sequence": ["earth", "venus", "earth", "jupiter"],
  "dep_start": "2029-06-01",
  "dep_end": "2030-06-01",
  "leg_tof_bounds": [[100, 200], [250, 450], [400, 700]],
  "population_size": 40,
  "max_iterations": 300,
  "max_c3": null,
  "mode": "pareto"
}
```

**Response:**
```json
{
  "job_id": "uuid-string",
  "status": "queued",
  "type": "multileg",
  "body_sequence": ["earth", "venus", "earth", "jupiter"],
  "message": "Multi-leg optimization job submitted. Connect to WS /ws/trajectory/{job_id} for live updates."
}
```

---

### GET /optimize/{job_id}/status

Poll the current status of an optimization job (alternative to WebSocket).

**Response (running):**
```json
{
  "job_id": "...",
  "status": "running",
  "result": {
    "iteration": 50,
    "max_iterations": 300,
    "best_dv_total": 12.47,
    ...
  }
}
```

**Response (complete):**
```json
{
  "job_id": "...",
  "status": "complete",
  "result": { ... }
}
```

---

### WebSocket: /ws/trajectory/{job_id}

Stream real-time optimization progress. Connect after submitting a `POST /optimize` or `/optimize/multileg`.

**Messages received (JSON):**

Single-leg progress:
```json
{
  "status": "running",
  "iteration": 42,
  "max_iterations": 200,
  "best_dv_total": 5.63,
  "best_departure_jd": 2462050.5,
  "best_tof_days": 220.0,
  "best_dv_departure": 3.2,
  "best_dv_arrival": 2.43,
  "converged": true,
  "population_best_dvs": [5.63, 5.89, 6.12]
}
```

Multi-leg progress:
```json
{
  "status": "running",
  "type": "multileg",
  "iteration": 42,
  "max_iterations": 300,
  "best_dv_total": 12.47,
  "best_departure_jd": 2462288.5,
  "best_leg_tof_days": [140, 340, 580],
  "best_total_tof_days": 1060,
  "best_dv_departure": 3.9,
  "best_dv_arrival": 8.1,
  "best_dv_flyby": 0.47,
  "converged": true,
  "body_sequence": ["earth", "venus", "earth", "jupiter"],
  "population_best_dvs": [12.47, 13.2, 14.1]
}
```

Final message has `"status": "complete"`. Connection closes after.

---

### WebSocket: /ws/ephemeris/stream

Stream real-time planetary positions for 3D animation.

**Send config (JSON) on connect:**
```json
{
  "body_ids": [399, 499, 599],
  "start_jd": 2461041.5,
  "speed": 1.0,
  "fps": 30,
  "scene_units": true,
  "binary": false
}
```

All fields optional. Defaults: all planets, 2026-01-01, 1 day/sec, 30 FPS, scene units, JSON.

**Messages received:**
```json
{
  "epoch_jd": 2461041.5,
  "epoch_iso": "2026-01-01T00:00:00",
  "bodies": [
    {"body_id": 399, "name": "Earth", "position": [-175.2, 0.03, 985.1]}
  ]
}
```

**Control messages (send as text):** `"pause"`, `"resume"`, `"stop"`, or a new config JSON.

---

## Active Bodies Catalog (12 total)

| NAIF ID | Name | Type |
|---------|------|------|
| 10 | Sun | Star |
| 199 | Mercury | Planet |
| 299 | Venus | Planet |
| 399 | Earth | Planet |
| 499 | Mars | Planet |
| 599 | Jupiter | Planet |
| 699 | Saturn | Planet |
| 799 | Uranus | Planet |
| 899 | Neptune | Planet |
| 999 | Pluto | Dwarf planet |
| 2000001 | Ceres | Dwarf planet |
| 301 | Moon | Moon (Earth) |

---

## Legacy configuration (.env)

```bash
REDIS_URL=redis://redis:6379       # Redis connection
EPHEMERIS_START=2025-01-01          # Cache start date
EPHEMERIS_END=2060-01-01            # Cache end date
EPHEMERIS_STEP_DAYS=1               # Sample interval (days)
```

---

## Legacy development (without Docker)

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Need Redis running locally
redis-server &

# Start API
cd src && uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Start worker (separate terminal)
cd src && arq workers.worker.WorkerSettings

# Serve frontend (separate terminal)
cd frontend && bun install --frozen-lockfile && bun run dev
```

---

## Bun/Elysia frontend

Use Bun **1.3.14**. `frontend/bun.lock` locks Elysia **1.4.30** and the existing Three.js **0.164.1** version.

From `frontend/`:

```bash
bun install --frozen-lockfile
bun run dev       # Builds the frontend and starts Elysia on port 3000
bun test          # Build, asset delivery, compression and public configuration checks
```

Rerun `bun run dev` after changing frontend source; this command does not enable hot module replacement. For a production artifact, run `bun run build`, then `bun run start` to serve it, or upload `dist/` to static hosting. Source files cannot be served directly with the old import-map setup.

The build bundles JavaScript/CSS, copies runtime-referenced textures, and writes precompressed gzip assets. Elysia serves only generated public files, uses long-lived caching for hashed JS/CSS, revalidates HTML, and exposes `/healthz`. The frontend image runs as an unprivileged user; Compose keeps its filesystem read-only. Docker builds run `bun install --frozen-lockfile`.

The browser API defaults to `http://localhost:8000`. For another backend, set its **public** URL at build time:

```bash
PUBLIC_API_URL=https://api.example.com bun run build
```

For the service Compose stack, `.env.local` supplies `PUBLIC_API_URL`, `PUBLIC_EPHEMERIS_URL` and `PUBLIC_JOBS_URL` before building. This is a browser-visible URL, never a secret; WebSocket URLs derive its `ws`/`wss` scheme. Backend CORS must permit the frontend origin. Only this explicit URL is inserted into the browser bundle; build environment variables are not generally exposed.

The Python numerical engine and job queue still use their existing runtime. Cloud deployment and production security hardening are planned, not completed.
