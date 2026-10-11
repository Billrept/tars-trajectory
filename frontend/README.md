# Frontend

The 3D solar-system view and mission planner. It's built with Three.js and plain ES modules, bundled by Bun, and served by a small Elysia server.

```bash
bun install --frozen-lockfile
bun run dev      # build, then serve on :3000; there's no hot reload, so rerun after edits
bun test         # unit tests: build output, render gating, search ranking, HTML escaping
```

The API URLs are validated and inlined **at build time**:

```bash
PUBLIC_API_URL=http://localhost:8002 PUBLIC_EPHEMERIS_URL=http://localhost:8001 PUBLIC_JOBS_URL=http://localhost:8003 bun run build
```

Docker Compose passes these as build arguments to `frontend/Dockerfile`. The backends only accept browser requests from origins listed in `CORS_ORIGINS` (`http://localhost:3000` locally).

## Layout

| Path | Role |
|---|---|
| `index.html`, `css/style.css` | Page structure and theme tokens: ink-blue sky, steel-blue selection, solar amber for actions that start something; Noto Sans headings, Source Sans 3 interface text |
| `js/app.js` | Scene, camera, planner, missions history and search wiring |
| `js/apiClient.js` | Calls to the jobs API. Every jobs request uses `credentials: 'include'` so the anonymous cookie is sent; ephemeris and trajectory calls send no credentials. |
| `js/utils/perf.js` | Render gate, pixel-ratio cap, fly easing, trail ring buffer, grid fade |
| `js/utils/search.js` | Search ranking: name prefix first, then substring |
| `js/utils/escape.js` | `escapeHtml` for any API-derived text that goes into `innerHTML` |
| `js/planetData.js`, `js/textures/` | Body facts and textures (see `THIRD_PARTY_NOTICES.md` for licences) |
| `build.ts`, `server.ts` | Bundler, and a static server with gzip, cache headers and `/healthz` |

## Behaviour worth knowing

- **Render on demand.** The scene redraws only when something changes: streamed positions, camera movement, a fly-to, a mission, a resize or a scene edit. Paused and idle, it renders about once a second, down from 60. Pixel ratio is capped at 1.5, and antialiasing is skipped on high-DPI screens.
- **Steady Sun.** There's no lens flare: three.js's flare samples the framebuffer every frame, so it flickered when grid or orbit lines crossed the Sun. Bodies don't spin while the simulation is paused. The ecliptic grid is at 7% opacity and fades to nothing across the inner system.
- **Search island.** An accessible combobox: arrow keys, Enter and Escape work, each body shows a colour dot and its type, and a message appears when nothing matches.
- **Your missions.** History comes from `GET /api/v1/jobs` and is requested on load, which also creates the cookie before the first submission. "Start fresh" calls `DELETE /api/v1/jobs/session`.
