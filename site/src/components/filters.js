import * as Inputs from "npm:@observablehq/inputs";
import {html} from "npm:htl";
import {ISCO_MAJORS} from "./isco.js";

const ALL = "(all)";

export function countrySelect(options, def) {
  const list = [ALL, ...options];
  const value = def && list.includes(def) ? def : ALL;
  return Inputs.select(list, {label: "Country", value});
}

export function iscoMajorSelect(present, def) {
  const opts = [ALL, ...present];
  const value = def && opts.includes(def) ? def : ALL;
  return Inputs.select(opts, {
    label: "ISCO group",
    value,
    format: (k) => (k === ALL ? "All ISCO groups" : `${k} — ${ISCO_MAJORS[k] ?? "?"}`)
  });
}

export function salaryRange(min = 0, max = 250000, def) {
  const clamp = (v, fallback) => (Number.isFinite(v) ? Math.min(Math.max(v, min), max) : fallback);
  const lo = clamp(def?.lo, min);
  const hi = clamp(def?.hi, max);
  return Inputs.form(
    {
      lo: Inputs.number([min, max], {label: "Salary min (€)", value: lo, step: 5000}),
      hi: Inputs.number([min, max], {label: "Salary max (€)", value: hi, step: 5000})
    },
    {template: (form) => html`<div>${form.lo}${form.hi}</div>`}
  );
}

export function dateRange(dates, def) {
  const valid = dates.filter((d) => d instanceof Date && !isNaN(d));
  if (valid.length === 0) return Inputs.form({from: Inputs.date(), to: Inputs.date()});
  const min = new Date(Math.min(...valid));
  const max = new Date(Math.max(...valid));
  const inRange = (d) => d instanceof Date && !isNaN(d) && d >= min && d <= max;
  const from = inRange(def?.from) ? def.from : min;
  const to = inRange(def?.to) ? def.to : max;
  return Inputs.form(
    {
      from: Inputs.date({label: "Posted from", value: from, min, max}),
      to: Inputs.date({label: "Posted to", value: to, min, max})
    },
    {template: (form) => html`<div style="display:flex;gap:0.75rem">${form.from}${form.to}</div>`}
  );
}

// Compose a SQL WHERE clause from the four filter values.
// Returns a string starting with "WHERE" (or "" if no filters active).
export function whereClause({country, iscoMajor, salary, dates}) {
  const parts = [];
  if (country && country !== ALL) parts.push(`country = '${escape(country)}'`);
  if (iscoMajor && iscoMajor !== ALL) parts.push(`isco_major = '${escape(iscoMajor)}'`);
  if (salary && (salary.lo != null || salary.hi != null)) {
    if (salary.lo != null) parts.push(`(salary_annual_eur_p50 IS NULL OR salary_annual_eur_p50 >= ${+salary.lo})`);
    if (salary.hi != null) parts.push(`(salary_annual_eur_p50 IS NULL OR salary_annual_eur_p50 <= ${+salary.hi})`);
  }
  if (dates && dates.from) parts.push(`posted_at >= TIMESTAMP '${toIso(dates.from)}'`);
  if (dates && dates.to)   parts.push(`posted_at <= TIMESTAMP '${toIso(dates.to)}'`);
  return parts.length ? `WHERE ${parts.join(" AND ")}` : "";
}

// Returns the same SQL fragment but suitable for appending to an existing WHERE clause.
// Use when you have an unconditional predicate (e.g. salary IS NOT NULL) and want to
// add the filter on top without the WHERE/AND shim noise.
export function andClause(where) {
  return where ? `${where} AND` : "WHERE";
}

export function escape(s) {
  return String(s).replace(/'/g, "''");
}

function toIso(d) {
  return new Date(d).toISOString().slice(0, 19).replace("T", " ");
}

export {ALL};
