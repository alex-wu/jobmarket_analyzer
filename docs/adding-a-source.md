# Adding a new source adapter

A source adapter ingests job postings from one external API and emits a DataFrame conforming to [`PostingSchema`](../src/jobpipe/schemas.py). The rest of the pipeline does not need to change.

## Checklist

1. **Create the adapter module.**
   - Path: `src/jobpipe/sources/<name>.py`.
   - Subclass `SourceConfig` if you need source-specific knobs.
   - Implement `name`, `config_model`, and `fetch(config) -> pd.DataFrame`.
   - Decorate with `@register("<name>")`.

2. **Map raw fields to `PostingSchema`.**
   - `posting_id`: deterministic hash, e.g. `sha1(f"{source}:{external_id}")`.
   - `posting_url`: required — every datapoint must link back.
   - `country`: ISO-3166-1 alpha-2.
   - Leave salary fields `None` if the source doesn't expose them — normalisation handles the gap.

3. **Record an HTTP cassette.**
   - Run the live API once locally: `uv run pytest tests/sources/test_<name>.py --record-mode=new_episodes`.
   - The cassette lands under `tests/cassettes/<name>/`. Verify no secrets in the YAML.

4. **Write the unit test.**
   - Path: `tests/sources/test_<name>.py`.
   - Assertions: (a) returns a DataFrame, (b) passes `PostingSchema.validate(out, lazy=True)`, (c) empty response → empty DataFrame (no exceptions), (d) 5xx → raises `SourceFetchError`.

5. **Wire into a preset.**
   - Set `enabled: true` for your adapter in `config/runs/<preset>.yaml`.
   - Add to the v1 preset only if it materially improves coverage for data-analyst roles in Ireland/Eurozone.

6. **Document.**
   - Append the adapter to the source table in `docs/architecture.md`.
   - Add the attribution to `NOTICE.md` if the source's terms require it.

## Minimal example

```python
# src/jobpipe/sources/my_board.py
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import httpx
import pandas as pd
from pydantic import Field

from jobpipe.schemas import PostingSchema
from jobpipe.sources import SourceConfig, SourceFetchError, register


class MyBoardConfig(SourceConfig):
    base_url: str = Field(default="https://my-board.example/api/v1")


@register("my_board")
class MyBoardAdapter:
    name = "my_board"
    config_model = MyBoardConfig

    def fetch(self, cfg: MyBoardConfig) -> pd.DataFrame:
        try:
            r = httpx.get(f"{cfg.base_url}/jobs", params={"q": cfg.keywords}, timeout=30)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceFetchError(f"my_board: {exc}") from exc

        now = datetime.now(timezone.utc)
        rows = [
            {
                "posting_id": hashlib.sha1(f"my_board:{j['id']}".encode()).hexdigest(),
                "source": "my_board",
                "title": j["title"],
                "company": j.get("company"),
                "location_raw": j.get("location"),
                "country": j["country_code"].upper(),
                "region": None,
                "remote": j.get("remote"),
                "salary_min_eur": None,  # filled by normalise.py
                "salary_max_eur": None,
                "salary_period": None,
                "salary_annual_eur_p50": None,
                "posted_at": j["posted_at"],
                "ingested_at": now,
                "posting_url": j["url"],
                "isco_code": None,
                "isco_match_method": None,
                "isco_match_score": None,
                "raw_payload": str(j),
            }
            for j in r.json().get("results", [])
        ]

        df = pd.DataFrame(rows)
        PostingSchema.validate(df, lazy=True)
        return df
```
