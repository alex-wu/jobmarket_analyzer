# Open questions

What the project knows it hasn't solved yet. ADRs in [DECISIONS.md](../DECISIONS.md) record locked decisions; this file tracks the loose ends. New user-facing features live in [feature-roadmap.md](feature-roadmap.md). When an item closes, it moves to **Resolved** with a pointer to the ADR or changelog entry that closed it. New working session? Start at [bootstrap.md](bootstrap.md).

---

## Active

### Data & upstream

- **Adzuna ToS attribution.** Adzuna's terms restrict organisational republishing of aggregates without written consent; personal research is permitted with attribution ("The Adzuna API" + link). The footer already reads "Data: Adzuna"; action: change the wording to "The Adzuna API" + link; consider requesting written consent given the fork-friendly public posture.
- **`/details/{id}` is undocumented upstream.** The work-arrangement fetcher's endpoint is absent from Adzuna's official OpenAPI spec and could vanish without notice — one more reason it ships opt-in and off (ADR-025).
- **`raw_payload` in the public asset.** The full Adzuna JSON per row ships inside `latest-*.parquet`. It's both size bloat and additional ToS surface. Decide keep/drop.
- **Spanish keyword dictionary is thin.** `work_arrangement` coverage is markedly lower for ES than GB. Cheap win: extend the Spanish keyword table (`100% remoto`, `presencial obligatorio`, …); the test suite already covers the table-driven shape.
- **Cross-language tagger noise.** The tagger combines each country's language with English; English word-boundary matches can fire on incidental English inside non-English postings. Low frequency — audit when adding more countries.

### Pipeline & quality gate

- **Artifact correctness gate.** Post-publish validation of the released parquet + manifest: schema version matches, row count sane vs prior week, schema-validate the published file, coverage rates within expected bands. The manifest's `accumulated_row_count` is the input signal.
- **Gate `min_total_rows` calibration.** The threshold is still a documented guess; ground it against the fresh-delta row counts of the published weekly manifests (18 weekly manifests now exist).
- **Salary quality (surfaced by the Salary Distribution page, 2026-11-15).** The floor (ADR-029) removes day/hour/month rates recorded as annual. Still open:
  - `salary_min_eur == 0`: Adzuna emits a zero minimum on some ranges, so the midpoint is half the maximum (e.g. 0–28,321 → 14,160). Candidate fix in `normalise._recompute_p50`: use the maximum when the minimum is 0.
  - Mislabelled figures above the floor (a monthly salary over €10,000) still pass.
  - One ~€46k bin holds ~330 near-identical *stated* salaries — check for duplicate postings that the URL-hash dedupe misses (same ad re-listed under new ids).
  - The floor value is per preset; re-check 10,000 when the preset widens to more countries.
  - First CI run with the floor has not happened yet (next `refresh.yml`); live data keeps the low values until then.
- **ISCO match-rate watch.** Fuzzy match rate hovers near the ~60% quality bar (cutoff already lowered 88 → 85). If it stays below on future runs, the LLM-fallback path (descoped by ADR-013) becomes load-bearing. The cheaper first lever is extending the ISCO label snapshot with missing English titles ("Analytics Engineer", "BI Developer" — ADR-021).

### Dashboard & CI

- **Preset switcher.** The site data loader pins one preset id; multi-preset enumeration + a UI switcher are queued (ADR-019). Until then, running a different preset means changing `PRESET_ID` in two places: `site/src/data/postings.db.js` and `.github/workflows/pages.yml`.
- **SQLite backend follow-ups (ADR-027).** Merged 2026-11-15 (PR #69); the loader ran on CI's Node 24 and the Pages deploy succeeded. Still open: (a) Safari / WebKit and real Edge are unverified; (b) wire `npm run parity` and a Firefox smoke into `pages.yml`; (c) re-run parity on Dependabot PR #63 (`@duckdb/node-api` 2.x) before merging it, since the loader depends on it; (d) default "Posted to" cuts at midnight of the last day, hiding that day's rows (pre-existing).
- **Chip filter bar rollout (ADR-028).** Chips and the skill filter exist only on Salary Distribution. The other six filtered pages still use the dropdown `filterCard`, ignore the `skill=` URL parameter (they pass it through), and say nothing about it. Rollout plan is in [bootstrap.md](bootstrap.md). `chips.css` must mirror the theme list in `observablehq.config.js`.
- **Skill chips expose tagger noise.** The automatic top-12 list shows false positives ("Source (digital game creation systems)", "logistics", "Microsoft Access"). Options: fix in the tagger, or add a curated `skills_filter` list to the preset YAML (rejected for now in ADR-028 as extra configuration).
- **Default salary-max filter hides the top postings.** The filter's upper bound defaults to 250,000 and `whereClause` applies it even at rest, so ~15 postings above €250k never appear on any page — including the outliers the Salary Distribution page exists to show. Candidate fix: take the bounds from the data, or apply no salary predicate while the inputs sit at their defaults.
- **"Disclosed" wording counts Adzuna estimates.** Overview, Trends and Compare call every non-null salary "disclosed", but ~42% are Adzuna predictions. Salary Distribution and Methodology now say "stated in ad" vs "estimated by Adzuna"; the other pages' KPI labels and notes should follow, and the medians could offer a stated-only variant.
- **Salary Distribution at full volume.** With ~4,400 salaries and no filter the dots are ~1 px radius (they grow as filters narrow; hover picks the nearest dot). Acceptable today; widening to 7 countries will multiply the count — revisit (taller row, or default to the 1st–99th percentile axis) then.
- **PR-gate smoke for `site/**`.** The headless smoke test only runs on push to `main`; a path-filtered PR job would catch dashboard regressions pre-merge at ~2-3 min per PR.
- **Local smoke dev-phase timeout (2026-09-13).** `npm run smoke` passes all 8 dev pages and all 8 dist pages, but the "/ filter interaction" step (second `page.goto` on the dev server with `waitUntil: "networkidle0"`) times out at 30 s — reproduced on an unmodified tree, so it is environmental (dev-server websocket / hot-reload keeps the network busy), not a page regression. CI is unaffected (`pages.yml` runs `SMOKE_PHASE=dist`). Candidate fix: `networkidle2` or a DOM-ready wait for that step. Until then, `SMOKE_PHASE=dist npm run smoke` is the CI-equivalent local gate.
- **`/details/{id}` reactivation criteria.** Re-enable only when the Spanish dictionary expansion plateaus AND coverage demand is demonstrated; keep the per-run call cap set even then so a wave of fresh postings can't exhaust the weekly quota.
- **Dependabot auto-merge scope.** Auto-merge currently blesses any patch/minor bump including `.github/workflows/**`; consider excluding workflow files since those change CI semantics.
- **Transitive npm warnings.** A handful of deprecation warnings chain to Observable Framework's own dependencies — not actionable downstream; Dependabot will surface the fix when upstream repins.

---

## Resolved

- **Low "annual" salaries** (2026-11-15, ADR-029) — were day, hourly and monthly rates that Adzuna reports without a pay period. Salary floor blanks them at normalise and at accumulation; the posting is kept.
- **"Imputed" was unexplained** (2026-11-15) — it is Adzuna's `salary_is_predicted` flag. Dashboard now says "Estimated by Adzuna" vs "Stated in ad"; Methodology has a "How salaries are handled" section.
- **No view of individual postings or outliers** (2026-11-15, ADR-028) — Salary Distribution page.
- **DuckDB-WASM Chromium load failure** (2026-11-15, ADR-027, PR #69) — browser engine replaced by SQLite.
- **Accumulation audit on real data** (2026-09-14) — checked on the 5,847-row `latest-data_analyst_eu` release (18 weekly runs): `posting_id` unique after the union; `first_seen_at`/`last_seen_at` populated on every row; 59% of rows seen in ≥2 runs; lifetime (`last_seen − first_seen`) median 7 d, p90 35 d, max 120 d, quantised to 7-day steps with ±1 d cron jitter; 1,001 rows right-censored (`last_seen` = snapshot date). Semantics hold; they feed F3 in feature-roadmap.md. Residual caveat: a posting dropping out of the fetch window looks identical to the ad closing.
- **Pipeline hardening for unattended runs** (2026-07-21) — credential scrubbing extended to wrapped errors/tracebacks and root handlers; retry restricted to 5xx/429/transport (previously dead code); NaT `posted_at` rows quarantined instead of aborting; truncation warnings; failure now files a GitHub issue; manifest carries `accumulated_row_count`. See CHANGELOG.
- **Schema v3** (2026-05-29, ADR-025) — dropped dead-weight columns, added ternary `work_arrangement`, salary rounding, `/details/` fetcher off by default.
- **Dashboard v2** (2026-07-20, ADR-026) — choropleth geography, arrangement page + global filter, skills surface, CSV export everywhere.
- **Filter persistence** (2026-05-19, ADR-024) — URL search params across all pages, including the future preset param.
- **Scope pivot to Adzuna-only** (2026-05-17, ADR-017..020) — closed the zero-row ATS investigation, OECD unblock, cross-source dedupe, and cold-load questions by descope or design.
- **No keyword translation table** (2026-05-18, ADR-021) — first multi-country run showed ES matching *better* than GB; English keywords serve all current markets.
- **Remotive ToS** — excluded entirely (ADR-009).
- **ESCO API pagination cap** — static snapshot via concept-tree walk (ADR-010).
- **Credential leak via `--verbose`** — central scrub filter (ADR-015).
- **Publish partition shape** — flat single parquet per release; hive partitioning strips partition columns into directory paths, which flat release-asset storage then loses.
