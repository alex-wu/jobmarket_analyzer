# ESCO ISCO-08 label snapshot

Static label corpus used by `src/jobpipe/isco/tagger.py` to fuzzy-match job
titles to ISCO-08 4-digit codes. Built once by `scripts/build_esco_snapshot.py`,
checked into the repo so the pipeline has no runtime dependency on the live
ESCO API (which is flagged "to be replaced" by the EU and whose pagination
caps at offset=100 as of v1.2.1).

## Files

- `isco08_labels.parquet` — 2 137 rows. Columns: `isco_code` (4-digit str),
  `label` (str), `label_kind` (`"preferred" | "alt"`). 436 unique ISCO codes
  (the full ISCO-08 unit-group set), 1 701 ESCO alternative-label entries.

## Provenance

- Source: ESCO v1.2.1 (released 2025-12-10), public REST API at
  `https://ec.europa.eu/esco/api/resource/concept`.
- Retrieval date: 2026-05-14.
- Method: BFS the ISCO concept tree from the 10 major groups (`C0`…`C9`),
  recurse through `narrowerConcept`, capture the preferred label of every
  4-digit leaf and the `title` of every `narrowerOccupation` listed under it.
- Total HTTP calls during build: ~620 (one per ISCO concept).

## Refresh

Re-run when ESCO publishes a new classification version:

```bash
uv run python scripts/build_esco_snapshot.py --pause 0.02
```

Commit the resulting parquet + a one-line update to this README's "Retrieval
date" + provenance version.

## Licence

The ESCO classification is published under the **European Union Public Licence
v1.2 (EUPL-1.2)**. We redistribute only labels + 4-digit code mappings, which
are factual data structures. Attribution is mandatory: see
[`DECISIONS.md` ADR-006](../../DECISIONS.md) and the project's `NOTICE.md`.

Source citation:

> "European Skills, Competences, Qualifications and Occupations (ESCO)
> classification version 1.2.1, © European Union, 2025. Licensed under
> EUPL-1.2."
