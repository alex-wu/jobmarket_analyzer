---
title: Work Arrangement
toc: false
---

# Work Arrangement

```js
import * as Plot from "npm:@observablehq/plot";
import {DuckDBClient} from "npm:@observablehq/duckdb";
import {html} from "npm:htl";
import {filterCard} from "./components/filterCard.js";
import {expandable} from "./components/expand.js";
import {whereClause, andClause} from "./components/filters.js";

const manifest = await FileAttachment("data/manifest.json").json();
const presets = await FileAttachment("data/presets.json").json();
const db = await DuckDBClient.of({postings: FileAttachment("data/postings.parquet")});

// Fixed category order + stable colours across every chart on this page.
const ORDER = ["remote", "hybrid", "onsite", "unknown"];
const color = {domain: ORDER, legend: true};
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

```js
const cov = await db.queryRow(`
  SELECT COUNT(*)::INT AS total, COUNT(work_arrangement)::INT AS classified
  FROM postings ${where}
`);
const covPct = cov.total > 0 ? Math.round((cov.classified / cov.total) * 100) : 0;
```

<div class="card">
  <strong>Coverage caveat.</strong> Only <strong>${cov.classified}</strong> of
  <strong>${cov.total}</strong> postings in this selection
  (<strong>${covPct}%</strong>) disclose a work arrangement. Arrangement is
  inferred from the posting text (remote / hybrid / on-site keywords); the
  remaining <strong>${cov.total - cov.classified}</strong> are shown as
  <code>unknown</code> — a genuine gap, not a fourth mode. Read shares against
  the classified base, not the whole market.
</div>

## Overall breakdown

```js
const overall = Array.from(await db.query(`
  SELECT COALESCE(work_arrangement, 'unknown') AS arrangement, COUNT(*)::INT AS n
  FROM postings ${where}
  GROUP BY 1
`));
```

```js
function overallChart(width, height = 260) {
  return Plot.plot({
    width,
    height,
    marginLeft: 70,
    marginRight: 36,
    color,
    x: {label: "Postings", grid: true},
    y: {label: null, domain: ORDER},
    marks: [
      Plot.barX(overall, {x: "n", y: "arrangement", fill: "arrangement", tip: true}),
      Plot.text(overall, {x: "n", y: "arrangement", text: (d) => `${d.n}`, dx: 6, textAnchor: "start"}),
      Plot.ruleX([0])
    ]
  });
}
```

${overall.length === 0
  ? html`<div class="card"><div>No postings in current selection.</div></div>`
  : expandable(
      "Postings by arrangement (incl. unknown)",
      resize((width) => overallChart(width)),
      (w, h) => overallChart(w, h)
    )}

## By country

Composition within each country, **including the unknown share** so the sparse
coverage stays visible.

```js
const byCountry = Array.from(await db.query(`
  SELECT country, COALESCE(work_arrangement, 'unknown') AS arrangement, COUNT(*)::INT AS n
  FROM postings
  ${andClause(where)} country IS NOT NULL
  GROUP BY 1, 2
`));
```

```js
function byCountryChart(width, height = 300, {normalize = true} = {}) {
  return Plot.plot({
    width,
    height,
    marginLeft: 60,
    color,
    x: {label: normalize ? "Share of postings" : "Postings", grid: true, percent: normalize},
    y: {label: null},
    marks: [
      Plot.barX(byCountry, {
        x: "n",
        y: "country",
        fill: "arrangement",
        offset: normalize ? "normalize" : null,
        order: ORDER,
        tip: true
      }),
      Plot.ruleX([0])
    ]
  });
}
```

${byCountry.length === 0
  ? html`<div class="card"><div>No country breakdown in current selection.</div></div>`
  : expandable(
      "Arrangement composition by country (incl. unknown)",
      resize((width) => byCountryChart(width)),
      (w, h) => byCountryChart(w, h)
    )}

## Among classified only

Excludes the <code>unknown</code> rows entirely — this is the mix **among the
${covPct}% that disclose an arrangement**, and should not be read as the market
mix. With so few classified rows, treat small countries with caution.

```js
const classified = Array.from(await db.query(`
  SELECT country, work_arrangement AS arrangement, COUNT(*)::INT AS n
  FROM postings
  ${andClause(where)} country IS NOT NULL AND work_arrangement IS NOT NULL
  GROUP BY 1, 2
`));
```

```js
function classifiedChart(width, height = 300) {
  return Plot.plot({
    width,
    height,
    marginLeft: 60,
    color: {domain: ["remote", "hybrid", "onsite"], legend: true},
    x: {label: "Share among classified", grid: true, percent: true},
    y: {label: null},
    marks: [
      Plot.barX(classified, {
        x: "n",
        y: "country",
        fill: "arrangement",
        offset: "normalize",
        order: ["remote", "hybrid", "onsite"],
        tip: true
      }),
      Plot.ruleX([0])
    ]
  });
}
```

${classified.length === 0
  ? html`<div class="card"><div>No classified postings in current selection.</div></div>`
  : expandable(
      "Composition among classified postings",
      resize((width) => classifiedChart(width)),
      (w, h) => classifiedChart(w, h)
    )}

<small>Arrangement is a keyword inference over the posting text
(<code>remote</code> / <code>hybrid</code> / <code>on-site</code>); it is not a
structured Adzuna field. Coverage rises when the <code>/details/</code> fetcher
is enabled for a preset. See <a href="/methodology">Methodology</a>.</small>
