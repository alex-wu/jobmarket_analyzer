---
title: Quality & Coverage
toc: false
---

# Quality & Coverage

How complete is each field, how confident are the auto-tagged ones, and where does the data come from?

```js
import * as Plot from "npm:@observablehq/plot";
import * as Inputs from "npm:@observablehq/inputs";
import {DuckDBClient} from "npm:@observablehq/duckdb";
import {html} from "npm:htl";
import {barChart} from "./components/barChart.js";
import {kpiCard} from "./components/kpiCard.js";
import {filterCard} from "./components/filterCard.js";
import {expandable} from "./components/expand.js";
import {whereClause} from "./components/filters.js";

const manifest = await FileAttachment("data/manifest.json").json();
const presets = await FileAttachment("data/presets.json").json();
const db = await DuckDBClient.of({postings: FileAttachment("data/postings.parquet")});
```

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
const filters = view(filterCard({countries, iscoPresent, dateBounds: [allDates.lo, allDates.hi], presets}));
```

```js
const where = whereClause(filters);
```

## Field coverage

```js
const coverage = await db.queryRow(`
  SELECT
    COUNT(*)::INT AS n,
    COUNT(salary_annual_eur_p50)::INT AS n_salary,
    COUNT(isco_code)::INT AS n_isco,
    SUM(CASE WHEN salary_imputed THEN 1 ELSE 0 END)::INT AS n_imputed
  FROM postings ${where}
`);
const pct = (num, den) => den > 0 ? `${Math.round((num / den) * 100)}%` : "—";
```

<div class="grid grid-cols-4">
  ${kpiCard("Postings", coverage.n.toLocaleString(), `of ${manifest.postings.row_count.toLocaleString()} in snapshot`)}
  ${kpiCard("Salary disclosed", pct(coverage.n_salary, coverage.n), `${coverage.n_salary.toLocaleString()} of ${coverage.n.toLocaleString()} rows`)}
  ${kpiCard("ISCO-tagged", pct(coverage.n_isco, coverage.n), "rapidfuzz cutoff 85")}
  ${kpiCard("Salary imputed", pct(coverage.n_imputed, coverage.n_salary), `${coverage.n_imputed.toLocaleString()} of ${coverage.n_salary.toLocaleString()} salaried`)}
</div>

<small>ESCO skill tags are surfaced on the <a href="/skills">Skills &amp; Roles</a> page.</small>

## ISCO match method breakdown

```js
const iscoMatch = Array.from(await db.query(`
  SELECT COALESCE(isco_match_method, 'none') AS method, COUNT(*)::INT AS n
  FROM postings ${where}
  GROUP BY 1
  ORDER BY 2 DESC
`));
```

${iscoMatch.length === 0
  ? html`<div class="card"><div>No data in current selection.</div></div>`
  : expandable(
      "ISCO match method (rows)",
      resize((width) => barChart(iscoMatch, {x: "n", y: "method", xLabel: "Postings", marginLeft: 90, height: 220, width})),
      (w, h) => barChart(iscoMatch, {x: "n", y: "method", xLabel: "Postings", marginLeft: 90, height: h, width: w})
    )}

<small>Methods: <code>exact</code> = title hashed directly to ISCO-08, <code>fuzzy</code> = rapidfuzz partial-ratio ≥ 85, <code>none</code> = no match (title unclassified).</small>

## Source breakdown

```js
const sources = Array.from(await db.query(`
  SELECT source, COUNT(*)::INT AS n
  FROM postings ${where}
  GROUP BY 1
  ORDER BY 2 DESC
`));
```

<div class="card">
  ${Inputs.table(sources, {columns: ["source", "n"], header: {source: "Source", n: "Postings"}, width: {n: 90}})}
</div>

## Pipeline manifest

<div class="card">
  ${Inputs.table(
    [
      {field: "preset_id", value: manifest.preset_id ?? "—"},
      {field: "run_id", value: manifest.run_id ?? "—"},
      {field: "git_sha", value: manifest.git_sha ?? "—"},
      {field: "pipeline_version", value: manifest.pipeline_version ?? "—"},
      {field: "schema_version", value: manifest.schema_version ?? "—"},
      {field: "generated_at", value: manifest.generated_at ?? "—"}
    ],
    {header: {field: "Field", value: "Value"}}
  )}
</div>

<small>Daily cron at 06:00 UTC writes the next snapshot. Weekly posting cadence lives on the <a href="/">Overview</a> page.</small>
