# Feature roadmap — BI & AI feature track

Product-feature backlog for the dashboard and the applied-AI layer. Complements
[open-questions.md](open-questions.md) (ops/quality loose ends — that file stays the
work queue for pipeline correctness); this file tracks **new user-facing capability**.
New session? Start at [bootstrap.md](bootstrap.md), then pick the top `planned` item here.

_Last updated: 2026-07-25._

## How to use this file (session bootstrap)

- Statuses: `idea` → `planned` → `in-progress` → `shipped` (or `dropped`, with a one-line why).
- One feature = one PR where feasible; squash-merge to `main`; update status + CHANGELOG in the same PR.
- Before building anything here, re-read the **hard constraints** below — they kill
  otherwise-good designs early.

## Hard constraints (apply to every feature)

1. **No backend.** Static Observable Framework site + DuckDB-WASM. Anything dynamic is
   either (a) computed at weekly build time and shipped as static JSON/parquet, or
   (b) computed client-side, optionally with a **user-supplied** LLM key (BYOK).
2. **Browser parquet is a column subset.** `site/src/data/postings.parquet.js` SELECTs
   a fixed list; `first_seen_at`/`last_seen_at`, `contract_type`, `contract_time`,
   `adzuna_category`, `description`, `location_area` are **not shipped** today. Features
   needing them must extend the loader (and mind asset size / ToS surface).
3. **Adzuna ToS.** Aggregates + attribution OK for personal research; republishing raw
   descriptions is not. No feature may ship raw `description` text to the public site.
4. **Adzuna quota.** 250 calls/day, ~30/wk used. Features must not add per-visitor API calls.
5. **LLM free tiers only.** Build-time: Gemini free tier (e.g. `gemini-2.5-flash-lite`),
   batched, weekly volume only (hundreds of calls max). Client-side: BYOK, feature must
   degrade gracefully to nothing when no key present. Free-tier data may be used for
   provider training — never send user PII by default; warn in UI where user pastes text (F9).
6. **Stock Observable defaults.** No custom CSS / fill overrides; `theme: "dashboard"`.
7. **Every new data page** must be added to `observablehq.config.js` `pages` AND
   `site/scripts/smoke.mjs` `DATA_PAGES` (hardcoded list), and pass
   `npm run build && npm run smoke`.

## Status board

| ID | Feature | Status | Effort | Value | Depends on |
|----|---------|--------|--------|-------|------------|
| F1 | Trends page (weekly time series) | shipped | S | ★★★★★ | — |
| F2 | Market-pulse KPI strip w/ WoW deltas | in-progress | S | ★★★★ | F1 |
| F3 | Posting lifetime (demand-tightness proxy) | planned | S-M | ★★★★★ | loader cols |
| F4 | Skill-salary premium + co-occurrence | planned | M | ★★★★★ | — |
| F5 | LLM ISCO fallback (build-time Gemini) | planned | S-M | ★★★★ | — |
| F6 | Weekly AI market brief (build-time) | planned | S | ★★★★ | F1 |
| F7 | "Ask the data" NL→SQL chat (BYOK) | planned | M | ★★★★★ | — |
| F8 | Employer & contract-mix pages | idea | M | ★★★ | loader cols |
| F9 | CV skill-gap matcher (BYOK) | idea | L | ★★★★ | F4 mature |
| F10 | Eurostat benchmark overlay (revival) | idea | M-L | ★★★ | adapter revival |
| F11 | Title canonicalization via embeddings | idea | M | ★★ | F5 |

## F1 — Trends page `[shipped]`

_Shipped 2026-07-25, PR #37 (`49eb80b`). All acceptance criteria met (page live,
nav + smoke lists, CSV export, build+smoke green)._

**What:** `/trends` — continuous weekly series over the accumulated snapshot: posting
volume by country, median €p50, salary-disclosure rate, arrangement share, top-skill
share. Global filterCard + week/month granularity toggle.
**Why:** Compare page only diffs two periods; this is the actual "state of the market"
view and the substrate for F2/F6.
**Notes:** `date_trunc('week', posted_at::TIMESTAMP)` (tz pitfall); share-based series
are the robust signal across the accumulation start (mid-May 2026) — annotate like
compare.md does. Guard weekly medians with `HAVING COUNT(salary) >= 3`.
**Done when:** page live, in nav + smoke list, CSV export of the weekly aggregate table,
build+smoke green.

## F2 — Market-pulse KPI strip `[in-progress]`

_Branch `feat/market-pulse-overview` (started 2026-07-25)._

**What:** 4-5 KPI cards on Overview (or top of /trends): latest complete week vs prior —
volume, median salary, remote share, disclosure rate, (later: median lifetime F3).
WoW delta arrows, reusing the `deltaSub` pattern now duplicated in compare.md and
trends.md — **extract it to `site/src/components/` first**, then consume from all
three pages.
**Why:** one-glance market state; cheap once F1 lands.
**Done when:** KPI strip renders with correct deltas on Overview; `deltaSub` is a
shared component (compare + trends refactored onto it); partial-week guard documented;
build+smoke green.

## F3 — Posting lifetime `[planned]`

**What:** `last_seen_at - first_seen_at` = days a posting stayed live. Distributions +
weekly median by ISCO major × country. Proxy for time-to-fill / demand tightness.
**Why:** unique differentiator — columns already accumulate (ADR-020), nobody publishes
this free.
**Blocked by:** loader must ship both columns (constraint 2). Validate semantics first:
`last_seen_at` only advances while a posting re-appears in the fetch window — confirm
against the accumulation audit item in open-questions.md before charting.
**Done when:** loader ships cols; lifetime section (on /trends or own page) with
right-censoring caveat (postings still live at snapshot date).

## F4 — Skill economics `[planned]`

**What:** on /skills: (a) **skill-salary premium** — median €p50 for postings with skill X
vs ISCO-major baseline, ≥N disclosed guard; (b) **co-occurrence** — top skill pairs
("know X → also asked: Y"), from `unnest(skills)` self-join in DuckDB-WASM.
**Why:** top job-seeker question ("what is Python worth"); pure SQL over shipped data.
**Notes:** premium is confounded (seniority/role mix) — label as descriptive, not causal.
**Done when:** both charts on /skills with disclosure-count guards + caveat copy.

## F5 — LLM ISCO fallback `[planned]`

**What:** weekly pipeline step: postings with `isco_match_method='none'` → Gemini
free-tier classification into ISCO-08 4-digit; write `isco_match_method='llm'` +
`isco_match_score`. Schema slot already exists (`schemas.py` isin includes `"llm"`).
**Why:** GB fuzzy match ~53%; every dashboard page improves. ADR-013 descoped it;
open-questions "ISCO match-rate watch" names it load-bearing if rate stays low.
**Notes:** cheaper first lever per ADR-021 = extend label snapshot with missing titles —
do that first, measure, then LLM the residual. Volume: low hundreds/wk — fits free tier.
Prompt gets title (+truncated description); cache by normalized title to cut calls.
Add `llm` share to Quality page match-method chart. Failure mode: Gemini outage →
rows stay `none` (never block the cron); pin response schema (JSON mode).
**Done when:** opt-in pipeline step + tests (fixture pattern), quality page shows `llm`
slice, ADR recorded.

## F6 — Weekly AI market brief `[planned]`

**What:** build-time: feed the week's **aggregates only** (KPI deltas, top movers — the
same numbers compare.md computes) to Gemini → 3-paragraph narrative → `brief.json`
shipped with the site; rendered on Overview with "AI-generated" label + date.
**Why:** high perceived value, zero client cost, hallucination-bounded (input = our own
computed numbers; instruct: no numbers not present in input).
**Notes:** aggregates only → no ToS/description issue. Site build must succeed with
`brief.json` missing/stale (cron resilience).
**Done when:** generator in refresh workflow, Overview renders it, graceful absence.

## F7 — "Ask the data" NL→SQL chat `[planned]`

**What:** page/panel: user question → Gemini (BYOK, key in localStorage, never sent to
us) generates DuckDB SQL against the `postings` schema (embedded in prompt) → executes
in the already-loaded DuckDB-WASM → table + auto chart. Show the SQL; read-only.
**Why:** flagship applied-AI BI feature; perfect no-backend fit — the query engine
already runs in the visitor's browser.
**Notes:** guard: single SELECT statement only (reject DDL/DML by parse), LIMIT cap,
error → show SQL + DuckDB error for manual fix. Degrade: without key, panel shows
"bring your own free AI Studio key" instructions + canned example queries that run
locally. Model: `gemini-2.5-flash` BYOK.
**Done when:** page live; works with key; useful without key; smoke covers no-key path.

## F8 — Employer & contract-mix pages `[idea]`

**What:** top hirers, repeat-poster vs new-entrant ratio, per-ISCO hiring concentration
(HHI), salary-transparency rate by company; contract_type/time share + trend.
**Notes:** `company` ships already; `contract_*` need loader cols (constraint 2).
Company names are raw Adzuna strings — expect dupes ("Google"/"Google LLC") until F11.

## F9 — CV skill-gap matcher `[idea]`

**What:** paste CV → Gemini (BYOK) extracts ESCO-style skills client-side → join against
demand + F4 premium data → coverage %, missing top skills, salary upside.
**Notes:** privacy: CV goes only to the user's own key — but free tier may train on it;
explicit UI warning required (constraint 5). Ship after F4 so output has salary teeth.

## F10 — Eurostat benchmark overlay `[idea]`

**What:** revive `benchmarks/eurostat.py` (+ existing `BenchmarkSchema`) for GB/ES
official medians per ISCO; overlay posted-salary vs official-median premium.
**Notes:** shelved by ADR-017 pivot, not deleted; OECD stays dead (Cloudflare-gated),
CSO stays dead (coarse). Check Eurostat ISCO granularity (often 1-digit for earnings
datasets — may cap the overlay at major-group level; UK post-Brexit coverage may be
absent → GB fallback source needed or ES-only).

## F11 — Title canonicalization `[idea]`

**What:** build-time Gemini embeddings on distinct titles → cluster → canonical role
labels; cleaner top-titles chart, role-level drill-down below ISCO granularity, input
to F8 company dedupe.
**Notes:** cache embeddings by title hash; weekly delta is small. Lowest value-per-effort
right now — last.

## Dropped

_(none yet — record ID, date, one-line why when it happens)_
