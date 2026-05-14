"""ISCO-08 4-digit tagging on posting titles.

Pure data-in / data-out: no HTTP, no FS once the label snapshot is loaded.
The loader is the only FS touchpoint and is cached.

Public entrypoints:

* :func:`load_isco_labels` — read the static ESCO snapshot.
* :func:`tag` — populate ``isco_code`` / ``isco_match_method`` / ``isco_match_score``
  on a postings DataFrame via rapidfuzz token-set matching.
"""

from __future__ import annotations

from jobpipe.isco.loader import load_isco_labels
from jobpipe.isco.tagger import tag

__all__ = ["load_isco_labels", "tag"]
