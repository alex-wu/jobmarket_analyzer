# Open questions

Single source of truth for what the project knows it hasn't solved yet. ADRs in [DECISIONS.md](../DECISIONS.md) document locked decisions; this file tracks the loose ends.

Items move between sections as they're resolved. When an item closes, leave a one-line entry under **Resolved** with the ADR or session-log reference so the audit trail survives.

---

## Resolved

- **Adzuna free tier capacity** — `max_pages=5 × results_per_page=50 = 250` per fetch, with `min_interval_hours=24` as the safety knob. Lived at 499 rows across two keywords in P1's live run without tripping the limit (P1 acceptance).
- **Remotive ToS** — Excluded entirely. ToS §8 prohibits redistribution + commercial database-building; attribution back-links don't override. See [ADR-009](../DECISIONS.md#adr-009--remotive-excluded-from-ingest-sources).
- **ESCO live API pagination** — `/api/search` and `/api/resource/concept?isInScheme=...` both cap at offset=100 as of v1.2.1. Workaround: walk the ISCO concept tree to build a static snapshot. See [ADR-010](../DECISIONS.md#adr-010--esco-label-snapshot-built-by-walking-the-isco-concept-tree).
- **HN Algolia + LLM client** — Descoped from v1. Contract stays as a stub for the post-v1 follow-up. See [ADR-013](../DECISIONS.md#adr-013--hn-algolia--llm-client-descoped-from-v1).
- **Local-only files (`CLAUDE.md`, `.claude/`)** — Untracked + gitignored. See [ADR-014](../DECISIONS.md#adr-014--local-only-files-excluded-from-the-public-repo).
- **`--verbose` httpx credential leak** — Centralised scrub filter on the `httpx`/`httpcore` loggers; tested in `tests/test_log_redaction.py`. See [ADR-015](../DECISIONS.md#adr-015--httpx-credential-redaction-filter-on-the-cli-logger).
- **GitHub Pages deploy strategy** — Monorepo with `site/`, `actions/deploy-pages`, Pages source = "GitHub Actions". See [ADR-016](../DECISIONS.md#adr-016--github-pages-deploy-via-actionsdeploy-pages-from-the-monorepo) and the manual checklist in [`docs/github-setup.md`](github-setup.md).

---

## Still open — owned by a future phase

### OECD SDMX unblock (no current owner)

`sdmx.oecd.org` returns 403 + a Cloudflare "Just a moment..." interstitial to anonymous httpx requests. The adapter ships disabled per [ADR-011](../DECISIONS.md#adr-011--oecd-sdmx-adapter-ships-disabled-cloudflare-bot-protection). Unblock paths in priority order:

1. OECD-issued API key header (registered developer programme — unverified whether the free option bypasses Cloudflare).
2. Switch the adapter to a CSV mirror via `data.oecd.org` / `data-explorer.oecd.org` if one publishes the same wage series.
3. Route through a fixed-egress proxy (Cloudflare Worker etc.). Adds infrastructure cost — would violate the free-tier goal.

Until one of those lands, benchmark coverage is CSO (Ireland) + Eurostat (Eurozone, 4-year-lagged SES).

### P6 dashboard decisions

These all require visual inspection of real data and are deferred until `site/` exists.

- **Adzuna posting recency.** Live P1 returned `posted_at` up to a year old. Decide: filter at ingest, surface an age column on the dashboard, or show a freshness badge per posting.
- **`salary_min_eur == 0` rows.** Adzuna emits a small non-zero count of zero-floored salaries. Decide: surface or hide.
- **CSO 4-digit ISCO coarseness.** [ADR-012](../DECISIONS.md#adr-012--cso-pxstat-4-digit-isco-coarseness) documents that CSO's `EHQ03` cube maps to a 3-bucket umbrella. The dashboard must not present CSO bucket-1 numbers as if they were ISCO-2511-specific. UI decision: label, tooltip, or row-level disclaimer.
- **Cross-source dedupe efficacy on the live mix.** Same job often appears on the company's Greenhouse and on Adzuna. Measure overlap once we have a full daily run.
- **Cross-day delta surfacing.** None of the source upstreams expose an incremental API, so every refresh fetches the full current set (see [`docs/architecture.md`](architecture.md#source-api-delta-semantics) for per-source detail). `posting_id` is stable, so the same posting reappears every day until it's removed upstream; `posted_at` is the upstream-reported create/update timestamp; `ingested_at` advances. P6 decision: present each daily release standalone (simplest, matches the publish model), compute `first_seen_at` by joining historical releases at build time (better UX, more loader logic), or flag "new today" by diffing against the previous `data-YYYY-MM-DD` release (cheaper, only needs the prior day).

### ISCO live-match-rate measurement (post-first-Actions-run)

Need a live `jobpipe normalise` against a full-day's worth of postings (estimated 500–1 500 rows after dedupe) to measure the rapidfuzz match rate at the 88 cutoff. A measured rate below 60% triggers a re-scope discussion on the LLM fallback (which is currently descoped via ADR-013).
