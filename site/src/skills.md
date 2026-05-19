---
title: Skills & Roles
toc: false
---

# Skills & Roles

```js
import * as Plot from "npm:@observablehq/plot";
import {DuckDBClient} from "npm:@observablehq/duckdb";
import {html} from "npm:htl";
import {barChart} from "./components/barChart.js";
import {heatmap} from "./components/heatmap.js";
import {filterCard} from "./components/filterCard.js";
import {expandable} from "./components/expand.js";
import {whereClause, andClause} from "./components/filters.js";
import {iscoMajorLabel} from "./components/isco.js";

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

## Top titles

```js
const titles = Array.from(await db.query(`
  SELECT title, COUNT(*)::INT AS n
  FROM postings
  ${andClause(where)} title IS NOT NULL
  GROUP BY 1
  ORDER BY 2 DESC
  LIMIT 15
`));
```

${titles.length === 0
  ? html`<div class="card"><div>No titles in current selection.</div></div>`
  : expandable(
      "Top 15 titles",
      resize((width) => barChart(titles, {x: "n", y: "title", xLabel: "Postings", marginLeft: 220, height: 380, width})),
      (w, h) => barChart(titles, {x: "n", y: "title", xLabel: "Postings", marginLeft: 220, height: h, width: w})
    )}

## ISCO-08 major group mix

```js
const iscoMix = Array.from(
  await db.query(`
    SELECT COALESCE(isco_major, '∅') AS isco_major,
           COUNT(*)::INT AS n
    FROM postings ${where}
    GROUP BY 1
    ORDER BY 2 DESC
  `),
  (d) => ({...d, label: d.isco_major === "∅" ? "Unclassified" : iscoMajorLabel(d.isco_major)})
);
```

${iscoMix.length === 0
  ? html`<div class="card"><div>No ISCO breakdown in current selection.</div></div>`
  : expandable(
      "ISCO-08 major group mix",
      resize((width) => barChart(iscoMix, {x: "n", y: "label", xLabel: "Postings", marginLeft: 220, height: 380, width})),
      (w, h) => barChart(iscoMix, {x: "n", y: "label", xLabel: "Postings", marginLeft: 220, height: h, width: w})
    )}

## Country × ISCO median salary

```js
const heatRows = Array.from(
  await db.query(`
    SELECT country,
           isco_major,
           quantile_cont(salary_annual_eur_p50, 0.5) AS p50,
           COUNT(salary_annual_eur_p50)::INT AS n
    FROM postings
    ${andClause(where)} salary_annual_eur_p50 IS NOT NULL AND isco_major IS NOT NULL
    GROUP BY 1, 2
    HAVING COUNT(*) >= 3
    ORDER BY 1, 2
  `),
  (d) => ({...d, iscoLabel: iscoMajorLabel(d.isco_major)})
);
```

${heatRows.length === 0
  ? html`<div class="card"><div>Heatmap needs at least 3 salaried + ISCO-tagged postings per cell. Loosen the filter to see it populate.</div></div>`
  : expandable(
      "Country × ISCO median €p50",
      resize((width) => heatmap(heatRows, {x: "country", y: "iscoLabel", value: "p50", valueLabel: "Median €p50", valueFormat: (v) => `€${(v / 1000).toFixed(0)}k`, marginLeft: 220, height: Math.max(220, 36 * new Set(heatRows.map((d) => d.iscoLabel)).size), width})),
      (w, h) => heatmap(heatRows, {x: "country", y: "iscoLabel", value: "p50", valueLabel: "Median €p50", valueFormat: (v) => `€${(v / 1000).toFixed(0)}k`, marginLeft: 220, height: h, width: w})
    )}

<small>Skills extraction (ESCO Pillar B Aho-Corasick tagger) is in pipeline but not yet surfaced here as a chart — see Methodology &amp; Docs.</small>
