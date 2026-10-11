import { expect, test } from 'bun:test';
// Unit tests for perf helpers used by the render-on-demand loop (plan item 1) and
// renderer settings (plan item 2). Scene wiring itself is covered by the plan's
// Playwright verification gate; these cover the pure logic.

import { shouldRender, clampPixelRatio, easeInOutCubic, flyProgress, TrailBuffer, gridFadeFactor } from './js/utils/perf.js';

// ── shouldRender: the frame-rate cap ─────────────────────────────────────────
test('shouldRender throttles to one render per 15 ms window', () => {
  // First render always allowed
  expect(shouldRender(0)).toBe(true);
  // 5 ms later (10 ms since last render) → skip
  expect(shouldRender(5)).toBe(false);
  // 16 ms since last render → allowed again, last render is now t=16
  expect(shouldRender(16)).toBe(true);
  // only 4 ms since the render at t=16 → skip
  expect(shouldRender(20)).toBe(false);
  // 15 ms after the render at t=16 → allowed
  expect(shouldRender(31)).toBe(true);
});

// ── clampPixelRatio: the dpr 1.5 cap (plan item 2) ──────────────────────────
test('clampPixelRatio caps at 1.5', () => {
  expect(clampPixelRatio(1)).toBe(1);
  expect(clampPixelRatio(1.25)).toBe(1.25);
  expect(clampPixelRatio(2)).toBe(1.5);
  expect(clampPixelRatio(3)).toBe(1.5);
});

// ── easeInOutCubic: time-based fly easing over ~1.2 s (plan item 7) ─────────
test('easeInOutCubic maps time to eased progress', () => {
  // start and end anchored
  expect(easeInOutCubic(0)).toBe(0);
  expect(easeInOutCubic(1)).toBe(1);
  // clamped outside [0, 1]
  expect(easeInOutCubic(-0.5)).toBe(0);
  expect(easeInOutCubic(1.5)).toBe(1);
  // symmetric midpoint, and slow-in (first quarter below linear)
  expect(easeInOutCubic(0.5)).toBe(0.5);
  expect(easeInOutCubic(0.25)).toBeLessThan(0.25);
  expect(easeInOutCubic(0.75)).toBeGreaterThan(0.75);
});

// ── flyProgress: reduced motion jumps instantly ─────────────────────────────
test('flyProgress returns 1 immediately under reduced motion, eased otherwise', () => {
  const now = 1000;
  expect(flyProgress(now - 10, now, true)).toBe(1);        // reduced motion: instant
  expect(flyProgress(now - 10, now, false)).toBeCloseTo(easeInOutCubic(10 / 1200));
  expect(flyProgress(now - 1200, now, false)).toBe(1);     // 1.2 s elapsed: done
  expect(flyProgress(now - 100, now, false)).toBeGreaterThan(0);
  expect(flyProgress(now - 100, now, false)).toBeLessThan(1);
});

// ── TrailBuffer: preallocated ring buffer for planet trails (plan item 9) ────
test('TrailBuffer stores points and reports occupied length and draw range', () => {
  const tb = new TrailBuffer(4);
  expect(tb.count()).toBe(0);

  tb.push([1, 2, 3]);
  tb.push([4, 5, 6]);
  expect(tb.count()).toBe(2);

  // Wrapping: capacity 4, push 6 total → keeps the last 4
  tb.push([7, 8, 9]);
  tb.push([10, 11, 12]);
  tb.push([13, 14, 15]);
  tb.push([16, 17, 18]);
  expect(tb.count()).toBe(4);

  // Oldest → newest ordering after wrap (6 pushes, capacity 4 → keeps last 4)
  expect(tb.get(0)).toEqual([7, 8, 9]);
  expect(tb.get(3)).toEqual([16, 17, 18]);
  expect(tb.get(-1)).toBeUndefined();
  expect(tb.get(4)).toBeUndefined();
});

test('TrailBuffer reset clears history', () => {
  const tb = new TrailBuffer(3);
  tb.push([1, 1, 1]);
  tb.reset();
  expect(tb.count()).toBe(0);
  tb.push([2, 2, 2]);
  expect(tb.count()).toBe(1);
  expect(tb.get(0)).toEqual([2, 2, 2]);
});

// ── gridFadeFactor: radial fade so the grid vanishes under the Sun glow ─────
test('gridFadeFactor is 0 inside inner radius, 1 outside outer, linear between', () => {
  // fully hidden at and inside the inner radius (under the Sun glow)
  expect(gridFadeFactor(0, 800, 3600)).toBe(0);
  expect(gridFadeFactor(800, 800, 3600)).toBe(0);
  // full strength at and beyond the outer radius
  expect(gridFadeFactor(3600, 800, 3600)).toBe(1);
  expect(gridFadeFactor(5000, 800, 3600)).toBe(1);
  // midpoint of the ramp is halfway
  expect(gridFadeFactor(2200, 800, 3600)).toBeCloseTo(0.5);
  // ramp is monotonic
  expect(gridFadeFactor(1000, 800, 3600)).toBeLessThan(gridFadeFactor(2000, 800, 3600));
});
