import * as Inputs from "npm:@observablehq/inputs";
import {html} from "npm:htl";
import {ISCO_MAJORS} from "./isco.js";

const ALL = "(all)";

export function countrySelect(options) {
  const list = [ALL, ...options];
  return Inputs.select(list, {label: "Country", value: ALL});
}

export function iscoMajorSelect(present) {
  const opts = [ALL, ...present];
  return Inputs.select(opts, {
    label: "ISCO group",
    value: ALL,
    format: (k) => (k === ALL ? "All ISCO groups" : `${k} — ${ISCO_MAJORS[k] ?? "?"}`)
  });
}

export function salaryRange(min = 0, max = 250000) {
  return Inputs.form(
    {
      lo: Inputs.number([min, max], {label: "Salary min (€)", value: min, step: 5000}),
      hi: Inputs.number([min, max], {label: "Salary max (€)", value: max, step: 5000})
    },
    {template: (form) => html`<div>${form.lo}${form.hi}</div>`}
  );
}

export function dateRange(dates) {
  const valid = dates.filter((d) => d instanceof Date && !isNaN(d));
  if (valid.length === 0) return Inputs.form({from: Inputs.date(), to: Inputs.date()});
  const min = new Date(Math.min(...valid));
  const max = new Date(Math.max(...valid));
  return Inputs.form(
    {
      from: Inputs.date({label: "Posted from", value: min, min, max}),
      to: Inputs.date({label: "Posted to", value: max, min, max})
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

function escape(s) {
  return String(s).replace(/'/g, "''");
}

function toIso(d) {
  return new Date(d).toISOString().slice(0, 19).replace("T", " ");
}

export {ALL};
