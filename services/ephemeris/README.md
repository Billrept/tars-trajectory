# Ephemeris service

Owns planetary position data. It publishes immutable datasets from NASA/JPL Horizons and serves them to the browser and to the other services.

- **Port (local):** `8001`. Interactive docs at http://localhost:8001/docs.
- **Image:** `services/Dockerfile`, target `ephemeris`, tagged `tars/ephemeris:local`. The one-shot `loader` reuses the same image.
- **Owns:**
  - dataset objects in S3-compatible storage: `datasets/<id>/…` and the `active.json` pointer
  - a disposable Redis cache in front of them

## How data gets in

`python -m ephemeris_service.loader` (the Compose `loader` service):
1. Fetches every body between `EPHEMERIS_START` and `EPHEMERIS_END` from JPL Horizons.
2. Converts UTC to TDB.
3. Validates the full sample grid.
4. Writes immutable NPZ chunks.
5. Moves `active.json` to the new dataset.

Publication is all-or-nothing: if any body is missing or malformed, the previous dataset stays active. The dataset ID is the SHA-256 of its manifest, so a given ID always refers to exactly the same data.

## Endpoints

| Kind | Path | Notes |
|---|---|---|
| Public | `GET /api/v1/ephemeris/bodies` | Body catalog |
| Public | `GET /api/v1/ephemeris/epoch-range` | Coverage window of the active dataset |
| Public | `GET /api/v1/ephemeris/bodies/{id-or-name}/ephemeris?start=&end=&step_days=&scene_units=` | Up to 1,000 sampled positions |
| Public | `WS /api/v1/ephemeris/ws/stream` | Live planet positions; Origin must be in `CORS_ORIGINS` |
| Legacy aliases | `/bodies`, `/epoch-range`, `/bodies/{id}/ephemeris`, `WS /ws/ephemeris/stream` | The frontend still uses these |
| Internal | `GET /internal/v1/active`, `/internal/v1/datasets/{id}`, `/internal/v1/datasets/{id}/bodies/{body}` | Need the `X-Service-Token` header. Never route these through a public proxy. |
| Health | `/livez`, `/health`, `/readyz` | `/readyz` fails until a validated dataset exists |

## Caching

- Public reads send `Cache-Control: public, max-age=60`, so a CDN can absorb read spikes. They only change when a new dataset is published.
- The active manifest is cached in-process for `ACTIVE_MANIFEST_TTL_SECONDS` (default 60). That covers public requests and every tick of the WebSocket stream; without it, each request re-read the pointer and manifest from storage and re-hashed them.
- Snapshots of pinned datasets are held in memory (two at most).

## Configuration

| Variable | Purpose |
|---|---|
| `SERVICE_TOKEN` | Shared secret for the internal endpoints (at least 32 characters) |
| `DATASET_BUCKET`, `S3_ENDPOINT_URL`, `AWS_*` | Dataset object storage |
| `CACHE_REDIS_URL`, `CACHE_PREFIX` | Disposable cache |
| `CORS_ORIGINS` | Allowed browser origins (also checked on the WebSocket) |
| `ACTIVE_MANIFEST_TTL_SECONDS` | Active-manifest cache lifetime, default `60` |
| `EPHEMERIS_START`, `EPHEMERIS_END` | Loader date range |

## Scaling

The service is bound by connections and memory, not CPU: each open WebSocket streams positions about 24 times a second. Scale replicas on open connections. Replicas share nothing except the object store and cache. Put public REST reads behind a CDN.
