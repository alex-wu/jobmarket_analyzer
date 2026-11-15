// Continuous median (linear interpolation between the two middle values),
// matching DuckDB's MEDIAN / quantile_cont(x, 0.5). NULLs are ignored; an empty
// group yields NULL. Pure JS so the browser client (sql.js) and the Node parity
// script (node:sqlite) register the exact same aggregate.
export function medianOf(values) {
  const v = values.filter((x) => x != null).map(Number).sort((a, b) => a - b);
  if (v.length === 0) return null;
  const rn = (v.length - 1) * 0.5;
  const lo = Math.floor(rn);
  const hi = Math.ceil(rn);
  return v[lo] + (v[hi] - v[lo]) * (rn - lo);
}
