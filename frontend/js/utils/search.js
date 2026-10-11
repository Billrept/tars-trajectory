// Rank bodies for the search list: name prefix matches first, then matches
// anywhere in the name; an empty query lists every body in catalogue order.
export function rankBodies(bodies, query) {
  const q = String(query ?? '').trim().toLowerCase();
  if (!q) return bodies.slice();
  const starts = [], contains = [];
  for (const body of bodies) {
    const name = body.name.toLowerCase();
    if (name.startsWith(q)) starts.push(body);
    else if (name.includes(q)) contains.push(body);
  }
  return starts.concat(contains);
}
