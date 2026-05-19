---
title: Geography
toc: false
---

# Geography

```js
import * as Plot from "npm:@observablehq/plot";
import {DuckDBClient} from "npm:@observablehq/duckdb";
import {html} from "npm:htl";
import {barChart} from "./components/barChart.js";
import {filterCard} from "./components/filterCard.js";
import {expandable} from "./components/expand.js";
import {whereClause, andClause} from "./components/filters.js";

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

## Median salary by country

```js
const byCountry = Array.from(await db.query(`
  SELECT country,
         quantile_cont(salary_annual_eur_p50, 0.5) AS p50,
         COUNT(salary_annual_eur_p50)::INT AS n
  FROM postings
  ${andClause(where)} salary_annual_eur_p50 IS NOT NULL
  GROUP BY 1
  ORDER BY 2 DESC
`));
```

${byCountry.length === 0
  ? html`<div class="card"><div>No country breakdown in current selection.</div></div>`
  : expandable(
      "Median €p50 by country",
      resize((width) => barChart(byCountry, {x: "p50", y: "country", xLabel: "Median €p50", xTickFormat: (v) => `€${(v / 1000).toFixed(0)}k`, marginLeft: 50, height: 300, width})),
      (w, h) => barChart(byCountry, {x: "p50", y: "country", xLabel: "Median €p50", xTickFormat: (v) => `€${(v / 1000).toFixed(0)}k`, marginLeft: 50, height: h, width: w})
    )}

## Postings volume by country

```js
const volume = Array.from(await db.query(`
  SELECT country, COUNT(*)::INT AS n
  FROM postings
  ${andClause(where)} country IS NOT NULL
  GROUP BY 1
  ORDER BY 2 DESC
`));
```

${volume.length === 0
  ? html`<div class="card"><div>No data in current selection.</div></div>`
  : expandable(
      "Postings by country",
      resize((width) => barChart(volume, {x: "n", y: "country", xLabel: "Postings", marginLeft: 50, height: 300, width})),
      (w, h) => barChart(volume, {x: "n", y: "country", xLabel: "Postings", marginLeft: 50, height: h, width: w})
    )}

## Posting cadence

```js
const weekly = Array.from(await db.query(`
  SELECT date_trunc('week', posted_at::TIMESTAMP)::DATE AS wk,
         country,
         COUNT(*)::INT AS n
  FROM postings
  ${andClause(where)} posted_at IS NOT NULL AND country IS NOT NULL
  GROUP BY 1, 2
  ORDER BY 1
`));
```

```js
function weeklyChart(width, height = 280) {
  return Plot.plot({
    width,
    height,
    marginLeft: 50,
    color: {legend: true},
    x: {label: null, type: "time"},
    y: {label: "Postings / week", grid: true},
    marks: [
      Plot.lineY(weekly, {x: "wk", y: "n", stroke: "country", curve: "monotone-x"}),
      Plot.dot(weekly, {x: "wk", y: "n", stroke: "country", r: 3, tip: true}),
      Plot.ruleY([0])
    ]
  });
}
```

${weekly.length === 0
  ? html`<div class="card"><div>No postings in current selection.</div></div>`
  : expandable(
      "Weekly postings by country",
      resize((width) => weeklyChart(width)),
      (w, h) => weeklyChart(w, h)
    )}

<small>Week buckets are <code>date_trunc('week', posted_at)</code>; the first and last weeks are usually partial.</small>
