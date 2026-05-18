"""Catches drift between PostingSchema and the accumulation projection.

`duckdb_io.export_accumulated` SELECTs an explicit column list from
`_ACCUMULATE_ANY_VALUE_COLS`. Any new PostingSchema column missing from that
tuple is silently dropped on the next accumulation rollup — and never appears
in `latest-{preset_id}.parquet`. This guard fails the build instead.
"""

from __future__ import annotations

from jobpipe.duckdb_io import _ACCUMULATE_ANY_VALUE_COLS
from jobpipe.schemas import PostingSchema

_EXCLUDED = frozenset(
    {
        "posting_id",
        "first_seen_at",
        "last_seen_at",
        "ingested_at",
    }
)


def test_accumulate_cols_cover_schema() -> None:
    schema_cols = set(PostingSchema.to_schema().columns)
    accumulate_cols = set(_ACCUMULATE_ANY_VALUE_COLS)
    missing = (schema_cols - _EXCLUDED) - accumulate_cols
    assert not missing, (
        f"new PostingSchema columns missing from _ACCUMULATE_ANY_VALUE_COLS: "
        f"{sorted(missing)}. Add them or extend _EXCLUDED if intentional."
    )
