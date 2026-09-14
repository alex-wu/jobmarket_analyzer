import {html} from "npm:htl";
import {kpiCard} from "./kpiCard.js";
import {deltaSub} from "./deltaSub.js";

const fmtK = (v) => (v == null ? "—" : `€${Math.round(v / 1000)}k`);
const fmtPct = (v) => (v == null ? "—" : `${Math.round(v * 100)}%`);

// Derive the pulse metrics from one aggregated period row
// {n, n_salary, med_salary, n_arr, n_remote}. Medians on <3 disclosed salaries
// are suppressed as noise; shares are null when the denominator is empty.
export function derivePulse(r) {
  return {
    ...r,
    med_salary: r.n_salary >= 3 ? r.med_salary : null,
    disclosure: r.n > 0 ? r.n_salary / r.n : null,
    remote_share: r.n_arr > 0 ? r.n_remote / r.n_arr : null
  };
}

// Four-card KPI strip: latest complete period vs the one before. Used by
// Overview and Trends so both pages report the same numbers for the same
// filter. `latest` / `prior` are derivePulse() rows (prior may be undefined).
export function marketPulse(latest, prior, {periodLabel, priorLabel = "prior", emptyText}) {
  if (latest == null) {
    return html`<div class="warning" label="No complete period">${emptyText}</div>`;
  }
  const d = (a, b, opts) => deltaSub(a, b, {...opts, label: priorLabel, missing: `no ${priorLabel}`});
  return html`<div class="grid grid-cols-4">
    ${kpiCard(`Postings — ${periodLabel}`, latest.n.toLocaleString(), d(prior?.n, latest.n, {kind: "pct", fmt: (v) => v.toLocaleString()}))}
    ${kpiCard("Median salary", fmtK(latest.med_salary), d(prior?.med_salary, latest.med_salary, {kind: "pct", fmt: fmtK}))}
    ${kpiCard("Disclose salary", fmtPct(latest.disclosure), d(prior?.disclosure, latest.disclosure, {kind: "pp", fmt: fmtPct}))}
    ${kpiCard("Remote (of classified)", fmtPct(latest.remote_share), d(prior?.remote_share, latest.remote_share, {kind: "pp", fmt: fmtPct}))}
  </div>`;
}
