import {ALL} from "./filters.js";

// Read current filter state from URL search params. Returns an object with
// undefined for absent keys — callers supply their own defaults (filter
// constructors do, with bounds from the DB).
export function readFromURL() {
  if (typeof window === "undefined") return {};
  const p = new URLSearchParams(window.location.search);
  const intOrU = (k) => (p.has(k) ? Number(p.get(k)) : undefined);
  const dateOrU = (k) => (p.has(k) ? new Date(`${p.get(k)}T00:00:00Z`) : undefined);
  return {
    country: p.get("country") ?? undefined,
    iscoMajor: p.get("isco") ?? undefined,
    arrangement: p.get("arr") ?? undefined,
    salaryLo: intOrU("salary_lo"),
    salaryHi: intOrU("salary_hi"),
    dateFrom: dateOrU("date_from"),
    dateTo: dateOrU("date_to"),
    preset: p.get("preset") ?? undefined
  };
}

// Update the URL in-place via history.replaceState. Omits any param equal to
// its default (keeps URLs clean when filters at rest). No navigation.
export function writeToURL(filters, defaults) {
  if (typeof window === "undefined") return;
  const p = new URLSearchParams(window.location.search);
  const setOrDel = (k, v, isDef) => (isDef ? p.delete(k) : p.set(k, String(v)));

  setOrDel("country", filters.country, filters.country == null || filters.country === ALL);
  setOrDel("isco", filters.iscoMajor, filters.iscoMajor == null || filters.iscoMajor === ALL);
  setOrDel("arr", filters.arrangement, filters.arrangement == null || filters.arrangement === ALL);

  const lo = filters.salary?.lo;
  const hi = filters.salary?.hi;
  setOrDel("salary_lo", lo, lo == null || lo === defaults.salaryLoBound);
  setOrDel("salary_hi", hi, hi == null || hi === defaults.salaryHiBound);

  const f = filters.dates?.from;
  const t = filters.dates?.to;
  setOrDel("date_from", isoDay(f), !f || sameDay(f, defaults.dateFromBound));
  setOrDel("date_to", isoDay(t), !t || sameDay(t, defaults.dateToBound));

  setOrDel("preset", filters.preset, !filters.preset || filters.preset === defaults.presetDefault);

  const qs = p.toString();
  const next = `${window.location.pathname}${qs ? "?" + qs : ""}${window.location.hash}`;
  window.history.replaceState(null, "", next);
}

function isoDay(d) {
  if (d == null) return "";
  const x = d instanceof Date ? d : new Date(d);
  return Number.isFinite(+x) ? x.toISOString().slice(0, 10) : "";
}

function sameDay(a, b) {
  if (!a || !b) return false;
  return isoDay(a) === isoDay(b);
}
