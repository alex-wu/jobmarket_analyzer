# Dashboard strategy: Observable Framework single-page BI

> Spec for the P6 dashboard rebuild. The implementer in the next session executes against this doc.
> Companion: [`docs/dashboard_data_gaps.md`](dashboard_data_gaps.md) — the upstream-pipeline extraction roadmap.

> **⚠ Principle 8 superseded by P8.** §2 principle 8 (SQL composition centralised in-browser via DuckDB-WASM) is correct at scale ≥ 10 MB parquet but wrong at our scale (23 KB compressed). DuckDB-WASM ships at 7.2 MB compressed (~310× the data) and dominates cold-load time. P8 replaces in-browser SQL with build-time data loaders + client-side `d3.rollup`. ADR-017 will formalise; rewrite of §3.3 + §3.4 pending. Full context: [`docs/sessions/2026-05-15-p7-shipped-handover.md`](sessions/2026-05-15-p7-shipped-handover.md) §3. The rest of this doc (layout, components, filter contract, styling discipline) remains valid.

---

## 1. Why this rebuild

P6 shipped a 4-page Observable Framework dashboard (`/`, `/salary`, `/roles`, `/about`). Real-world feedback after first end-to-end review: several chart cells error at runtime, the visual polish trails Observable's own published examples, and the headline visualisation is a hand-composed raincloud (`density` + `dot(dodgeY)` + `boxX`) where stock Plot marks would do the job with less surface area. The narrative is weak — pages dump charts vertically without a story.

This document codifies a rebuild against three constraints, decided in scoping:

- **Single page, top-to-bottom story.** No multi-route navigation. The dashboard reads like a BI canvas: title → filters → KPIs → salary → roles → cross-cut → cadence → sources.
- **Stock Observable libraries first.** Plot's built-in marks, Framework's `grid` / `card` classes, the theme palette. Custom CSS and bespoke compositions only after the stock primitive has been ruled out.
- **Design against today's schema.** The 19-field `PostingSchema` as-shipped (no `experience_level` / `work_arrangement` / `skills` yet). Those land via the upstream pipeline roadmap in [`docs/dashboard_data_gaps.md`](dashboard_data_gaps.md); the dashboard reserves no layout slots for them.

Audience is tiered into one design: recruiter / portfolio-glance reader, data-curious public, and OSS fork-target developer. The page must telegraph craft within 60 seconds and reward exploration when given longer.

---

## 2. First principles

The rebuild adheres to these eight rules. They are listed in priority order — earlier rules override later ones when they conflict.

1. **Stock Observable Framework + Plot defaults — full stop.** Reach for stock Plot marks (`Plot.barX`, `Plot.rectY` + `Plot.binX`, `Plot.lineY`, `Plot.cell`, `Plot.tip`, `Plot.crosshairX`), Framework layout primitives (`<div class="grid grid-cols-N">`, `<div class="card">`), and shipped themes (`theme: "dashboard"`). **Do NOT override `fill` / `stroke` / `fillOpacity` / `scheme` on marks.** Plot already picks `currentColor` (monochrome) or `observable10` (categorical encoding) — both adapt to whatever theme is active. Hard-coding `var(--theme-foreground-focus)` on every mark was overcorrection; it pinned every chart to the accent colour and made categorical encodings impossible. Lesson confirmed by user mid-session ("removing the styling make it much better now closer to the clean visuals by observable"). Custom CSS / inline `style="..."` attributes / composed marks are LAST RESORT, only after the stock primitive has been ruled out for a specific semantic reason.
2. **Components are pure functions.** A component takes `(rows, options)` and returns a `Plot.plot(...)` object or `HTMLElement`. It does NOT call `display()` internally and does NOT manage state. The caller composes them inside a markdown `js` cell. This matches the `examples/plot/src/components/dailyPlot.js` pattern.
3. **Reactive runtime is the state model.** Use `view(Inputs.x)` to display an input AND bind its value. Re-runs propagate automatically when any cell's dependency changes. No `addEventListener`, no manual subscription wiring.
4. **Responsive by default.** Every chart cell is wrapped in `resize((width) => Plot.plot({width, ...}))`. Fixed-width charts are a bug.
5. **Theme is project-level, not per-mark.** `observablehq.config.js` `theme: "dashboard"` (alias for `[air, near-midnight, alt, wide]`) handles light/dark auto-switching, card elevation, and full-width layout in one config line. Per-page or per-chart overrides exist (frontmatter custom stylesheet, `Plot.plot({style: ...})`) but are reserved for semantic distinctions — a "warning" cell, a brand-coloured headline — not generic accent.
6. **Coverage transparency.** Any chart that filters on a nullable field (ISCO code, salary, posting date) surfaces its denominator. The single global coverage banner does most of this work; individual charts annotate `n=` labels on bars where the count is informative.
7. **FileAttachment paths are static literals.** Framework analyses these at build time. `FileAttachment("data/postings.parquet")` is fine; `FileAttachment(\`data/${name}.parquet\`)` will fail the build. Single source of truth.
8. **SQL composition is centralised.** One `whereClause()` builder consumes all filter inputs and emits one `WHERE ...` string. Every SQL cell reads the same `where` variable. No per-cell filter logic.

---

## 3. Reference patterns

Each pattern below is a verbatim idiom to use during the rebuild. Source: live Observable Framework docs (fetched May 2026), and the `observablehq/framework/examples/plot` reference repo. Memory pitfalls cross-referenced.

### 3.1 KPI row — Framework `grid` + `card`

```html
<div class="grid grid-cols-4">
  <div class="card">
    <h2>Postings</h2>
    <span class="big">${kpi.n.toLocaleString()}</span>
    <small>across ${countryCount} countries</small>
  </div>
  <!-- three more cards -->
</div>
```

Reference: <https://observablehq.com/framework/markdown#grids>. Replaces the current `.kpi-grid` + `.kpi` custom CSS in `site/src/style.css`.

### 3.2 Responsive Plot — `resize((width) => …)`

```js
display(resize((width) => Plot.plot({
  width,
  height: 240,
  x: {label: "Median salary (€)", tickFormat: (v) => `€${(v / 1000).toFixed(0)}k`, grid: true},
  y: {label: null},
  marks: [
    Plot.barX(byCountry, {x: "p50", y: "country", sort: {y: "x", reverse: true}, tip: true}),
    Plot.text(byCountry, {x: "p50", y: "country", text: (d) => `n=${d.n}`, dx: 6, textAnchor: "start"}),
    Plot.ruleX([0])
  ]
})));
```

Reference: <https://observablehq.com/framework/javascript#display>, <https://observablehq.com/plot/features/interactions>. Use `tip: true` as a mark option (simpler than `Plot.tip(...)` + `Plot.pointer(...)`); Plot generates a theme-aware tooltip from the mark's channels automatically. Don't add `fill`/`stroke` — Plot picks `currentColor` which respects the theme.

### 3.3 DuckDB result handling

```js
const db = await DuckDBClient.of({postings: FileAttachment("data/postings.parquet")});

const rows = Array.from(await db.query(`
  SELECT country, quantile_cont(salary_annual_eur_p50, 0.5) AS p50, COUNT(*)::INT AS n
  FROM postings ${where} AND salary_annual_eur_p50 IS NOT NULL
  GROUP BY 1 ORDER BY 2 DESC
`));
```

`db.query()` returns an Arrow Table — wrap with `Array.from()` before passing to Plot. (Memory: `pitfall-duckdb-client-arrow-table`.) For single-row results use `db.queryRow()` directly.

Casts: `date_trunc('week', posted_at::TIMESTAMP)` — the TIMESTAMPTZ overload is missing in DuckDB-WASM. (Memory: `pitfall-duckdb-date-trunc-tz`.)

### 3.4 Filters — `view()` + global `where`

```js
const country = view(countrySelect(countries));
const isco    = view(iscoMajorSelect(iscoPresent));
const salary  = view(salaryRange(0, 250000));
const dates   = view(dateRange([allDates.lo, allDates.hi]));

const where = whereClause({country, isco, salary, dates});  // → "WHERE ..." or ""
```

Each `view()` call both renders the input in the page AND yields a reactive value. Downstream SQL cells reference `where` directly. Reference: <https://observablehq.com/framework/inputs>.

### 3.5 Two-way cell heatmap

```js
display(resize((width) => Plot.plot({
  width,
  marginLeft: 220,
  color: {legend: true, label: "Median salary (€)"},
  marks: [
    Plot.cell(countryByIsco, {x: "country", y: "iscoLabel", fill: "p50", inset: 0.5, tip: true}),
    Plot.text(countryByIsco, {x: "country", y: "iscoLabel", text: (d) => `${Math.round(d.p50/1000)}k`})
  ]
})));
```

Reference: <https://observablehq.com/plot/marks/cell>. Replaces the brittle hard-coded `facetBy: GB && IE` faceting from the previous `/salary` page. Note: `color: {legend: true}` is enough — Plot infers the scale type from the data and picks a default sequential scheme. Specifying `scheme: "blues"` is a per-chart override; only add it if a specific palette is required for accessibility or brand.

### 3.6 Pure-function component

```js
// site/src/components/barChart.js
import * as Plot from "npm:@observablehq/plot";

export function barChart(rows, {x, y, xLabel, width, height, marginLeft = 220, sort = {y: "x", reverse: true}, annotate = (d) => `n=${d.n ?? d[x]}`, fill, xTickFormat} = {}) {
  return Plot.plot({
    ...(width ? {width} : {}),
    ...(height ? {height} : {}),
    marginLeft,
    x: {label: xLabel, grid: true, ...(xTickFormat ? {tickFormat: xTickFormat} : {})},
    y: {label: null},
    marks: [
      Plot.barX(rows, {x, y, ...(fill !== undefined ? {fill} : {}), sort, tip: true}),
      Plot.text(rows, {x, y, text: annotate, dx: 6, textAnchor: "start"}),
      Plot.ruleX([0])
    ]
  });
}
```

Called from the page as `display(resize((width) => barChart(rows, {x: "p50", y: "country", xLabel: "Median salary (€)", width})));`. One function replaces five inline horizontal-bar blocks previously duplicated across `salary.md` and `roles.md`. `fill` is optional and undefined by default — Plot's `currentColor` handles single-series colouring; pass `fill: "channel-name"` (or a function) only when an explicit colour encoding is needed.

---

## 4. Single-page architecture

The rebuilt page is one markdown file (`site/src/index.md`) with the sections below. `observablehq.config.js` drops the `pages` array — single-route site.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Job Market Analyzer · EU data-analyst preset · daily snapshot       │  H1 + subtitle
│  As of 2026-05-15 · 504 postings · 2 countries · pipeline v0.5.0     │  manifest chip
├──────────────────────────────────────────────────────────────────────┤
│  [Country ▾] [ISCO major ▾] [Salary range ─────] [Posted after ─]    │  filter strip
├──────────────────────────────────────────────────────────────────────┤
│  Coverage: N matches your filter · M% ISCO-tagged · S% with salary   │  coverage banner (live)
├──────────────────────────────────────────────────────────────────────┤
│ ┌─KPI──┐ ┌─KPI──┐ ┌─KPI──┐ ┌─KPI──┐                                 │  grid grid-cols-4
│ │ Pst  │ │ Sal% │ │ ISCO%│ │ Span │                                 │  card class
│ └──────┘ └──────┘ └──────┘ └──────┘                                 │
├──────────────────────────────────────────────────────────────────────┤
│ ## Salary distribution                                               │
│ ┌─────── histogram (Plot.rectY + Plot.binX) ────────┐                │  grid grid-cols-2
│ │  Plot.tip on bars · Plot.ruleY([0]) · log toggle? │                │
│ └───────────────────────────────────────────────────┘                │
│ ┌──── median by country (barChart) ─────────────────┐                │
│ │  n=… annotations · sorted desc                    │                │
│ └───────────────────────────────────────────────────┘                │
├──────────────────────────────────────────────────────────────────────┤
│ ## Roles & occupations                                               │
│ ┌──── top-15 titles (barChart) ─────┐ ┌──── ISCO major mix (barChart) ──┐│
│ │  count-based bars                  │ │  Unclassified faded grey        ││
│ └────────────────────────────────────┘ └──────────────────────────────┘│
├──────────────────────────────────────────────────────────────────────┤
│ ## Country × ISCO median salary (Plot.cell heatmap)                  │  full-width
│   sequential blue scale · in-cell €k labels · pointer tip            │
├──────────────────────────────────────────────────────────────────────┤
│ ## Posting cadence                                                   │  full-width
│   areaY + lineY + dot · Plot.crosshair · weekly bucket               │
├──────────────────────────────────────────────────────────────────────┤
│ ## Sources & methodology                                             │  folds About in
│   sources table · manifest chips · gaps roadmap + ADR links          │
└──────────────────────────────────────────────────────────────────────┘
```

Sections in order:

1. **Title + subtitle + manifest chip** — H1 with one-line subtitle; "As of {generated_at} · {row_count} postings · {country_count} countries · pipeline {pipeline_version}" rendered from manifest.
2. **Filter strip** — `<div class="grid grid-cols-4">` of four `view()` inputs.
3. **Coverage banner** — live, reads filtered counts via the same `where` clause.
4. **KPI row** — four `<div class="card">` tiles inside `<div class="grid grid-cols-4">`. Values: total postings, % with salary, % ISCO-tagged, date span.
5. **Salary distribution** — two-up grid: (a) histogram via `Plot.rectY` + `Plot.binX`, (b) median by country via `barChart()`.
6. **Roles & occupations** — two-up grid: (a) top-15 titles via `barChart()`, (b) ISCO major mix via `barChart()` with "Unclassified" faded.
7. **Country × ISCO median salary** — full-width `Plot.cell` heatmap (replaces brittle country faceting).
8. **Posting cadence** — full-width weekly `Plot.areaY` + `Plot.lineY` + `Plot.dot` with `Plot.crosshair` / `Plot.tip`.
9. **Sources & methodology** — closing section: sources `Inputs.table`, manifest chips, link to `dashboard_data_gaps.md` + ADRs.

---

## 5. Component inventory

| File | Status | Signature | Reason |
|---|---|---|---|
| `components/coverageNote.js` | **Keep** | `(manifest, live?) → HTMLElement` | Already coherent; serves the transparency principle. Minor edit: drop the `<a href="./about">` link (no separate route any more); link directly to the same-page `#sources-methodology` anchor and the GitHub gaps doc. |
| `components/isco.js` | **Keep as-is** | `iscoMajorLabel(code) → string` + `ISCO_MAJORS` map | Pure lookup; reused across multiple sections. |
| `components/filters.js` | **Light rewrite** | `countrySelect / iscoMajorSelect / salaryRange / dateRange / whereClause / ALL` | Current implementation is already clean (single-quote escape, ISO timestamp). One change: lay out the filter strip inline via `Inputs.form({...})` so it renders as one row of four inputs, not four separate forms. Verify `whereClause` returns `""` when every input is at its `ALL` / full-range default. |
| `components/raincloud.js` | **Drop** | n/a | Non-standard composition; user explicitly requested removal. The "salary distribution" headline becomes a histogram (`Plot.rectY` + `Plot.binX`) optionally overlaid with `Plot.boxX` if compact enough; called inline from the page — no wrapper component. |
| `components/kpiCard.js` | **New** | `(label, value, sub?) → HTMLElement` | Encapsulates `<div class="card"><h2>${label}</h2><span class="big">${value}</span><small>${sub}</small></div>` so the KPI row is `${kpiCard("Postings", n, `across ${k} countries`)}` × 4 inside `<div class="grid grid-cols-4">`. Lets the page treat each tile as a one-liner. Replaces the custom `.kpi-grid` / `.kpi` CSS block. |
| `components/barChart.js` | **New** | `(rows, {x, y, xLabel, sort?, annotate?}) → Plot` | Five sections currently inline a near-identical horizontal-bar `Plot.plot` (country medians, ISCO medians, top titles, top titles on roles, ISCO mix). One function, called five times. See §3.6 for the canonical signature. |
| `components/heatmap.js` | **New** | `(rows, {x, y, value, label}) → Plot` | Country × ISCO median salary view (§4 section 7). `Plot.cell` + sequential scheme + in-cell text + `Plot.tip`. Pure function, no internal state. |

Existing `style.css` shrinks to one rule: the `.note` callout class. The `.kpi-grid`, `.kpi`, and `.filter-strip` rules go away.

---

## 6. Visual catalog

For each section in §4, the Plot marks, the SQL aggregation, and the interaction.

| § | Section | Marks | SQL grain | Interaction |
|---|---|---|---|---|
| 4 | KPI row | none (HTML cards) | `SELECT COUNT(*), COUNT(salary_…), COUNT(isco_code), MIN/MAX(posted_at)` filtered by `${where}` | none — static text reactive on filter change |
| 5a | Salary distribution | `Plot.rectY` + `Plot.binX({y: "count"}, {x: "salary"})` + `Plot.ruleY([0])` + `Plot.tip` | `SELECT salary_annual_eur_p50 FROM postings ${where} AND salary IS NOT NULL` (raw rows) | hover for bin range + count |
| 5b | Median salary by country | `Plot.barX` (sort desc) + `Plot.text` (n labels) + `Plot.ruleX([0])` + `Plot.tip` | `SELECT country, quantile_cont(p50, 0.5), COUNT(*) GROUP BY 1` | hover for country + €median + n |
| 6a | Top titles by count | `Plot.barX` + `Plot.text` (count labels) | `SELECT title, COUNT(*) GROUP BY 1 ORDER BY 2 DESC LIMIT 15` | hover for title + count |
| 6b | ISCO major distribution | `Plot.barX` (faded "Unclassified") + `Plot.text` | `SELECT COALESCE(isco_major, '∅'), COUNT(*) GROUP BY 1` | hover for label + count |
| 7 | Country × ISCO heatmap | `Plot.cell` (sequential blue) + `Plot.text` (in-cell €k) + `Plot.tip` | `SELECT country, isco_major, quantile_cont(p50, 0.5), COUNT(*) GROUP BY 1,2 HAVING COUNT >= 3` | hover for cell breakdown; legend = colour scale |
| 8 | Posting cadence | `Plot.areaY` + `Plot.lineY` + `Plot.dot` + `Plot.crosshair` + `Plot.tip` | `SELECT date_trunc('week', posted_at::TIMESTAMP)::DATE, COUNT(*) GROUP BY 1` | crosshair + tip on hover |
| 9 | Sources table | `Inputs.table` | `SELECT source, COUNT(*) GROUP BY 1 ORDER BY 2 DESC` | sortable columns |

Filters apply to every cell. The cadence chart (§8) deliberately ignores the date filter on its X axis (it shows the same X span regardless of slider) but applies country / ISCO / salary filters to the count.

---

## 7. Filter contract

A single global filter strip at the top of `index.md`. Backing values:

```js
const country = view(countrySelect(countries));        // string | ALL
const isco    = view(iscoMajorSelect(iscoPresent));    // string | ALL
const salary  = view(salaryRange(0, 250000));          // {lo, hi}
const dates   = view(dateRange([allDates.lo, allDates.hi]));  // {from, to}

const where = whereClause({country, iscoMajor: isco, salary, dates});  // "WHERE …" or ""
```

Then every downstream cell:

```js
const byCountry = Array.from(await db.query(`
  SELECT country, quantile_cont(salary_annual_eur_p50, 0.5) AS p50, COUNT(*)::INT AS n
  FROM postings ${where} ${where ? "AND" : "WHERE"} salary_annual_eur_p50 IS NOT NULL
  GROUP BY 1 ORDER BY 2 DESC
`));
```

The `${where} ${where ? "AND" : "WHERE"}` shim is ugly but explicit; abstracting it further hides which cells filter and which don't. Keep as-is.

`whereClause()` invariant: returns `""` when every input is at its `ALL` / full-range default. Add a unit-style smoke check in the page (assert `where === ""` on first render with no user interaction).

---

## 8. Styling discipline

| Concern | Approach |
|---|---|
| KPI tile background, padding, radius | `<div class="card">` — Framework primitive. |
| KPI row layout | `<div class="grid grid-cols-4">` — Framework primitive. |
| Two-up chart row | `<div class="grid grid-cols-2">` — Framework primitive. |
| Big number, small subtitle inside KPI | `<span class="big">` / `<small>` — Framework primitives (`big` class is theme-managed). |
| Chart primary fill | **Omit `fill`.** Plot picks `currentColor` (monochrome) which reads the theme's `--theme-foreground`. |
| Chart axis grid / text | Plot defaults (theme-aware). |
| Categorical colour | **Omit `fill` channel mapping or just pass the field name.** Plot picks `observable10` automatically. |
| Sequential heatmap color | `Plot.cell(rows, {fill: "value"})` + `color: {legend: true}`. Plot picks a default sequential scheme; only add `scheme:` if specific palette is required. |
| "Faded" / "muted" emphasis | Wrap text in `<small>`. Skip custom CSS rules; the theme handles size + colour. |
| Theme | `theme: "dashboard"` in `observablehq.config.js` — alias for `[air, near-midnight, alt, wide]`. Auto light/dark, lifted cards, full-width layout. |
| Custom `style.css` | **Empty file or absent** unless a specific need surfaces. Run with `style:` config key removed entirely. |
| Mobile breakpoints | `grid grid-cols-N` is already responsive; `resize()` on each chart handles re-flow. No `@media` queries needed. |

After the rebuild, `style.css` does not exist. If a custom rule becomes necessary, justify it: "could Framework / Plot defaults do this?" first.

---

## 9. Implementation phases

Six phases. The implementer session ticks them in order.

1. **P6r.1 — Bug audit & screenshot reel.** Start `npm run dev`, walk the current 4 pages, screenshot every chart that errors or looks visually broken. Save to `docs/sessions/2026-05-15-dashboard-baseline.md` (per session log convention). Output: a regression checklist the rebuild must clear.
2. **P6r.2 — Land this strategy doc.** Commit `docs/dashboard_strategy.md`, README touch-ups, and the gaps-doc cross-link. No code change. Pure docs commit.
3. **P6r.3 — New components.** Add `kpiCard.js` + `barChart.js` (skip `heatmap.js` for now — earn it in P6r.4). Smoke-test by replacing ONE bar chart at a time on the existing `/salary` page; verify it still renders before moving on. This shakes out the component contracts without committing to the single-page layout yet.
4. **P6r.4 — Single-page rewrite.** Rewrite `site/src/index.md` against §4. Drop the `pages` array from `observablehq.config.js`. Wire the global `where` clause through every SQL cell. Add `heatmap.js` for §4-7.
5. **P6r.5 — Cleanup.** Delete `site/src/salary.md`, `site/src/roles.md`, `site/src/about.md`, `site/src/components/raincloud.js`. Strip `site/src/style.css` to the `.note` rule only. Update `site/scripts/smoke.mjs` to assert single-page selectors instead of the four routes.
6. **P6r.6 — Verification.** Run §10 below. Commit. Tag if green.

---

## 10. Verification

For this strategy doc:

- Renders cleanly in GitHub Markdown preview — ASCII wireframe box alignment, table borders, code fences.
- Every code block is copy-paste-runnable (no `<...>` placeholders).
- Component inventory accounts for every existing file under `site/src/components/`.
- File list in §11 matches the file deltas in §9.

For the eventual rebuild (referenced from this doc):

- `cd site && npm run build` exits 0 with no errors logged.
- `node scripts/smoke.mjs` passes (Puppeteer headless walk of `/`).
- Visual width sweep: every chart re-flows at 1440 / 1024 / 768 / 360 px (`resize()` working).
- Filter strip: changing any one of the four inputs updates every chart AND the coverage banner. Toggling everything back to `ALL` / full range restores `where === ""`.
- Theme toggle: switch to dark via the Framework sidebar control; no hard-coded colour bleeds through.
- Sample data path: opens the page with `data/gh_databuild_samples/postings__postings.parquet` and renders all sections without empty / error states.

---

## 11. Critical files

**To create:**

- `docs/dashboard_strategy.md` — this file.
- `site/src/components/kpiCard.js`
- `site/src/components/barChart.js`
- `site/src/components/heatmap.js`

**To modify:**

- `site/src/index.md` — full rewrite against §4.
- `site/observablehq.config.js` — drop `pages` array; keep `title`, `theme`, `base`, `footer`, `style`.
- `site/src/components/filters.js` — inline the four inputs into one form; verify `ALL` defaults yield `where === ""`.
- `site/src/components/coverageNote.js` — drop `./about` link; point to in-page anchor + GitHub gaps doc.
- `site/src/style.css` — strip to `.note` rule only.
- `site/scripts/smoke.mjs` — assert single-page selectors.
- `README.md` — replace P6 description with the single-page model + cross-link this doc.
- `docs/dashboard_data_gaps.md` — one-line header pointer to this doc.

**To delete:**

- `site/src/salary.md`
- `site/src/roles.md`
- `site/src/about.md`
- `site/src/components/raincloud.js`

---

## 12. Open follow-ups

- **Three deferred fields** — `experience_level`, `work_arrangement`, `skills`. Extraction roadmap lives in [`docs/dashboard_data_gaps.md`](dashboard_data_gaps.md). This rebuild reserves no layout slots; when the fields land, a new strategy revision adds the visual sections.
- **LLM ISCO fallback** — descoped from v1 per [ADR-013](../DECISIONS.md). Live match rate at ~56 % (Run 5, n=504); the dashboard surfaces the coverage but does not work around it.
- **Cross-day delta on KPI cards** — would let a tile show "504 (↑12 since yesterday)". Blocked on a history table (`data/postings_history.parquet` partitioned by snapshot date). Out of this rebuild's scope.
- **Second preset** — moved to P11.1. The dashboard already reads whatever the manifest's `preset_id` says, so the only change is the title chip. No layout consequence.
- **Scaffolder warning** — do NOT run `npm create @observablehq` for any new file; the scaffolder is interactive-only and rejects `--yes`. Hand-author every component. (Memory: `pitfall-observable-scaffolder-interactive`.)
