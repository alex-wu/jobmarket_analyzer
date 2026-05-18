"""Build the static ESCO Pillar B (skills/knowledge/transversal) snapshot.

One-shot script. Pulls the ESCO v1.1.1 classification CSV bundle published by
the tabiya-tech open-dataset mirror — the official ESCO download portal is
email-gated and the public REST API caps listing endpoints at offset=100
(memory: pitfall-esco-api), so the GitHub mirror is the only path that lets
this run unattended.

Source: https://github.com/tabiya-tech/tabiya-open-dataset
        (mirror of ESCO v1.1.1 in CSV form, released 2024-01-17)

Output schema (`config/esco/skills_labels.parquet`):
    skill_uri           str         ESCO canonical URI
    preferred_label     str         preferredLabel.en
    alt_labels          list[str]   alternativeLabel.en (may be empty)
    skill_type          str         skill/competence | knowledge | language
    reuse_level         str         transversal | cross-sector | sector-specific | occupation-specific
    related_isco_codes  list[str]   ISCO-08 codes whose occupations link this
                                    skill via essential / optional relation

English labels only for v1 — multilingual is deferred until a non-English
preset lands. Re-run when ESCO publishes a new minor version that the tabiya
mirror picks up.

Usage:
    uv run python scripts/build_esco_skills_snapshot.py
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import httpx
import pandas as pd

logger = logging.getLogger("build_esco_skills_snapshot")

TABIYA_RAW = (
    "https://raw.githubusercontent.com/tabiya-tech/tabiya-open-dataset/"
    "main/tabiya-esco-v1.1.1/csv"
)
SKILLS_CSV = f"{TABIYA_RAW}/skills.csv"
OCCUPATIONS_CSV = f"{TABIYA_RAW}/occupations.csv"
RELATIONS_CSV = f"{TABIYA_RAW}/occupation_skill_relations.csv"

DEFAULT_OUT = Path("config/esco/skills_labels.parquet")


def _download(client: httpx.Client, url: str, into: Path) -> Path:
    if into.exists():
        logger.info("cached %s (%d bytes)", into.name, into.stat().st_size)
        return into
    into.parent.mkdir(parents=True, exist_ok=True)
    logger.info("downloading %s", url)
    r = client.get(url)
    r.raise_for_status()
    into.write_bytes(r.content)
    logger.info("wrote %s (%d bytes)", into, len(r.content))
    return into


def _split_alt_labels(raw: object) -> list[str]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    parts = [s.strip() for s in str(raw).split("\n")]
    return [p for p in parts if p]


def build(out_path: Path, *, cache_dir: Path = Path(".cache/esco")) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        skills_path = _download(client, SKILLS_CSV, cache_dir / "skills.csv")
        occs_path = _download(client, OCCUPATIONS_CSV, cache_dir / "occupations.csv")
        rels_path = _download(client, RELATIONS_CSV, cache_dir / "relations.csv")

    skills = pd.read_csv(skills_path)
    occs = pd.read_csv(occs_path)
    rels = pd.read_csv(rels_path)

    logger.info(
        "loaded skills=%d occupations=%d relations=%d",
        len(skills),
        len(occs),
        len(rels),
    )

    occ_to_isco = (
        occs[["ID", "ISCOGROUPCODE"]]
        .dropna(subset=["ISCOGROUPCODE"])
        .assign(ISCOGROUPCODE=lambda d: d["ISCOGROUPCODE"].astype(str).str.zfill(4))
        .set_index("ID")["ISCOGROUPCODE"]
        .to_dict()
    )

    rels = rels.assign(isco=rels["OCCUPATIONID"].map(occ_to_isco)).dropna(subset=["isco"])
    skill_to_iscos: dict[str, list[str]] = (
        rels.groupby("SKILLID")["isco"].agg(lambda s: sorted(set(s))).to_dict()
    )

    skills = skills.rename(
        columns={
            "ORIGINURI": "skill_uri",
            "PREFERREDLABEL": "preferred_label",
            "SKILLTYPE": "skill_type",
            "REUSELEVEL": "reuse_level",
        }
    )
    skills["alt_labels"] = skills["ALTLABELS"].map(_split_alt_labels)
    skills["related_isco_codes"] = skills["ID"].map(
        lambda k: skill_to_iscos.get(k, [])
    )

    out = skills[
        [
            "skill_uri",
            "preferred_label",
            "alt_labels",
            "skill_type",
            "reuse_level",
            "related_isco_codes",
        ]
    ].copy()

    out = out.dropna(subset=["skill_uri", "preferred_label"]).reset_index(drop=True)
    out["preferred_label"] = out["preferred_label"].astype(str).str.strip()
    out = out[out["preferred_label"].str.len() > 0].reset_index(drop=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)

    logger.info(
        "wrote %d skills to %s (skill_types=%s, with_isco_links=%d)",
        len(out),
        out_path,
        out["skill_type"].value_counts().to_dict(),
        int((out["related_isco_codes"].map(len) > 0).sum()),
    )
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path(".cache/esco"),
        help="Where to cache downloaded CSVs (delete to force re-download).",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")
    try:
        build(args.out, cache_dir=args.cache)
    except httpx.HTTPError as exc:
        logger.error("download failed: %s", exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
