# Third-party notices

TARS is MIT-licensed (see [LICENSE](LICENSE)). This file lists third-party
software, data and assets it depends on, with their licenses. Dependency
versions are pinned in `requirements.txt` / `requirements.lock` (Python) and
`frontend/package.json` / `frontend/bun.lock` (frontend).

## Frontend

| Package | License | Notes |
|---|---|---|
| [Three.js](https://threejs.org/) | MIT | 3D rendering, pinned in `frontend/package.json` |
| [Elysia](https://elysiajs.com/) | MIT | Serves the built frontend (`frontend/server.ts`) |

Three.js and Elysia are the only runtime dependencies in
`frontend/package.json`; the Bun toolchain is a build-time dependency.

### Fonts

The frontend loads Google Fonts at runtime:

- Noto Sans — SIL Open Font License 1.1
  (https://fonts.google.com/noto/specimen/Noto+Sans)
- Source Sans 3 — SIL Open Font License 1.1
  (https://fonts.google.com/specimen/Source+Sans+3)

Google Fonts is a trademark of Google LLC. Use of Google Fonts does not imply
endorsement by Google.

### Textures

The textures in `frontend/js/textures/` come from
[Solar System Scope textures](https://www.solarsystemscope.com/textures/),
© INOVE, licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Their `2k_*` and
`8k_*` filenames are kept as shipped.

This project uses:

- `2k_mercury.jpg`, `2k_venus_surface.jpg`, `2k_earth_daymap.jpg`,
  `2k_earth_nightmap.jpg`, `2k_earth_clouds.jpg`,
  `2k_earth_specular_map.tif`, `2k_mars.jpg`, `2k_jupiter.jpg`,
  `2k_saturn.jpg`, `2k_saturn_ring_alpha.png`, `2k_uranus.jpg`,
  `2k_neptune.jpg`, `2k_sun.jpg`
- `2k_ceres_fictional.jpg` (Solar System Scope's fictional Ceres texture)
- `4k_stars_milky_way.jpg` (a downscale of their
  `8k_stars_milky_way.jpg`)

**CC BY 4.0 attribution required:** "Textures by Solar System Scope"
(https://www.solarsystemscope.com/textures/), licensed CC BY 4.0
(https://creativecommons.org/licenses/by/4.0/). The textures are based on NASA
elevation and imagery data.

### Source unconfirmed — verify before public release

- `2k_pluto.jpg` — not listed on the Solar System Scope textures page (that
  page has no Pluto texture). Source unconfirmed.
- `8k_sun.jpg`, `8k_stars_milky_way.jpg` — not referenced by any code and
  slated for deletion; if they are kept, treat them as Solar System Scope
  (CC BY 4.0) but confirm before shipping.

## Backend (Python)

| Package | License |
|---|---|
| FastAPI | MIT |
| Uvicorn/Starlette | BSD 3-Clause |
| Pydantic | MIT |
| pydantic-settings | MIT |
| websockets | BSD 3-Clause |
| NumPy | BSD 3-Clause |
| SciPy | BSD 3-Clause |
| Numba | BSD 2-Clause |
| Astropy | BSD 3-Clause |
| httpx | BSD 3-Clause |
| ARQ | MIT |
| redis-py | MIT |
| protobuf | BSD 3-Clause |
| grpcio-tools (build time only) | Apache-2.0 |

See `requirements.lock` for the full pinned dependency tree and each
package's metadata.

## Local test infrastructure

- [SeaweedFS](https://github.com/seaweedfs/seaweedfs) — Apache-2.0. Used as
  the local S3-compatible object store in `docker-compose.test.yml`
  (the cloud target is S3).
- PostgreSQL, Redis, Docker images as referenced in the Compose files —
  see their respective licenses (PostgreSQL License; Redis RSALv2/SSPLv1 for
  Redis 7.4+, MIT for older; check the pinned image tags).

## Ephemeris data

Ephemeris data is downloaded from the JPL Horizons system
(https://ssd.jpl.nasa.gov/horizons/).

Data courtesy of NASA/JPL-Caltech, JPL Horizons System.

Horizons provides no formal terms-of-use statement beyond its
acknowledgement request; the citation template it offers is:

> Giorgini, JD and JPL Solar System Dynamics Group, NASA/JPL Horizons
> On-Line Ephemeris System, https://ssd.jpl.nasa.gov/horizons/
> (data retrieved YYYY-MON-DD).

Horizons output is intended for observers, mission planners and researchers,
with fitness-for-purpose the user's responsibility, and is not certified for
spacecraft safety or mission-critical use without contacting the Solar System
Dynamics Group.
