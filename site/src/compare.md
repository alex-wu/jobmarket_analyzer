---
title: Compare Periods
---

# Compare Periods

```js
import * as Plot from "npm:@observablehq/plot";
import * as Inputs from "npm:@observablehq/inputs";
import {DuckDBClient} from "npm:@observablehq/duckdb";
import {html} from "npm:htl";
import {kpiCard} from "./components/kpiCard.js";
import {expandable} from "./components/expand.js";
import {iscoMajorLabel} from "./components/isco.js";

const db = await DuckDBClient.of({postings: FileAttachment("data/postings.parquet")});
```

Pick two time slices of the snapshot and see how the market moved between them:
volume, pay, disclosure, arrangement mix, and which skills are gaining or losing ground.

<div class="note" label="Read the deltas with care">

Accumulation started mid-May 2026 — earlier postings enter only through each run's
lookback window, so early-period **counts** understate the market. The **share**-based
deltas (percentage points of the period's own postings) are the robust signal;
treat raw-count deltas across that boundary as collection artefacts, not market moves.

</div>

## Periods

```js
const granularity = view(Inputs.radio(["quarter", "month", "week"], {label: "Granularity", value: "month"}));
```

```js
const periodExpr = `date_trunc('${granularity}', posted_at::TIMESTAMP)::DATE`;
const buckets = Array.from(await db.query(`
  SELECT ${periodExpr}::VARCHAR AS bucket, COUNT(*)::INT AS n
  FROM postings
  WHERE posted_at IS NOT NULL
  GROUP BY 1
  ORDER BY 1
`));
```

```js
function bucketLabel(b) {
  const d = new Date(`${b}T00:00:00Z`);
  if (granularity === "quarter") return `Q${Math.floor(d.getUTCMonth() / 3) + 1} ${d.getUTCFullYear()}`;
  if (granularity === "month") return d.toLocaleDateString("en-GB", {year: "numeric", month: "short"});
  return `wk of ${d.toLocaleDateString("en-GB", {day: "2-digit", month: "short", year: "numeric"})}`;
}
const bucketIds = buckets.map((b) => b.bucket);
const fmtBucket = (b) => `${bucketLabel(b)} — ${buckets.find((x) => x.bucket === b)?.n ?? 0} postings`;
```

```js
const periodA = view(Inputs.select(bucketIds, {
  label: "Period A (baseline)",
  format: fmtBucket,
  value: bucketIds.at(-2) ?? bucketIds.at(-1)
}));
const periodB = view(Inputs.select(bucketIds, {
  label: "Period B (compare)",
  format: fmtBucket,
  value: bucketIds.at(-1)
}));
```

```js
const labelA = bucketLabel(periodA);
const labelB = bucketLabel(periodB);
const inPeriods = `${periodExpr} IN (DATE '${periodA}', DATE '${periodB}')`;
const periodCase = `CASE WHEN ${periodExpr} = DATE '${periodA}' THEN 'A' ELSE 'B' END`;
```

${periodA === periodB
  ? html`<div class="warning" label="Same period twice">Period A and Period B are identical — every delta below is zero by construction. Pick two different periods.</div>`
  : ""}

## What moved

```js
const kpiRows = Array.from(await db.query(`
  SELECT ${periodCase} AS period,
         COUNT(*)::INT AS n,
         COUNT(salary_annual_eur_p50)::INT AS n_salary,
         MEDIAN(salary_annual_eur_p50) AS med_salary,
         COUNT(work_arrangement)::INT AS n_arr,
         COUNT(*) FILTER (WHERE work_arrangement = 'remote')::INT AS n_remote
  FROM postings
  WHERE posted_at IS NOT NULL AND ${inPeriods}
  GROUP BY 1
`));
const empty = {n: 0, n_salary: 0, med_salary: null, n_arr: 0, n_remote: 0};
const A = kpiRows.find((r) => r.period === "A") ?? empty;
const B = kpiRows.find((r) => r.period === "B") ?? empty;
```

```js
const fmtK = (v) => (v == null ? "—" : `€${Math.round(v / 1000)}k`);
const pct = (num, den) => (den > 0 ? num / den : null);
const fmtPct = (v) => (v == null ? "—" : `${Math.round(v * 100)}%`);
// Delta sub-line: "A → B" plus the movement, sign always shown.
function deltaSub(a, b, {kind, fmt = String}) {
  if (a == null || b == null) return `${labelA}: ${a == null ? "—" : fmt(a)}`;
  const arrow = b > a ? "▲" : b < a ? "▼" : "＝";
  const move = kind === "pp"
    ? `${(b - a) >= 0 ? "+" : ""}${((b - a) * 100).toFixed(1)} pp`
    : a === 0 ? "n/a" : `${(b - a) >= 0 ? "+" : ""}${Math.round(((b - a) / a) * 100)}%`;
  return `${labelA}: ${fmt(a)} · ${arrow} ${move}`;
}
```

<div class="grid grid-cols-4">
  ${kpiCard(`Postings — ${labelB}`, B.n.toLocaleString(), deltaSub(A.n, B.n, {kind: "pct", fmt: (v) => v.toLocaleString()}))}
  ${kpiCard(`Median salary — ${labelB}`, fmtK(B.med_salary), deltaSub(A.med_salary, B.med_salary, {kind: "pct", fmt: fmtK}))}
  ${kpiCard(`Disclose salary — ${labelB}`, fmtPct(pct(B.n_salary, B.n)), deltaSub(pct(A.n_salary, A.n), pct(B.n_salary, B.n), {kind: "pp", fmt: fmtPct}))}
  ${kpiCard(`Remote (of classified) — ${labelB}`, fmtPct(pct(B.n_remote, B.n_arr)), deltaSub(pct(A.n_remote, A.n_arr), pct(B.n_remote, B.n_arr), {kind: "pp", fmt: fmtPct}))}
</div>

<small>Median salary is over disclosed <code>€p50</code> only (${A.n_salary.toLocaleString()} postings in ${labelA}, ${B.n_salary.toLocaleString()} in ${labelB}); remote share is among arrangement-classified postings (${A.n_arr.toLocaleString()} / ${B.n_arr.toLocaleString()}).</small>

## Skills gaining & losing ground

```js
const skillCounts = Array.from(await db.query(`
  SELECT period, skill, COUNT(*)::INT AS n
  FROM (
    SELECT ${periodCase} AS period, unnest(skills) AS skill
    FROM postings
    WHERE posted_at IS NOT NULL AND ${inPeriods}
  )
  GROUP BY 1, 2
`));
```

```js
// Δ share in percentage points of each period's own posting count, so the
// accumulation-driven volume growth cancels out. Noise guard: ≥3 mentions
// across both periods.
const bySkill = new Map();
for (const r of skillCounts) {
  const e = bySkill.get(r.skill) ?? {skill: r.skill, nA: 0, nB: 0};
  if (r.period === "A") e.nA = r.n; else e.nB = r.n;
  bySkill.set(r.skill, e);
}
const movers = Array.from(bySkill.values(), (e) => ({
  ...e,
  delta: (A.n > 0 && B.n > 0) ? (e.nB / B.n - e.nA / A.n) * 100 : 0,
  direction: (e.nB / (B.n || 1) - e.nA / (A.n || 1)) >= 0 ? "gaining" : "losing"
}))
  .filter((e) => e.nA + e.nB >= 3 && e.delta !== 0)
  .sort((a, b) => b.delta - a.delta);
const topMovers = [...movers.slice(0, 10), ...movers.slice(-10)]
  .filter((e, i, arr) => arr.findIndex((x) => x.skill === e.skill) === i);
```

```js
function moversChart(width, height = 460) {
  return Plot.plot({
    width,
    height,
    marginLeft: 220,
    x: {label: `Δ share of postings (pp), ${labelA} → ${labelB}`, grid: true},
    y: {label: null},
    color: {legend: true},
    marks: [
      Plot.axisY({label: null, lineWidth: (220 - 30) / 10, textOverflow: "ellipsis"}),
      Plot.barX(topMovers, {
        x: "delta",
        y: "skill",
        fill: "direction",
        sort: {y: "x", reverse: true},
        tip: true,
        channels: {[`${labelA}`]: "nA", [`${labelB}`]: "nB"}
      }),
      Plot.ruleX([0])
    ]
  });
}
```

${topMovers.length === 0
  ? html`<div class="card"><h2>Top skill movers</h2><div>Not enough tagged skills in these periods (≥3 combined mentions required).</div></div>`
  : expandable(
      "Top skill movers",
      resize((width) => moversChart(width)),
      (w, h) => moversChart(w, h)
    )}

<small>Share = postings mentioning the skill ÷ postings in that period. A skill can gain share while losing absolute mentions, and vice versa — hover for the underlying counts.</small>

## Mix shifts

```js
const iscoRows = Array.from(await db.query(`
  SELECT ${periodCase} AS period,
         CASE WHEN isco_code IS NULL THEN NULL ELSE SUBSTR(isco_code, 1, 1) END AS isco_major,
         COUNT(*)::INT AS n
  FROM postings
  WHERE posted_at IS NOT NULL AND ${inPeriods}
  GROUP BY 1, 2
`)).map((r) => ({
  period: r.period === "A" ? labelA : labelB,
  label: iscoMajorLabel(r.isco_major),
  share: r.period === "A" ? (A.n ? r.n / A.n : 0) : (B.n ? r.n / B.n : 0),
  n: r.n
}));
```

```js
const arrRows = Array.from(await db.query(`
  SELECT ${periodCase} AS period,
         COALESCE(work_arrangement, 'unknown') AS arrangement,
         COUNT(*)::INT AS n
  FROM postings
  WHERE posted_at IS NOT NULL AND ${inPeriods}
  GROUP BY 1, 2
`)).map((r) => ({
  period: r.period === "A" ? labelA : labelB,
  arrangement: r.arrangement,
  share: r.period === "A" ? (A.n ? r.n / A.n : 0) : (B.n ? r.n / B.n : 0),
  n: r.n
}));
```

```js
// Grouped horizontal bars: one facet row per category, one bar per period.
function mixChart(rows, {y, width, height = 300, xLabel = "Share of period's postings"}) {
  return Plot.plot({
    width,
    height,
    marginLeft: 220,
    x: {label: xLabel, grid: true, percent: true},
    y: {axis: null, label: null},
    fy: {label: null},
    color: {legend: true, domain: [labelA, labelB]},
    marks: [
      Plot.barX(rows, {x: "share", y: "period", fy: y, fill: "period", tip: true, sort: {fy: "-x"}}),
      Plot.ruleX([0])
    ]
  });
}
```

<div class="grid grid-cols-2">
  ${iscoRows.length === 0
    ? html`<div class="card"><h2>ISCO-08 major group mix</h2><div>No postings in these periods.</div></div>`
    : expandable(
        "ISCO-08 major group mix",
        resize((width) => mixChart(iscoRows, {y: "label", width})),
        (w, h) => mixChart(iscoRows, {y: "label", width: w, height: h})
      )}
  ${arrRows.length === 0
    ? html`<div class="card"><h2>Work-arrangement mix (incl. unknown)</h2><div>No postings in these periods.</div></div>`
    : expandable(
        "Work-arrangement mix (incl. unknown)",
        resize((width) => mixChart(arrRows, {y: "arrangement", width})),
        (w, h) => mixChart(arrRows, {y: "arrangement", width: w, height: h})
      )}
</div>

## Median salary by country

```js
const salaryRows = Array.from(await db.query(`
  SELECT ${periodCase} AS period,
         country,
         COUNT(salary_annual_eur_p50)::INT AS n_sal,
         MEDIAN(salary_annual_eur_p50) AS med
  FROM postings
  WHERE posted_at IS NOT NULL AND country IS NOT NULL AND ${inPeriods}
  GROUP BY 1, 2
  HAVING COUNT(salary_annual_eur_p50) >= 3
`)).map((r) => ({
  period: r.period === "A" ? labelA : labelB,
  country: r.country,
  med: r.med,
  n_sal: r.n_sal
}));
```

```js
function salaryChart(width, height = 300) {
  return Plot.plot({
    width,
    height,
    marginLeft: 80,
    x: {label: "Median annual €p50", grid: true, tickFormat: (v) => `€${(v / 1000).toFixed(0)}k`},
    y: {axis: null, label: null},
    fy: {label: null},
    color: {legend: true, domain: [labelA, labelB]},
    marks: [
      Plot.barX(salaryRows, {x: "med", y: "period", fy: "country", fill: "period", tip: true, channels: {disclosed: "n_sal"}}),
      Plot.ruleX([0])
    ]
  });
}
```

${salaryRows.length === 0
  ? html`<div class="card"><h2>Median €p50 by country</h2><div>Needs at least 3 disclosed salaries per country per period — none qualify in this selection.</div></div>`
  : expandable(
      "Median €p50 by country",
      resize((width) => salaryChart(width)),
      (w, h) => salaryChart(w, h)
    )}

<small>Countries appear only with ≥3 disclosed salaries in a period; a country with one bar qualified in only one of the two periods. Imputed salaries are included — see Quality &amp; Coverage for imputation rates.</small>
