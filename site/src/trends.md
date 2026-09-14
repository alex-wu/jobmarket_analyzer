---
title: Trends
---

# Trends

```js
import * as Plot from "npm:@observablehq/plot";
import * as Inputs from "npm:@observablehq/inputs";
import {DuckDBClient} from "npm:@observablehq/duckdb";
import {html} from "npm:htl";
import {marketPulse, derivePulse} from "./components/marketPulse.js";
import {filterCard} from "./components/filterCard.js";
import {expandable} from "./components/expand.js";
import {dataTable} from "./components/dataTable.js";
import {whereClause, andClause} from "./components/filters.js";

const presets = await FileAttachment("data/presets.json").json();
const db = await DuckDBClient.of({postings: FileAttachment("data/postings.parquet")});
```

Continuous view of the accumulated snapshot: how volume, pay, disclosure,
arrangement mix, and skill demand move week by week. The Compare page diffs two
periods; this page shows the whole path.

<div class="note" label="Read the early buckets with care">

Accumulation started mid-May 2026 — earlier postings enter only through each run's
lookback window, so early **counts** understate the market. **Share** and **median**
series are the robust signal across that boundary; treat early raw-count growth as a
collection artefact, not a market move. The first and last buckets are usually partial.

</div>

```js
const countries = Array.from(
  await db.query(`SELECT DISTINCT country FROM postings WHERE country IS NOT NULL ORDER BY 1`),
  (r) => r.country
);
const iscoPresent = Array.from(
  await db.query(`SELECT DISTINCT isco_major FROM postings WHERE isco_major IS NOT NULL ORDER BY 1`),
  (r) => r.isco_major
);
const allDates = await db.queryRow(`SELECT MIN(posted_at) AS lo, MAX(posted_at) AS hi FROM postings WHERE posted_at IS NOT NULL`);
```

```js
const filters = view(filterCard({
  countries,
  iscoPresent,
  dateBounds: [allDates.lo, allDates.hi],
  presets,
  extras: {
    granularity: Inputs.radio(["week", "month"], {label: "Granularity", value: "week"})
  }
}));
```

```js
const where = whereClause(filters);
const granularity = filters.granularity;
const periodExpr = `date_trunc('${granularity}', posted_at::TIMESTAMP)::DATE`;
```

```js
function bucketLabel(d) {
  if (d == null) return "—";
  const dt = d instanceof Date ? d : new Date(d);
  if (granularity === "month") return dt.toLocaleDateString("en-GB", {year: "numeric", month: "short"});
  return `wk of ${dt.toLocaleDateString("en-GB", {day: "2-digit", month: "short", year: "numeric"})}`;
}
const fmtK = (v) => (v == null ? "—" : `€${Math.round(v / 1000)}k`);
const fmtPct = (v) => (v == null ? "—" : `${Math.round(v * 100)}%`);
```

```js
// One row per bucket with everything the KPIs, rate charts, and the summary
// table need. Medians on <3 disclosed salaries are suppressed as noise.
const buckets = Array.from(await db.query(`
  SELECT ${periodExpr} AS bucket,
         COUNT(*)::INT AS n,
         COUNT(salary_annual_eur_p50)::INT AS n_salary,
         MEDIAN(salary_annual_eur_p50) AS med_salary,
         COUNT(work_arrangement)::INT AS n_arr,
         COUNT(*) FILTER (WHERE work_arrangement = 'remote')::INT AS n_remote,
         COUNT(*) FILTER (WHERE work_arrangement = 'hybrid')::INT AS n_hybrid,
         COUNT(*) FILTER (WHERE work_arrangement = 'onsite')::INT AS n_onsite
  FROM postings
  ${andClause(where)} posted_at IS NOT NULL
  GROUP BY 1
  ORDER BY 1
`)).map(derivePulse);
```

## Market pulse

```js
// Same rule as Overview: the bucket containing the newest posting in the
// snapshot is still filling, so the strip compares the latest *complete*
// bucket with the one before. Cutoff is over the unfiltered snapshot so the
// reference bucket does not move with filters. Charts below still plot the
// partial bucket.
const cutoff = await db.queryRow(`SELECT ${periodExpr.replace("posted_at::TIMESTAMP", "MAX(posted_at)::TIMESTAMP")} AS b FROM postings`);
const cutoffMs = +new Date(cutoff.b);
const complete = buckets.filter((b) => +new Date(b.bucket) < cutoffMs);
const latest = complete.at(-1);
const prior = complete.at(-2);
```

${marketPulse(latest, prior, {
  periodLabel: latest ? bucketLabel(latest.bucket) : "",
  priorLabel: "prior",
  emptyText: "No postings in a complete " + granularity + " for the current filter — widen the selection."
})}

<small>Latest <em>complete</em> ${granularity} vs the one before — the newest, still-filling bucket is excluded here (it is still plotted in the charts below). Same numbers as the Overview strip at week granularity. Median salary needs ≥3 disclosed <code>€p50</code> in a bucket; remote share is among arrangement-classified postings.</small>

## Volume & pay

```js
const volumeRows = Array.from(await db.query(`
  SELECT ${periodExpr} AS bucket, country, COUNT(*)::INT AS n
  FROM postings
  ${andClause(where)} posted_at IS NOT NULL AND country IS NOT NULL
  GROUP BY 1, 2
  ORDER BY 1
`));
```

```js
const salaryTrendRows = Array.from(await db.query(`
  SELECT ${periodExpr} AS bucket, country,
         COUNT(salary_annual_eur_p50)::INT AS n_sal,
         MEDIAN(salary_annual_eur_p50) AS med
  FROM postings
  ${andClause(where)} posted_at IS NOT NULL AND country IS NOT NULL
  GROUP BY 1, 2
  HAVING COUNT(salary_annual_eur_p50) >= 3
  ORDER BY 1
`));
```

```js
function volumeChart(width, height = 300) {
  return Plot.plot({
    width,
    height,
    marginLeft: 50,
    color: {legend: true},
    x: {label: null, type: "time"},
    y: {label: `Postings / ${granularity}`, grid: true},
    marks: [
      Plot.lineY(volumeRows, {x: "bucket", y: "n", stroke: "country", curve: "monotone-x"}),
      Plot.dot(volumeRows, {x: "bucket", y: "n", stroke: "country", r: 3, tip: true}),
      Plot.ruleY([0])
    ]
  });
}
function salaryTrendChart(width, height = 300) {
  return Plot.plot({
    width,
    height,
    marginLeft: 50,
    color: {legend: true},
    x: {label: null, type: "time"},
    y: {label: "Median annual €p50", grid: true, tickFormat: (v) => `€${(v / 1000).toFixed(0)}k`},
    marks: [
      Plot.lineY(salaryTrendRows, {x: "bucket", y: "med", stroke: "country", curve: "monotone-x"}),
      Plot.dot(salaryTrendRows, {x: "bucket", y: "med", stroke: "country", r: 3, tip: true, channels: {disclosed: "n_sal"}}),
      Plot.ruleY([0])
    ]
  });
}
```

<div class="grid grid-cols-2">
  ${volumeRows.length === 0
    ? html`<div class="card"><h2>Postings per ${granularity} by country</h2><div>No postings in current selection.</div></div>`
    : expandable(
        `Postings per ${granularity} by country`,
        resize((width) => volumeChart(width)),
        (w, h) => volumeChart(w, h)
      )}
  ${salaryTrendRows.length === 0
    ? html`<div class="card"><h2>Median €p50 by country</h2><div>Needs ≥3 disclosed salaries per country per bucket — none qualify.</div></div>`
    : expandable(
        "Median €p50 by country",
        resize((width) => salaryTrendChart(width)),
        (w, h) => salaryTrendChart(w, h)
      )}
</div>

<small>Volume is count-based — the accumulation caveat above applies to its early ramp. Salary points appear only where a country disclosed ≥3 salaries in the bucket; hover for the disclosed count. Imputed salaries included — see Quality &amp; Coverage.</small>

## Disclosure & arrangement

```js
const arrShareRows = buckets
  .filter((b) => b.n_arr > 0)
  .flatMap((b) => [
    {bucket: b.bucket, arrangement: "remote", share: b.n_remote / b.n_arr, n: b.n_remote},
    {bucket: b.bucket, arrangement: "hybrid", share: b.n_hybrid / b.n_arr, n: b.n_hybrid},
    {bucket: b.bucket, arrangement: "onsite", share: b.n_onsite / b.n_arr, n: b.n_onsite}
  ]);
const disclosureRows = buckets.filter((b) => b.disclosure != null);
```

```js
function disclosureChart(width, height = 300) {
  return Plot.plot({
    width,
    height,
    marginLeft: 50,
    x: {label: null, type: "time"},
    y: {label: "Share disclosing €p50", grid: true, percent: true},
    marks: [
      Plot.lineY(disclosureRows, {x: "bucket", y: "disclosure", curve: "monotone-x"}),
      Plot.dot(disclosureRows, {x: "bucket", y: "disclosure", r: 3, tip: true, channels: {postings: "n", disclosed: "n_salary"}}),
      Plot.ruleY([0])
    ]
  });
}
function arrangementChart(width, height = 300) {
  return Plot.plot({
    width,
    height,
    marginLeft: 50,
    color: {legend: true},
    x: {label: null, type: "time"},
    y: {label: "Share of classified", grid: true, percent: true},
    marks: [
      Plot.lineY(arrShareRows, {x: "bucket", y: "share", stroke: "arrangement", curve: "monotone-x"}),
      Plot.dot(arrShareRows, {x: "bucket", y: "share", stroke: "arrangement", r: 3, tip: true}),
      Plot.ruleY([0])
    ]
  });
}
```

<div class="grid grid-cols-2">
  ${disclosureRows.length === 0
    ? html`<div class="card"><h2>Salary disclosure rate</h2><div>No postings in current selection.</div></div>`
    : expandable(
        "Salary disclosure rate",
        resize((width) => disclosureChart(width)),
        (w, h) => disclosureChart(w, h)
      )}
  ${arrShareRows.length === 0
    ? html`<div class="card"><h2>Work-arrangement mix (of classified)</h2><div>No arrangement-classified postings in current selection.</div></div>`
    : expandable(
        "Work-arrangement mix (of classified)",
        resize((width) => arrangementChart(width)),
        (w, h) => arrangementChart(w, h)
      )}
</div>

<small>Arrangement shares are among classified postings only — unclassified coverage differs by country (Spanish keyword dictionary is thinner; see Quality &amp; Coverage), so cross-country level comparisons are shakier than within-country trends.</small>

## Skill demand over time

```js
const skillBucketRows = Array.from(await db.query(`
  SELECT bucket, skill, COUNT(*)::INT AS n
  FROM (
    SELECT ${periodExpr} AS bucket, unnest(skills) AS skill
    FROM postings
    ${andClause(where)} posted_at IS NOT NULL
  )
  GROUP BY 1, 2
`));
```

```js
// Top skills by total mentions in the filtered range; share = mentions ÷ the
// bucket's posting count, so accumulation-driven volume growth cancels out.
const TOP_N = 6;
const totals = new Map();
for (const r of skillBucketRows) totals.set(r.skill, (totals.get(r.skill) ?? 0) + r.n);
const topSkills = Array.from(totals.entries()).sort((a, b) => b[1] - a[1]).slice(0, TOP_N).map(([s]) => s);
const bucketN = new Map(buckets.map((b) => [+b.bucket, b.n]));
const skillShareRows = skillBucketRows
  .filter((r) => topSkills.includes(r.skill) && (bucketN.get(+r.bucket) ?? 0) > 0)
  .map((r) => ({...r, share: r.n / bucketN.get(+r.bucket)}))
  .sort((a, b) => a.bucket - b.bucket);
```

```js
function skillTrendChart(width, height = 340) {
  return Plot.plot({
    width,
    height,
    marginLeft: 50,
    color: {legend: true, domain: topSkills},
    x: {label: null, type: "time"},
    y: {label: "Share of postings mentioning skill", grid: true, percent: true},
    marks: [
      Plot.lineY(skillShareRows, {x: "bucket", y: "share", stroke: "skill", curve: "monotone-x"}),
      Plot.dot(skillShareRows, {x: "bucket", y: "share", stroke: "skill", r: 3, tip: true}),
      Plot.ruleY([0])
    ]
  });
}
```

${skillShareRows.length === 0
  ? html`<div class="card"><h2>Top-skill share over time</h2><div>No tagged skills in current selection.</div></div>`
  : expandable(
      `Top ${topSkills.length} skills — share over time`,
      resize((width) => skillTrendChart(width)),
      (w, h) => skillTrendChart(w, h)
    )}

<small>Skills come from the ESCO tagger over the truncated posting description — see <a href="./methodology#esco-skills-tagger">methodology</a>. "Top" is by total mentions within the current filter; a skill can rank top overall yet dip to zero in a sparse bucket.</small>

## Bucket summary

```js
const summaryRows = buckets.slice().reverse().map((b) => ({
  bucket: b.bucket,
  n: b.n,
  n_salary: b.n_salary,
  med_salary: b.med_salary,
  disclosure: b.disclosure,
  n_arr: b.n_arr,
  remote_share: b.remote_share
}));
```

${dataTable(summaryRows, {
  title: "Per-bucket summary",
  filename: "jobmarket-trends.csv",
  subtitle: "One row per bucket at the selected granularity, newest first; CSV exports every column.",
  columns: ["bucket", "n", "n_salary", "med_salary", "disclosure", "n_arr", "remote_share"],
  header: {
    bucket: granularity === "month" ? "Month" : "Week of",
    n: "Postings",
    n_salary: "With €p50",
    med_salary: "Median",
    disclosure: "Discl. %",
    n_arr: "Classified",
    remote_share: "Remote %"
  },
  format: {
    bucket: (v) => {
      const d = v instanceof Date ? v : new Date(v);
      return granularity === "month"
        ? d.toLocaleDateString("en-GB", {year: "numeric", month: "short"})
        : d.toLocaleDateString("en-GB", {day: "2-digit", month: "short", year: "numeric"});
    },
    med_salary: (v) => fmtK(v),
    disclosure: (v) => fmtPct(v),
    remote_share: (v) => fmtPct(v)
  },
  width: {bucket: 120}
})}
