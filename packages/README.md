# Shared packages

The only code shared between services. A service never imports another service's application code; anything two services need lives here.

## `tars_core`: the numerical engine

Pure calculation code. No network clients, web framework or service settings.

| Module | Contents |
|---|---|
| `mechanics/` | Kepler propagation, Lambert solver, multi-leg patched-conic transfers, frame and scene transforms |
| `optimizer/` | NSGA-II multi-objective optimizer (time of flight vs total ΔV), objectives, result types |
| `planner/` | Route search over the body catalog |
| `ephemeris.py` | `EphemerisSnapshot`: an interpolation view over one pinned dataset |
| `arrays.py` | Safe NPZ encoding and decoding: `allow_pickle=False`, with dtype, shape, finite-value and size checks |
| `bodies.py` | The 12-body catalog (NAIF IDs, GM, radius, colour) |
| `time.py` | UTC ↔ TDB conversion (Astropy) and ISO / Julian-date helpers |
| `calculation.py` | Request-shaped entry points used by the trajectory service and the worker |

The model is a heliocentric patched-conic approximation, not flight-qualified mission design. Numerical loops use one pinned in-memory snapshot and never make a network call per fitness evaluation.

## `tars_contracts`: wire contracts and clients

| Module | Contents |
|---|---|
| `requests.py` | Pydantic request models and `normalize_submission` (canonical payloads for idempotency fingerprints) |
| `client.py` | `EphemerisClient`: the internal client to the ephemeris service. Verifies manifest and chunk checksums, keeps two pinned snapshots in memory, and reuses the active manifest for `active_ttl` seconds (default 60). |
| `ttl.py` | `TTLValue`: one cached value with a time-to-live. A failed fetch caches nothing. |
| `horizons.py` | JPL Horizons query client and epoch-grid validation, used by the ephemeris loader and dataset store |

## Using them

Both are plain setuptools packages. The service images install them with `uv pip install --no-deps`. Locally, `pytest.ini` puts both on `pythonpath`, so no install step is needed for tests.
