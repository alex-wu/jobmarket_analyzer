"""Build the static ESCO occupation -> ISCO-08 label snapshot.

One-shot script. Walks the ESCO ISCO-08 hierarchy via the public REST API
(``/api/resource/concept?uri=http://data.europa.eu/esco/isco/C{N}``), since
ESCO's ``/api/search`` and ``/api/resource/concept?isInScheme=...`` endpoints
both cap at offset=100 (pagination broken as of v1.2.1).

For each 4-digit ISCO leaf group it captures:
  * The ISCO group's own preferred label (e.g. "Systems analysts" -> 2511)
  * All ESCO ``narrowerOccupation.title`` entries (e.g. "ICT business analyst",
    "data analyst" -> 2511)

Output schema:

    isco_code   str   4-digit ISCO-08 (``^\\d{4}$``)
    label       str   non-empty, stripped
    label_kind  str   ``"preferred" | "alt"``

Re-run when ESCO releases a new classification version. Not invoked by the
jobpipe runtime. Provenance + retrieval date go in ``config/esco/README.md``.

Usage:
    uv run python scripts/build_esco_snapshot.py
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

logger = logging.getLogger("build_esco_snapshot")

ESCO_CONCEPT_URL = "https://ec.europa.eu/esco/api/resource/concept"
ISCO_MAJOR_GROUPS = [f"http://data.europa.eu/esco/isco/C{n}" for n in range(0, 10)]
ISCO_4D_RE = re.compile(r"/isco/C(\d{4})$")
DEFAULT_OUT = Path("config/esco/isco08_labels.parquet")


def fetch_concept(client: httpx.Client, uri: str) -> dict[str, Any]:
    r = client.get(
        ESCO_CONCEPT_URL,
        params={"uri": uri, "language": "en"},
        timeout=60.0,
    )
    r.raise_for_status()
    return r.json()


def walk_isco_tree(client: httpx.Client, pause_seconds: float = 0.0) -> list[tuple[str, str, str]]:
    """BFS the ISCO concept tree, collect (isco_code, label, label_kind) rows."""
    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    queue: list[str] = list(ISCO_MAJOR_GROUPS)

    while queue:
        uri = queue.pop(0)
        if uri in seen:
            continue
        seen.add(uri)
        if pause_seconds:
            time.sleep(pause_seconds)
        try:
            data = fetch_concept(client, uri)
        except httpx.HTTPError as exc:
            logger.warning("fetch %s failed: %s", uri, exc)
            continue

        links = data.get("_links", {}) or {}
        narrower_concepts = links.get("narrowerConcept", []) or []
        narrower_occupations = links.get("narrowerOccupation", []) or []

        match = ISCO_4D_RE.search(uri)
        if match:
            isco_code = match.group(1)
            preferred = (data.get("preferredLabel") or {}).get("en") or data.get("title")
            if preferred:
                rows.append((isco_code, str(preferred).strip(), "preferred"))
            for occ in narrower_occupations:
                title = occ.get("title")
                if title and isinstance(title, str):
                    cleaned = title.strip()
                    if cleaned:
                        rows.append((isco_code, cleaned, "alt"))
            logger.debug(
                "ISCO %s: %s + %d occupations",
                isco_code,
                preferred,
                len(narrower_occupations),
            )

        for child in narrower_concepts:
            child_uri = child.get("uri")
            if child_uri and child_uri not in seen:
                queue.append(child_uri)

    return rows


def build(out_path: Path, *, pause_seconds: float = 0.0) -> Path:
    headers = {"Accept": "application/json", "User-Agent": "jobpipe-build-esco/0.1"}
    with httpx.Client(headers=headers) as client:
        logger.info("walking ESCO ISCO-08 tree from %d major groups", len(ISCO_MAJOR_GROUPS))
        rows = walk_isco_tree(client, pause_seconds=pause_seconds)

    df = pd.DataFrame(rows, columns=["isco_code", "label", "label_kind"])
    df["label_norm"] = df["label"].str.lower()
    df = df.drop_duplicates(subset=["isco_code", "label_norm"]).drop(columns=["label_norm"])
    df = df.sort_values(["isco_code", "label_kind", "label"]).reset_index(drop=True)

    bad = df.loc[~df["isco_code"].str.match(r"^\d{4}$")]
    if not bad.empty:
        raise RuntimeError(f"non-4-digit ISCO codes leaked: {bad.head()}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    logger.info(
        "wrote %s rows to %s (unique ISCO codes: %d, preferred=%d, alt=%d)",
        len(df),
        out_path,
        df["isco_code"].nunique(),
        (df["label_kind"] == "preferred").sum(),
        (df["label_kind"] == "alt").sum(),
    )
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--pause",
        type=float,
        default=0.05,
        help="Seconds to sleep between concept fetches (default 0.05).",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")
    try:
        build(args.out, pause_seconds=args.pause)
    except httpx.HTTPError as exc:
        logger.error("ESCO API error: %s", exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
