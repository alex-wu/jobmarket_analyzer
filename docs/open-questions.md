# Open questions

What the project knows it hasn't solved yet. ADRs in [DECISIONS.md](../DECISIONS.md) record locked decisions; this file tracks the loose ends. New user-facing features live in [feature-roadmap.md](feature-roadmap.md). When an item closes, it moves to **Resolved** with a pointer to the ADR or changelog entry that closed it. New working session? Start at [bootstrap.md](bootstrap.md).

---

## Active

### Data & upstream

- **Adzuna ToS attribution.** Adzuna's terms restrict organisational republishing of aggregates without written consent; personal research is permitted with attribution ("The Adzuna API" + link). Action: add the attribution line to the dashboard footer; consider requesting written consent given the fork-friendly public posture.
- **`/details/{id}` is undocumented upstream.** The work-arrangement fetcher's endpoint is absent from Adzuna's official OpenAPI spec and could vanish without notice — one more reason it ships opt-in and off (ADR-025).
- **`raw_payload` in the public asset.** The full Adzuna JSON per row ships inside `latest-*.parquet`. It's both size bloat and additional ToS surface. Decide keep/drop.
- **Spanish keyword dictionary is thin.** `work_arrangement` coverage is markedly lower for ES than GB. Cheap win: extend the Spanish keyword table (`100% remoto`, `presencial obligatorio`, …); the test suite already covers the table-driven shape.
- **Cross-language tagger noise.** The tagger combines each country's language with English; English word-boundary matches can fire on incidental English inside non-English postings. Low frequency — audit when adding more countries.

### Pipeline & quality gate

- **Artifact correctness gate.** Post-publish validation of the released parquet + manifest: schema version matches, row count sane vs prior week, schema-validate the published file, coverage rates within expected bands. The manifest's `accumulated_row_count` is the input signal.
- **Gate `min_total_rows` calibration.** The threshold is still a documented guess; ground it against the fresh-delta row counts of the published weekly manifests (7+ weeks of real data now exist).
- **Accumulation audit on real data.** Verify the dated-release union dedupes as intended over multiple weeks (`first_seen_at`/`last_seen_at` drift), now that enough weekly releases exist.
- **`salary_min_eur == 0` rows.** Adzuna emits a small number of zero-floored salaries; decide whether the dashboard surfaces or hides them.
- **ISCO match-rate watch.** Fuzzy match rate hovers near the ~60% quality bar (cutoff already lowered 88 → 85). If it stays below on future runs, the LLM-fallback path (descoped by ADR-013) becomes load-bearing. The cheaper first lever is extending the ISCO label snapshot with missing English titles ("Analytics Engineer", "BI Developer" — ADR-021).

### Dashboard & CI

- **Preset switcher.** The site data loader pins one preset id; multi-preset enumeration + a UI switcher are queued (ADR-019). Until then, running a different preset means changing one constant in `site/src/data/postings.parquet.js`.
- **PR-gate smoke for `site/**`.** The headless smoke test only runs on push to `main`; a path-filtered PR job would catch dashboard regressions pre-merge at ~2-3 min per PR.
- **`/details/{id}` reactivation criteria.** Re-enable only when the Spanish dictionary expansion plateaus AND coverage demand is demonstrated; keep the per-run call cap set even then so a wave of fresh postings can't exhaust the weekly quota.
- **Dependabot auto-merge scope.** Auto-merge currently blesses any patch/minor bump including `.github/workflows/**`; consider excluding workflow files since those change CI semantics.
- **Transitive npm warnings.** A handful of deprecation warnings chain to Observable Framework's own dependencies — not actionable downstream; Dependabot will surface the fix when upstream repins.

---

## Resolved

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
