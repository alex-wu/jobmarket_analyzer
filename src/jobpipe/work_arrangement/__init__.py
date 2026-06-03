"""Work-arrangement inference: remote / hybrid / onsite / NULL.

Populates the `work_arrangement` column on a PostingSchema-shaped DataFrame
by scanning posting text (title + description) for multilingual keywords.

Two flavours of input:

- **Lookup dict** (`posting_id -> full_description`) — produced by
  `jobpipe.work_arrangement.fetcher` after a per-posting Adzuna
  `/v1/api/jobs/{country}/details/{id}` fetch. The full body has higher
  hit-rate than the 500-char `/search` truncation.
- **No lookup** — the tagger falls back to the truncated `description`
  column already present on the frame. Lower coverage but no quota cost.

Tiebreak rule: hybrid > remote > onsite. A `hybrid` mention beats a
`remote` mention since hybrid postings often advertise "remote flexibility"
that would otherwise classify them as full-remote.
"""

from __future__ import annotations
