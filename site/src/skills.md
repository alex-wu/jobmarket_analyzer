---
title: Skills & Roles
toc: false
---

# Skills & Roles

```js
import * as Plot from "npm:@observablehq/plot";
import * as Inputs from "npm:@observablehq/inputs";
import {DuckDBClient} from "npm:@observablehq/duckdb";
import {html} from "npm:htl";
import {barChart} from "./components/barChart.js";
import {dataTable} from "./components/dataTable.js";
import {heatmap} from "./components/heatmap.js";
import {wordCloud} from "./components/wordCloud.js";
import {filterCard} from "./components/filterCard.js";
import {expandable} from "./components/expand.js";
import {whereClause, andClause, escape as sqlEscape} from "./components/filters.js";
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

## Role focus

Narrow the sections below to a single job title. This filter is page-local; the
card filters above carry across pages as usual.

```js
const topTitles = Array.from(
  await db.query(`
    SELECT title FROM postings
    ${andClause(where)} title IS NOT NULL
    GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 25
  `),
  (r) => r.title
);
const titlePick = view(Inputs.select(["(all)", ...topTitles], {label: "Role / title"}));
```

```js
const whereT = titlePick === "(all)" ? where : `${andClause(where)} title = '${sqlEscape(titlePick)}'`;
```

## ISCO-08 major group mix

```js
const iscoMix = Array.from(
  await db.query(`
    SELECT COALESCE(isco_major, '∅') AS isco_major,
           COUNT(*)::INT AS n
    FROM postings ${whereT}
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
    ${andClause(whereT)} salary_annual_eur_p50 IS NOT NULL AND isco_major IS NOT NULL
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

## Top skills

```js
const skillRows = Array.from(await db.query(`
  SELECT skill, COUNT(*)::INT AS n
  FROM (SELECT unnest(skills) AS skill FROM postings ${whereT})
  GROUP BY 1
  ORDER BY 2 DESC
  LIMIT 25
`));
```

${skillRows.length === 0
  ? html`<div class="card"><div>No tagged skills in current selection.</div></div>`
  : expandable(
      "Top 25 skills",
      resize((width) => barChart(skillRows, {x: "n", y: "skill", xLabel: "Postings mentioning skill", marginLeft: 220, height: 520, width})),
      (w, h) => barChart(skillRows, {x: "n", y: "skill", xLabel: "Postings mentioning skill", marginLeft: 220, height: h, width: w})
    )}

## Skill cloud

```js
const cloudRows = Array.from(await db.query(`
  SELECT skill, COUNT(*)::INT AS n
  FROM (SELECT unnest(skills) AS skill FROM postings ${whereT})
  GROUP BY 1
  ORDER BY 2 DESC
  LIMIT 60
`));
```

${cloudRows.length === 0
  ? html`<div class="card"><div>No tagged skills in current selection.</div></div>`
  : expandable(
      "Skill cloud (top 60, sized by mentions)",
      resize((width) => wordCloud(cloudRows, {width, height: 400})),
      (w, h) => {
        const holder = html`<div></div>`;
        wordCloud(cloudRows, {width: w, height: h, maxFont: 64}).then((node) => holder.append(node));
        return holder;
      }
    )}

## Filtered postings

```js
const filtered = Array.from(await db.query(`
  SELECT title, company, country, posted_at,
         salary_annual_eur_p50, salary_imputed, salary_period,
         isco_code, isco_major, isco_match_method, isco_match_score,
         source, work_arrangement, posting_url
  FROM postings
  ${whereT}
  ORDER BY posted_at DESC NULLS LAST
  LIMIT 2000
`));
```

${dataTable(filtered, {
  title: "Filtered postings",
  filename: "jobmarket-skills.csv",
  subtitle: "Rows behind the charts above, incl. the role filter (up to 2,000). CSV exports every column.",
  columns: ["title", "company", "country", "isco_major", "posted_at", "salary_annual_eur_p50"],
  header: {
    title: "Title",
    company: "Company",
    country: "Country",
    isco_major: "ISCO",
    posted_at: "Posted",
    salary_annual_eur_p50: "€p50"
  },
  format: {
    salary_annual_eur_p50: (v) => v == null ? "—" : `€${Math.round(v / 1000)}k`,
    posted_at: (v) => v == null ? "—" : new Date(v).toLocaleDateString("en-GB", {year: "numeric", month: "short", day: "2-digit"})
  },
  width: {country: 70, isco_major: 60, posted_at: 100, salary_annual_eur_p50: 80}
})}

<small>Skills are ESCO Pillar B labels matched in the posting text
(Aho-Corasick, word-boundary checked) — counts are postings mentioning the
skill at least once. See Methodology &amp; Docs.</small>
