# Dashboard data-gaps roadmap

> Companion to [`docs/dashboard_strategy.md`](dashboard_strategy.md). That doc specifies *how* the dashboard renders against today's schema; this one specifies *what* upstream extraction work would expand it.

P6 ships the Observable Framework dashboard against `PostingSchema` as-is. The original visualisation brief called for `experience_level`, `work_arrangement`, and `skills` facets — none of those live in the schema today, and the `remote` boolean is too sparsely populated (1% non-null) to anchor a chart. Rather than fabricate them with thin heuristics, the dashboard documents the gap and surfaces "coverage" annotations on every chart that would otherwise mislead.

This doc is the spec for the upstream pipeline pass that closes those gaps. It assumes the reader has read the rest of [`README.md`](../README.md) + the relevant ADRs in [`DECISIONS.md`](../DECISIONS.md).

## Scope

Three intentionally omitted fields, in order of likely extraction difficulty:

| Field | Effort | Accuracy ceiling | Dependencies |
| --- | --- | --- | --- |
| `experience_level` | low (regex + title heuristic) | ~85% with confusion at the Mid/Senior boundary | none |
| `work_arrangement` | medium (per-source structured fields + regex fallback) | ~90% for sources that expose it; ~70% via regex | per-source adapter passes |
| `skills` (multi-label) | high (ESCO skill-pillar matcher) | precision-bounded; bound by ESCO label quality | existing `scripts/build_esco_snapshot.py`, ADR-013 trigger |

The dashboard will gain (a) two new categorical filters on `salary.md` and `roles.md`, and (b) a "skills hierarchy" treemap or hierarchical bar (Excel → SQL → Python → Snowflake-style complexity gradient) on `roles.md` once any of these lands.

## 1. `experience_level`

Three signals, in priority order:

1. **Title prefix/suffix regex.** Match against `^(Junior|Jr\.?|Senior|Sr\.?|Lead|Principal|Staff|Head of|Director of|Trainee|Graduate|Intern)\b` and `\b(I|II|III|IV)$`. Title-based signal is the single highest-precision source — Adzuna feeds and ATS payloads both put it in the title roughly 60-70% of the time on the data-analyst preset.
2. **Description regex** against `raw_payload` (already stored on every row, 100% non-null). Patterns:
   - Entry / graduate: `\b(graduate scheme|junior|entry[- ]level|0[-+] ?years|new grad|early career|trainee|intern)\b`
   - Mid: `\b(mid[- ]level|2[-+] ?years|3[-+] ?years)\b`
   - Senior: `\b(senior|sr\.?|5[-+] ?years|7[-+] ?years|10[-+] ?years|lead engineer)\b`
   - Lead/Principal: `\b(principal|staff|lead|head of|director of)\b`
3. **LLM zero-shot classifier fallback** (Claude Haiku) for the rows where (1) and (2) yield zero matches. Cost back-of-envelope: ~500 postings/day × ~$0.0002/posting at Haiku 4.5 pricing = ~$0.03/day. That's small but introduces a new ADR-013-style external-dep decision and adds a new failure surface in CI.

**Recommendation:** ship (1) + (2) first; emit `experience_level_method ∈ {"title", "description", "none"}` to mirror `isco_match_method`. Gate (3) behind a new ADR once we have a baseline match rate. Match rates should be reported in the manifest the same way ISCO methods already are (see `manifest.postings.isco_match_method_counts`).

**Output schema additions to `PostingSchema`:**

```python
experience_level: Series[str] = pa.Field(
    nullable=True,
    isin=["entry", "mid", "senior", "lead", "executive"],
)
experience_level_method: Series[str] = pa.Field(
    nullable=True,
    isin=["title", "description", "llm", "none"],
)
experience_level_confidence: Series[float] = pa.Field(nullable=True, ge=0.0, le=1.0)
```

**Where to put the extractor:** new module `src/jobpipe/experience.py`, called from `normalise.run()` after FX + p50 are done. Same shape as `src/jobpipe/isco.py`.

## 2. `work_arrangement`

The `remote` boolean already exists on `PostingSchema` but is only set when an adapter explicitly populated it. Five extraction paths, ranked by accuracy:

| Source / signal | Field | Cardinality | Notes |
| --- | --- | --- | --- |
| Greenhouse | `offices`, `metadata.workplace_type` | varies | `offices[].location.name` includes "Remote" / city names. Inspect `raw_payload` JSON. |
| Lever | `workplaceType` | enum: `"on-site" / "hybrid" / "remote" / "unspecified"` | Cleanest source — direct mapping. |
| Ashby | `workplaceType` | enum: `"OnSite" / "Hybrid" / "Remote"` | Direct mapping. |
| Personio | `office` + `recruitingCategory` | string | Inconsistent; needs heuristic. |
| Adzuna | no native field | — | Falls back to description regex. |
| Description regex | (cross-source fallback) | — | `\b(remote|hybrid|on[- ]?site|in[- ]?office|wfh|work[- ]from[- ]home)\b`; combine with proximity to `location` keywords to disambiguate "remote office in X" from "remote work". |

The most accurate path is **per-source extraction**: each adapter writes a `work_arrangement` field at ingest time from the structured source fields, falling back to description regex for sources that lack one. This avoids the regex's classic false-positive on phrases like *"this is not a remote role"* or *"hybrid cloud experience required"*.

**Output schema additions:**

```python
work_arrangement: Series[str] = pa.Field(
    nullable=True,
    isin=["onsite", "hybrid", "remote"],
)
work_arrangement_method: Series[str] = pa.Field(
    nullable=True,
    isin=["source_field", "description_regex", "none"],
)
```

**Migration note:** the existing `remote: bool` field becomes redundant once `work_arrangement` lands. Keep both for one release (one tag of `v0.x`) so downstream consumers can switch, then drop `remote` in the next major bump with an ADR.

## 3. `skills`

The hardest of the three because:

- Skills are **multi-label** (one posting → 5–20 skills), not single-valued.
- The reference taxonomy (ESCO skill pillar) has ~13k labels — full-text fuzzy matching across them is O(n × m) and slow.
- False positives erode trust faster than missing data: surfacing "Excel" on a posting that says "Excellent communicator" is worse than no skills column.

**Approach:** mirror the existing ISCO tagger pattern from `src/jobpipe/isco.py`:

1. Build an ESCO skill-snapshot via the existing `scripts/build_esco_snapshot.py` runner (already pulls occupations; extend it to pull `Skill` concepts via the same tree-walk per [`pitfall-esco-api`](../memory-style note in `MEMORY.md`)). Emit `data/esco_skills_snapshot.parquet`.
2. **Pre-filter the search space** by the row's `isco_code`: ESCO publishes `skillRelations` between occupations and skills (`essentialSkill`, `optionalSkill`). For a posting tagged ISCO 2511 ("Systems analysts"), restrict the candidate label set to that occupation's ~50–150 related skills + the global core. This collapses 13k labels to ~200 per posting.
3. **Token-level fuzzy match** with rapidfuzz `partial_ratio` against the candidate set, cutoff 88+ (higher than ISCO's 85 because skills shouldn't tolerate even mild fuzziness — "SQL" vs "MySQL" matters).
4. Cap at top-N hits per posting to keep `skills` rendering manageable on the dashboard (suggest 12).

**Output schema additions:**

```python
skills: Series[list[str]] = pa.Field(nullable=True)  # list of ESCO preferredLabels
skills_method: Series[str] = pa.Field(nullable=True, isin=["esco_fuzzy", "llm", "none"])
skills_confidence_min: Series[float] = pa.Field(nullable=True, ge=0.0, le=1.0)
```

**Cost / time:** rapidfuzz over ~200 candidates × ~500 postings/day ≈ 100k comparisons per refresh, runs in <2s on CI. The expensive piece is the one-time ESCO skill snapshot build (a few minutes; cached as a parquet artefact like the occupation snapshot already is).

**Dashboard payoff:** unlocks the "skills hierarchy / complexity premium" view the original brief asked for. Plausible visualisation: a Plot horizontal bar of skill → median salary of postings tagging that skill, sorted descending (Snowflake / dbt / Python at the top, Excel near the bottom — the actual story is data-driven, not asserted).

## 4. Sequencing

Suggested phasing once any of these get prioritised:

1. **`experience_level` first** — lowest effort, immediate dashboard payoff, no new deps.
2. **`work_arrangement` second** — per-source adapter work but no new taxonomies.
3. **`skills` last** — gated behind ESCO skill snapshot + an ADR-013-style decision on whether the LLM fallback ever ships.

None of these block the v0.1.0 tag; they're follow-ups slotted into the next milestone after P7 (Pages deploy + screenshots + second preset).

## 5. Surfacing extraction quality

Whatever lands, the manifest must report match-method counts the same way it does for ISCO today:

```jsonc
"postings": {
  "row_count": 504,
  "experience_level_method_counts": {"title": 180, "description": 120, "none": 204},
  "work_arrangement_method_counts": {"source_field": 5, "description_regex": 0, "none": 499},
  "skills_method_counts":           {"esco_fuzzy": 0, "none": 504}
}
```

The dashboard's `coverageNote.js` already reads `isco_match_method_counts` from the manifest — extend it to also surface the three new counts in the per-page banner so users see *exactly* how much of any new chart's data was inferred vs. measured.
