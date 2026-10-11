// js/utils/escape.js — single escape helper for any HTML template that
// interpolates API data, error messages or user input. Numbers produced by
// toFixed() in static templates don't need it.

const ESCAPES = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
};

export function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, ch => ESCAPES[ch]);
}
