---
title: Salary Distribution
style: chips.css
---

# Salary Distribution

```js
import * as Inputs from "npm:@observablehq/inputs";
import * as d3 from "npm:d3";
import {html} from "npm:htl";
import {openDb, loadBootstrap} from "./components/db.js";
import {chipFilterBar} from "./components/chipFilters.js";
import {distributionChart, summarize} from "./components/distribution.js";
import {dataTable} from "./components/dataTable.js";
import {kpiCard} from "./components/kpiCard.js";
import {whereClause, andClause} from "./components/filters.js";
import {iscoMajorLabel} from "./components/isco.js";

const presets = await FileAttachment("data/presets.json").json();
const db = await openDb();
```

```js
const {countries, iscoPresent, allDates} = await loadBootstrap(db);
// Skill chips: the most-mentioned skills, minus any skill found in over half
// of all postings (too generic to filter on). Unfiltered on purpose — the
// chips live inside the filter bar.
const topSkills = await db.query(`
  SELECT skill, COUNT(DISTINCT posting_id) AS n
  FROM posting_skills
  GROUP BY 1
  HAVING COUNT(DISTINCT posting_id) <= 0.5 * (SELECT COUNT(*) FROM postings)
  ORDER BY 2 DESC, 1
  LIMIT 12
`);
```

Every dot is one posting with a salary. The curve above the dots is the shape of the
distribution, the box below marks the median and the middle 50%. Hover a dot for the
posting, click to open it.

<div class="note" label="Two kinds of salary">

**Stated in ad** — the employer put a salary in the posting. **Estimated by Adzuna** —
the posting gave no salary, so Adzuna (the job board this data comes from) predicted one
from similar ads. Estimates are useful for the overall shape but are not what any
employer offered; use the *Adzuna estimates* filter to leave them out.

</div>

```js
const SPLITS = {
  none: {label: "None", group: () => "All postings"},
  country: {label: "Country", group: (d) => d.country ?? "Unknown country"},
  arrangement: {label: "Arrangement", group: (d) => d.work_arrangement ?? "unknown"},
  isco: {label: "ISCO group", group: (d) => iscoMajorLabel(d.isco_major)}
};

const filters = view(chipFilterBar({
  countries,
  iscoPresent,
  dateBounds: [allDates.lo, allDates.hi],
  presets,
  skills: topSkills,
  extras: {
    split: Inputs.radio(Object.keys(SPLITS), {label: "Split rows by", value: "none", format: (k) => SPLITS[k].label}),
    imputed: Inputs.radio(["include", "exclude"], {label: "Adzuna estimates", value: "include", format: (k) => (k === "include" ? "Include" : "Exclude")}),
    axis: Inputs.radio(["full", "zoom"], {label: "Salary axis", value: "full", format: (k) => (k === "full" ? "Full range" : "1st–99th percentile")})
  }
}));
```

```js
const where = whereClause(filters);
const total = (await db.queryRow(`SELECT COUNT(*) AS n FROM postings ${where}`)).n;
// Stated first, then by salary: within each block the stated salaries sit
// next to the baseline and Adzuna's estimates hang below them.
// (`salary_imputed` is Adzuna's `salary_is_predicted` flag.)
const salaried = await db.query(`
  SELECT title, company, country, posted_at,
         salary_annual_eur_p50, salary_imputed,
         isco_major, work_arrangement, posting_url
  FROM postings
  ${andClause(where)} salary_annual_eur_p50 IS NOT NULL
  ORDER BY salary_imputed, salary_annual_eur_p50
`);
```

```js
const MIN_GROUP = 3;
const KINDS = ["Stated in ad", "Estimated by Adzuna"];
const rows = salaried
  .filter((d) => filters.imputed === "include" || !d.salary_imputed)
  .map((d) => ({
    ...d,
    value: d.salary_annual_eur_p50,
    kind: KINDS[d.salary_imputed ? 1 : 0],
    url: d.posting_url,
    group: SPLITS[filters.split].group(d)
  }));
const summary = summarize(rows, {minCount: filters.split === "none" ? 1 : MIN_GROUP});
const dropped = new Set(rows.map((d) => d.group)).size - summary.length;

const values = Float64Array.from(rows, (d) => d.value).sort();
const overall = {
  n: values.length,
  q1: d3.quantileSorted(values, 0.25),
  med: d3.quantileSorted(values, 0.5),
  q3: d3.quantileSorted(values, 0.75)
};
const domain = filters.axis === "zoom"
  ? [d3.quantileSorted(values, 0.01), d3.quantileSorted(values, 0.99)]
  : [values[0], values.at(-1)];
const offAxis = rows.filter((d) => d.value < domain[0] || d.value > domain[1]).length;
const nImputed = rows.filter((d) => d.salary_imputed).length;
```

```js
const fmtK = (v) => (v == null ? "—" : `€${Math.round(v / 1000)}k`);
const fmtEur = (v) => `€${Math.round(v).toLocaleString("en-GB")} / yr`;
const fmtDate = (v) => (v == null ? "—" : v.toLocaleDateString("en-GB", {year: "numeric", month: "short", day: "2-digit"}));
const fmtPct = (num, den) => (den > 0 ? `${Math.round((num / den) * 100)}%` : "—");
```

<div class="grid grid-cols-4">
  ${kpiCard("Postings with salary", overall.n.toLocaleString(), `${fmtPct(salaried.length, total)} of ${total.toLocaleString()} in filter have one`)}
  ${kpiCard("Median salary", fmtK(overall.med), "annual €, midpoint of range")}
  ${kpiCard("Middle 50%", overall.n ? `${fmtK(overall.q1)} – ${fmtK(overall.q3)}` : "—", "25th to 75th percentile")}
  ${kpiCard("Estimated by Adzuna", fmtPct(nImputed, overall.n), `${nImputed.toLocaleString()} dots — ad stated no salary`)}
</div>

```js
function chart(width) {
  return distributionChart(rows, summary, {
    width,
    domain,
    xLabel: "Annual salary (€)",
    format: fmtK,
    colorDomain: KINDS,
    colorLabel: "Salary is",
    channels: {
      // Not named `title`: that channel name would replace the whole tip.
      posting: {value: "title", label: "Title"},
      company: {value: "company", label: "Company"},
      salary: {value: "value", label: "Salary"},
      country: {value: "country", label: "Country"},
      arrangement: {value: (d) => d.work_arrangement ?? "unknown", label: "Arrangement"},
      posted: {value: "posted_at", label: "Posted"}
    },
    tipFormat: {posting: true, company: true, salary: fmtEur, fill: true, country: true, arrangement: true, posted: fmtDate}
  });
}
```

<div class="grid grid-cols-1">
  ${summary.length === 0
    ? html`<div class="card"><h2>Salary distribution</h2><div>No postings with a salary in the current selection — loosen the filters.</div></div>`
    : html`<div class="card"><h2>Salary distribution</h2>${resize((width) => chart(width))}</div>`}
</div>

<small>
Box: median and 25th–75th percentile; whiskers reach the furthest posting within 1.5 × that range.
Dot colour separates salaries stated in the ad from Adzuna's estimates.
Dots shrink as the selection grows so every posting stays visible.
${offAxis > 0 ? html`<strong>${offAxis.toLocaleString()}</strong> postings fall outside the 1st–99th percentile axis and are not drawn as dots; the curve, box and figures still include them. ` : ""}
${dropped > 0 ? html`<strong>${dropped}</strong> group${dropped === 1 ? "" : "s"} with fewer than ${MIN_GROUP} salaries ${dropped === 1 ? "is" : "are"} not shown as a row. ` : ""}
</small>

## Postings behind the chart

${dataTable(d3.sort(rows, (d) => -d.value), {
  title: "Postings with salary",
  filename: "jobmarket-salary-distribution.csv",
  subtitle: "Every dot above, highest salary first. Click a title to open the original posting; CSV exports every column.",
  columns: ["title", "company", "country", "value", "kind", "work_arrangement", "posted_at"],
  header: {
    title: "Title",
    company: "Company",
    country: "Country",
    value: "Salary",
    kind: "Salary source",
    work_arrangement: "Arrangement",
    posted_at: "Posted"
  },
  format: {
    value: fmtK,
    posted_at: fmtDate,
    title: (t, i, data) => data[i].url
      ? html`<a href="${data[i].url}" target="_blank" rel="noopener">${t}</a>`
      : t
  },
  width: {title: 320, company: 220, country: 70, value: 80, kind: 110, work_arrangement: 110, posted_at: 100}
})}
