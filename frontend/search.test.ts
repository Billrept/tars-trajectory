import { expect, test } from 'bun:test';
import { rankBodies } from './js/utils/search.js';

const bodies = [{ name: 'Sun' }, { name: 'Mercury' }, { name: 'Mars' }, { name: 'Uranus' }, { name: 'Moon' }];
const names = (list: { name: string }[]) => list.map(b => b.name);

test('rankBodies lists everything for an empty query', () => {
  expect(names(rankBodies(bodies, ''))).toEqual(['Sun', 'Mercury', 'Mars', 'Uranus', 'Moon']);
  expect(names(rankBodies(bodies, '   '))).toEqual(['Sun', 'Mercury', 'Mars', 'Uranus', 'Moon']);
});

test('rankBodies puts prefix matches before substring matches, case-insensitively', () => {
  expect(names(rankBodies(bodies, 'M'))).toEqual(['Mercury', 'Mars', 'Moon']);
  expect(names(rankBodies(bodies, 'ur'))).toEqual(['Uranus', 'Mercury']);
  expect(names(rankBodies(bodies, 'xyz'))).toEqual([]);
});
