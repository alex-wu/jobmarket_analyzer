---
title: Skills & Roles
---

# Skills & Roles

```js
import * as Plot from "npm:@observablehq/plot";
import * as Inputs from "npm:@observablehq/inputs";
import {html} from "npm:htl";
import {openDb, loadBootstrap} from "./components/db.js";
import {barChart} from "./components/barChart.js";
import {dataTable} from "./components/dataTable.js";
import {heatmap} from "./components/heatmap.js";
import {filterCard} from "./components/filterCard.js";
import {expandable} from "./components/expand.js";
import {whereClause, andClause, escape as sqlEscape} from "./components/filters.js";
import {iscoMajorLabel} from "./components/isco.js";

const manifest = await FileAttachment("data/manifest.json").json();
const presets = await FileAttachment("data/presets.json").json();
const db = await openDb();
```

```js
const {countries, iscoPresent, allDates} = await loadBootstrap(db);
// Options for the page-scoped Role/title filter. Unfiltered on purpose: the
// select lives inside the filter card, so deriving options from the other
// filters would be circular.
const topTitles = Array.from(
  await db.query(`SELECT title FROM postings WHERE title IS NOT NULL GROUP BY 1 ORDER BY COUNT(*) DESC, 1 LIMIT 25`),
  (r) => r.title
);
```

```js
const filters = view(filterCard({
  countries,
  iscoPresent,
  dateBounds: [allDates.lo, allDates.hi],
  presets,
  extras: {title: Inputs.select(["(all)", ...topTitles], {label: "Role / title (this page)"})}
}));
```

```js
const where = whereClause(filters);
const whereT = !filters.title || filters.title === "(all)"
  ? where
  : `${andClause(where)} title = '${sqlEscape(filters.title)}'`;
```

## Top titles & top skills

```js
const titles = Array.from(await db.query(`
  SELECT title, COUNT(*) AS n
  FROM postings
  ${andClause(where)} title IS NOT NULL
  GROUP BY 1
  ORDER BY 2 DESC, 1
  LIMIT 15
`));
```

```js
const skillRows = Array.from(await db.query(`
  SELECT skill, COUNT(*) AS n
  FROM posting_skills JOIN postings ON postings.id = posting_skills.posting_id
  ${whereT}
  GROUP BY 1
  ORDER BY 2 DESC, 1
  LIMIT 25
`));
```

<div class="grid grid-cols-2">
  ${titles.length === 0
    ? html`<div class="card"><h2>Top 15 titles</h2><div>No titles in current selection.</div></div>`
    : expandable(
        "Top 15 titles",
        resize((width) => barChart(titles, {x: "n", y: "title", xLabel: "Postings", marginLeft: 220, height: 460, width})),
        (w, h) => barChart(titles, {x: "n", y: "title", xLabel: "Postings", marginLeft: 220, height: h, width: w})
      )}
  ${skillRows.length === 0
    ? html`<div class="card"><h2>Top 25 skills</h2><div>No tagged skills in current selection.</div></div>`
    : expandable(
        "Top 25 skills",
        resize((width) => barChart(skillRows, {x: "n", y: "skill", xLabel: "Postings mentioning skill", marginLeft: 220, height: 460, width})),
        (w, h) => barChart(skillRows, {x: "n", y: "skill", xLabel: "Postings mentioning skill", marginLeft: 220, height: h, width: w})
      )}
</div>

## ISCO-08 mix & median salary

```js
const iscoMix = Array.from(
  await db.query(`
    SELECT COALESCE(isco_major, '∅') AS isco_major,
           COUNT(*) AS n
    FROM postings ${whereT}
    GROUP BY 1
    ORDER BY 2 DESC
  `),
  (d) => ({...d, label: d.isco_major === "∅" ? "Unclassified" : iscoMajorLabel(d.isco_major)})
);
```

```js
const heatRows = Array.from(
  await db.query(`
    SELECT country,
           isco_major,
           median(salary_annual_eur_p50) AS p50,
           COUNT(salary_annual_eur_p50) AS n
    FROM postings
    ${andClause(whereT)} salary_annual_eur_p50 IS NOT NULL AND isco_major IS NOT NULL
    GROUP BY 1, 2
    HAVING COUNT(*) >= 3
    ORDER BY 1, 2
  `),
  (d) => ({...d, iscoLabel: iscoMajorLabel(d.isco_major)})
);
```

<div class="grid grid-cols-2">
  ${iscoMix.length === 0
    ? html`<div class="card"><h2>ISCO-08 major group mix</h2><div>No ISCO breakdown in current selection.</div></div>`
    : expandable(
        "ISCO-08 major group mix",
        resize((width) => barChart(iscoMix, {x: "n", y: "label", xLabel: "Postings", marginLeft: 220, height: 380, width})),
        (w, h) => barChart(iscoMix, {x: "n", y: "label", xLabel: "Postings", marginLeft: 220, height: h, width: w})
      )}
  ${heatRows.length === 0
    ? html`<div class="card"><h2>Country × ISCO median €p50</h2><div>Heatmap needs at least 3 salaried + ISCO-tagged postings per cell. Loosen the filter to see it populate.</div></div>`
    : expandable(
        "Country × ISCO median €p50",
        resize((width) => heatmap(heatRows, {x: "country", y: "iscoLabel", value: "p50", valueLabel: "Median €p50", valueFormat: (v) => `€${(v / 1000).toFixed(0)}k`, marginLeft: 220, height: Math.max(220, 36 * new Set(heatRows.map((d) => d.iscoLabel)).size), width})),
        (w, h) => heatmap(heatRows, {x: "country", y: "iscoLabel", value: "p50", valueLabel: "Median €p50", valueFormat: (v) => `€${(v / 1000).toFixed(0)}k`, marginLeft: 220, height: h, width: w})
      )}
</div>

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
