# Portfolio audit — what makes this a standout piece

Ranked backlog of features and improvements scored on **portfolio value per hour**, not engineering interest. Complements [feature-roadmap.md](feature-roadmap.md) (F-numbered capability track) and [open-questions.md](open-questions.md) (ops/quality queue): this file says *which order* and *why it matters to a reviewer*. Item numbers here (#1–#18) are referenced from [bootstrap.md](bootstrap.md).

_Audited 2026-09-13 against `main @ b2799e8`, the 2026-09-07 production manifest, and a green local gate (ruff + format + mypy strict + 374 pytest)._

---

## Verdict

The plumbing is senior-grade. The story is not yet told. A reviewer who opens the repo sees badges and a wall of text, no picture, and a dashboard that says "use Firefox." The dashboard has eight pages of charts and zero written findings. Fixing the first impression and adding one page of actual insight does more than any new feature.

The engineering already exceeds most analytics portfolios: unattended weekly pipeline live for 17 weeks, immutable dated archive with pure-function recompute, pandera contracts, mypy strict, CodeQL, OpenSSF Scorecard, 26-ADR trail. That is the moat. The work now is making it legible in under two minutes, then adding analytical depth on top of the data that only this pipeline produces.

## Where it stands (2026-09-13)

| Signal | Value | Note |
|---|---|---|
| Accumulated corpus | 5,527 postings | 180-day window; ~980 fresh/week. Thin for cross-country claims. |
| Country coverage | 2 of 7 | GB + ES active. Other five are a one-line YAML edit. |
| ISCO match rate | 55% fuzzy | 45% of rows untagged → "Unclassified" on every page. |
| Idle time | 7 weeks | No commits 2026-07-25 → 2026-09-13. F2 shipped 2026-09-14 on the branch; PR pending. |
| Repo signals | 0 stars, 2 topics | No screenshot. Description still promises benchmark overlays shelved by ADR-017. |
| Dashboard | 8 pages | Charts, filters, CSV, choropleth. No narrative findings page. |

### Already standout

- **Live, unattended, weekly.** Real production loop with failure alerting (red run files an issue). Not a notebook.
- **Accumulation architecture.** Immutable dated releases + recomputed `latest`. Yields first/last-seen per posting — a metric nobody publishes free.
- **Taxonomy grounding.** ESCO/ISCO-08 occupations + Pillar B skills via Aho-Corasick. Domain literacy, not keyword counting.
- **Decision trail.** 26 ADRs incl. superseded ones; honest known-limitations doc; Quality page.
- **Security + CI hygiene.** Credential scrubbing, CodeQL, Scorecard, Dependabot auto-merge, strict typing gate before tests.
- **No-backend BI.** DuckDB-WASM in browser, URL-persisted filters, stock Framework idiom. Free to host, fast to fork.

### Holding it back

- **No visual first impression.** README opens with badges + paragraph. No hero screenshot/GIF, no inline diagram.
- **Charts without conclusions.** Analytics portfolios are judged on insight communication. Nothing states what the data says.
- **Thin data.** Two countries, three keywords. Geography and country comparisons can't carry weight yet.
- **"Use Firefox" banner.** Most reviewers open Chrome. A visible browser caveat reads as broken, whatever the upstream cause (duckdb-wasm #1658).
- **Pluggability unproven.** Preset system is the core claim; one preset exists and the loader hardcodes it.
- **Applied-AI layer is all roadmap.** `llm.py` is a stub. F5/F6/F7 are where the "AI" would come from.
- **Stale surface.** Repo description, `pipeline_version 0.0.1`, no tagged release, open WIP branch.

---

## Ranked backlog

Effort: **S** < 4h · **M** 4–12h · **L** > 12h (for someone who knows the codebase). Value = what a hiring reviewer notices (★1–5).

### Tier 1 — do before anything else

| # | Item | Value | Effort | Complexity | Why it ranks here |
|---|---|---|---|---|---|
| 1 | **README hero + repo metadata** — screenshot/GIF, 3-line pitch, live link above fold, inline architecture diagram, fix GitHub description + topics | ★★★★★ | S · 2h | Low | Decides whether anyone reads further. Description still advertises shelved benchmark overlays. Surface the rigor ("17 weeks unattended, 374 tests, mypy strict, 26 ADRs") on the first screen. |
| 2 | **Widen to 7 countries** — `gb de fr nl es it pl` in preset YAML; recalibrate `gate.min_total_rows` | ★★★★★ | S · 1h + 1 cron | Low | Triples corpus growth; makes choropleth + every cross-country chart real. Quota safe (~105 calls/wk vs 250/day). Watch cross-language tagger noise on DE/FR/IT/PL. |
| 3 | **Findings page** — "What the data says": 5–7 written findings, each with chart + caveat, dated | ★★★★★ | M · 6h | Low | Biggest gap. Turns a dashboard into an analysis. Candidates: ES vs GB disclosure gap; remote share by ISCO; SQL/Python co-demand; salary spread by country; posting churn. |
| 4 | ~~**Finish F2 KPI strip**~~ — shipped 2026-09-14, see below; PR + merge pending | ★★★ | S · 3h | Low | Open WIP branch for 7 weeks looks abandoned. Overview needs a one-glance summary anyway. |

### Tier 2 — differentiators

| # | Item | Value | Effort | Complexity | Why |
|---|---|---|---|---|---|
| 5 | **F3 Posting lifetime** — `last_seen − first_seen`; distribution + weekly median by ISCO × country; right-censoring caveat | ★★★★★ | M · 6h | Medium | Unique metric only the accumulation architecture produces. 17 weeks of archive now exist to validate semantics. Ship loader cols first. The "why did you build it that way" talking point. |
| 6 | **F6 Weekly AI market brief** — build-time Gemini over aggregates only → `brief.json`; graceful absence | ★★★★ | M · 5h | Medium | Cheapest credible applied-AI feature. Hallucination-bounded by construction (input = own numbers). Good guardrails story. |
| 7 | **F7 Ask-the-data NL→SQL** — BYOK Gemini → DuckDB SQL → runs in browser; single-SELECT guard; canned queries without key | ★★★★★ | M · 10h | High | Flagship. No-backend fit is elegant: query engine already in visitor's browser. Needs SQL parse guard, LIMIT cap, no-key path in smoke. |
| 8 | **F5 ISCO match uplift** — step 1: extend label snapshot with missing titles (ADR-021); step 2: Gemini fallback on residual | ★★★★ | M · 6h | Medium | 45% untagged is the most visible data-quality weakness. Cheap lever first, measure, then LLM. Add `llm` slice to Quality page. |
| 9 | **Chrome reliability** — bump duckdb-wasm, auto-retry on `TProtocolException`, drop banner if fixed | ★★★★ | S–M · 3h | Unknown | Upstream bug #1658, but the banner is ours. Check newer duckdb-wasm; else silent retry-once-then-reload beats telling reviewers to switch browsers. Not an architectural pivot. |
| 10 | **F4 Skill economics** — skill-salary premium vs ISCO baseline; co-occurrence pairs | ★★★★ | M · 6h | Medium | Answers the job-seeker question directly. Pure SQL over shipped data. Label descriptive, not causal. |

### Tier 3 — proof and reach

| # | Item | Value | Effort | Complexity | Why |
|---|---|---|---|---|---|
| 11 | **Second preset + switcher** — e.g. `software_developer_eu`; `presets.json` from `config/runs`; un-hardcode loader + `pages.yml`; UI switcher (ADR-019) | ★★★★ | L · 12h | Medium | Proves the fork-friendly claim. Until then "pluggable presets" is an assertion. Doubles corpus; enables cross-role comparison. |
| 12 | **v1.0.0 release + case study** — tag, release notes, `pipeline_version` bump, 90-sec demo video, ~1500-word write-up | ★★★★ | M · 6h | Low | Distribution. Structure: problem → constraints (free tier, no backend, ToS) → architecture → three findings → what broke. |
| 13 | **Statistical rigor pass** — IQR bands on medians, bootstrap CI or n-guard labels, small-n suppression stated once as policy | ★★★ | M · 4h | Medium | Separates analyst from chart-maker. Guards exist (≥3 disclosed) but aren't visible as policy. |
| 14 | **Ops hygiene bundle** — Adzuna attribution footer · gate calibration on 17 manifests · artifact correctness gate · PR-gate smoke for `site/**` · `raw_payload` drop | ★★★ | S each | Low | Attribution is 15 min and a ToS risk. `raw_payload` drop shrinks public asset + ToS surface. Gate calibration finally data-grounded. |
| 15 | **F10 Eurostat benchmark overlay** — revive adapter; posted vs official median premium | ★★★ | M–L · 10h | High | Strong if it works; earnings datasets often 1-digit ISCO, GB coverage post-Brexit uncertain. Validate data exists before coding — or drop and fix repo description. |
| 16 | **F8 Employer & contract mix** — top hirers, HHI concentration, transparency by company | ★★★ | M · 6h | Medium | Company strings dirty until canonicalization. Needs loader cols. |
| 17 | **F9 CV skill-gap matcher** — BYOK; ESCO skill extraction; join vs demand + premium | ★★★★ | L · 15h | High | Highest wow of the AI items but depends on F4 and carries privacy UI burden. Later. |
| 18 | **F11 Title canonicalization** — embeddings → clusters → canonical roles | ★★ | M · 8h | Medium | Lowest value per effort. Only as enabler for F8. |

---

## Standout checklist

✓ have · ~ partial · ✗ missing

**First two minutes**
- ✗ Hero image or GIF of the dashboard in README
- ✗ Three-line pitch: what, for whom, what's unusual
- ~ Live link above the fold (present, buried in prose)
- ✗ Architecture diagram inline in README (exists in docs/architecture.md)
- ✗ Rigor stats up front: uptime, tests, typing, ADR count
- ✗ Accurate GitHub description + topics

**Insight, not plumbing**
- ✗ Written findings with charts and caveats
- ✗ One unique metric nobody else publishes (posting lifetime)
- ~ Small-n discipline visible as policy, not just code
- ✓ Honest limitations (Quality page, Methodology, open-questions)
- ✗ Cross-country comparison with enough data to mean something

**Engineering credibility**
- ✓ Unattended production loop with alerting
- ✓ Schema contracts (pandera) + drift-guard test
- ✓ Typed, linted, tested in CI before merge
- ✓ Security posture: CodeQL, Scorecard, credential scrubbing
- ✓ ADR trail including reversals
- ✗ Tagged release (still 0.0.1)

**Applied AI with guardrails**
- ✗ LLM used where it beats heuristics (ISCO residual)
- ✗ Hallucination-bounded narrative (aggregates-only brief)
- ✗ NL→SQL with parse guard, BYOK, degrade to canned
- ✓ Deterministic fallback everywhere (ADR-007 contract)

**Reproducibility**
- ✓ Fork + run runbook (operations.md, github-setup.md)
- ✗ Second preset live proving pluggability
- ✗ Preset switcher in UI
- ✓ Data as open artifact (Parquet releases, manifest)

**Reliability and reach**
- ✗ Works in Chrome without a caveat banner
- ✗ Case study write-up (blog / LinkedIn)
- ✗ Short demo video
- ~ ToS attribution exactly as Adzuna requires

---

## Suggested sequence

**Sprint A — legibility (~1 day):** #1 README hero → #2 widen countries, let Monday cron run → #4 finish F2, close branch → #14 attribution footer.

**Sprint B — insight (~2 days, after one wider cron):** #3 findings page on the wider corpus → #5 posting lifetime → #6 AI brief → #9 Chrome retry check.

**Sprint C — flagship + proof (~3 days):** #7 NL→SQL → #8 ISCO uplift → #10 skill economics → #12 v1.0.0 tag + case study + video.

#11 second preset + switcher slots in whenever a second role is worth tracking. Everything below #12 is optional polish for this project's purpose.

---

## Keeping this file useful

Re-score when an item ships (move it to a "Shipped" list at the bottom with date + PR) or when the state table drifts. Feature acceptance criteria stay in feature-roadmap.md; ops detail stays in open-questions.md — link, don't duplicate.

## Shipped from this list

- **#4 F2 KPI strip** — 2026-09-14, `c485893` + `52b5165` on `feat/market-pulse-overview` (PR pending). Shared `deltaSub`, Overview Market pulse strip, snapshot-count fix.
