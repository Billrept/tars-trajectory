// js/utils/perf.js — pure helpers for the render-on-demand loop.
// No THREE imports: unit-testable with bun:test, wired into app.js's animate().

// One render at most every 15 ms (~60 fps cap). `nowMs` is performance.now().
let lastRenderMs = -Infinity;
export function shouldRender(nowMs) {
  if (nowMs - lastRenderMs >= 15) {
    lastRenderMs = nowMs;
    return true;
  }
  return false;
}

// Display resolution above 1.5 buys nothing on this scene and doubles GPU fill.
export function clampPixelRatio(dpr) {
  return Math.min(dpr, 1.5);
}

// Radial fade factor for one vertex of the ecliptic grid, so the grid vanishes
// under the Sun's glow instead of poking through it near the origin.
// `r` is the vertex distance from the centre; `inner` is where the fade starts,
// `outer` where the grid reaches full strength (both in the same units as `r`).
// Returns 0 inside `inner`, 1 outside `outer`, smooth in between. Pure function
// so the fade curve can be unit-tested; app.js bakes it into vertex colours.
export function gridFadeFactor(r, inner, outer) {
  if (r <= inner) return 0;
  if (r >= outer) return 1;
  return (r - inner) / (outer - inner);
}

// Time-based ease-in-out cubic for camera fly-to. t in [0, 1], clamped.
export function easeInOutCubic(t) {
  t = Math.min(1, Math.max(0, t));
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

// Fly progress for the camera transition: eased over FLY_DURATION_MS of elapsed
// time, or an instant jump under reduced motion. `startMs`/`nowMs` are
// performance.now()-based; `reducedMotion` is prefers-reduced-motion.
export const FLY_DURATION_MS = 1200;
export function flyProgress(startMs, nowMs, reducedMotion) {
  if (reducedMotion) return 1;
  return easeInOutCubic((nowMs - startMs) / FLY_DURATION_MS);
}

// Fixed-capacity ring buffer of [x, y, z] points for planet trails.
// The scene keeps one preallocated BufferGeometry per body and rewrites
// positions in place; this answers "how many points are live" (draw range)
// and "what is the oldest→newest order" without any allocation per update.
export class TrailBuffer {
  constructor(capacity) {
    this.capacity = capacity;
    this.items = new Array(capacity);
    this.size = 0;
    this.head = 0; // index of the oldest live point
  }

  push(point) {
    this.items[(this.head + this.size) % this.capacity] = point;
    if (this.size < this.capacity) this.size++;
    else this.head = (this.head + 1) % this.capacity;
  }

  count() { return this.size; }

  get(i) {
    if (i < 0 || i >= this.size) return undefined;
    return this.items[(this.head + i) % this.capacity];
  }

  reset() {
    this.size = 0;
    this.head = 0;
  }
}
