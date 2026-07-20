---
title: Geography
toc: false
---

# Geography

```js
import * as Inputs from "npm:@observablehq/inputs";
import {DuckDBClient} from "npm:@observablehq/duckdb";
import {html} from "npm:htl";
import {choropleth} from "./components/choropleth.js";
import {filterCard} from "./components/filterCard.js";
import {expandable} from "./components/expand.js";
import {whereClause, andClause} from "./components/filters.js";

const manifest = await FileAttachment("data/manifest.json").json();
const presets = await FileAttachment("data/presets.json").json();
const europe = await FileAttachment("data/europe.json").json();
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

## Map

```js
const metric = view(Inputs.select(
  new Map([
    ["Postings volume", "n"],
    ["Median salary €p50", "p50"]
  ]),
  {label: "Metric"}
));
```

```js
const byCountry = Array.from(await db.query(`
  SELECT country,
         COUNT(*)::INT AS n,
         quantile_cont(salary_annual_eur_p50, 0.5) AS p50
  FROM postings
  ${andClause(where)} country IS NOT NULL
  GROUP BY 1
`));
```

```js
const valueByIso2 = new Map(
  byCountry.filter((d) => d[metric] != null).map((d) => [d.country, Number(d[metric])])
);
const metricLabel = metric === "p50" ? "Median €p50" : "Postings";
const metricFormat = metric === "p50"
  ? (v) => `€${(v / 1000).toFixed(0)}k`
  : (v) => v.toLocaleString();
```

${valueByIso2.size === 0
  ? html`<div class="card"><div>No data in current selection.</div></div>`
  : expandable(
      metricLabel + " by country",
      resize((width) => choropleth(europe, valueByIso2, {label: metricLabel, format: metricFormat, width})),
      (w, h) => choropleth(europe, valueByIso2, {label: metricLabel, format: metricFormat, width: w, height: h})
    )}

<small>The map shows countries present in the current filter selection; gray
outlines mean no data (not zero — the preset only ingests some countries).
Median salary appears only for countries with disclosed salaries.</small>
