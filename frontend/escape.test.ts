import { expect, test } from 'bun:test';
// Unit tests for the shared HTML escape helper. Every innerHTML template that
// interpolates API data, error text or user input goes through this.

import { escapeHtml } from './js/utils/escape.js';

test('escapeHtml neutralizes HTML metacharacters', () => {
  expect(escapeHtml('<script>alert("x")</script>')).toBe('&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;');
  expect(escapeHtml(`<img src=x onerror='steal()'>`)).toBe(
    '&lt;img src=x onerror=&#39;steal()&#39;&gt;'
  );
});

test('escapeHtml escapes the ampersand first so double-escaping payloads stay inert', () => {
  expect(escapeHtml('&lt;script&gt;')).toBe('&amp;lt;script&amp;gt;');
});

test('escapeHtml passes plain text and numbers through', () => {
  expect(escapeHtml('Earth → Mars')).toBe('Earth → Mars');
  expect(escapeHtml(3.72)).toBe('3.72');
  expect(escapeHtml('')).toBe('');
});

test('escapeHtml coerces null and undefined to safe strings', () => {
  expect(escapeHtml(null)).toBe('null');
  expect(escapeHtml(undefined)).toBe('undefined');
});
