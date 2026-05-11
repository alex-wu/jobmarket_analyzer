"""Source adapter registry.

Every source adapter is a small module under this package that:
1. Subclasses :class:`SourceConfig` for its config knobs (or uses it directly).
2. Implements the :class:`SourceAdapter` Protocol.
3. Registers itself with :func:`register`.
4. Returns a :class:`pandas.DataFrame` conforming to :class:`jobpipe.schemas.PostingSchema`.

See ``docs/adding-a-source.md`` for a walkthrough.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

import pandas as pd
from pydantic import BaseModel


class SourceConfig(BaseModel):
    """Common config shape for source adapters. Subclass for source-specific knobs."""

    enabled: bool = True
    keywords: list[str] = []
    countries: list[str] = []
    max_results: int = 500


@runtime_checkable
class SourceAdapter(Protocol):
    name: str
    config_model: type[SourceConfig]

    def fetch(self, config: SourceConfig) -> pd.DataFrame: ...


_REGISTRY: dict[str, SourceAdapter] = {}


def register(name: str) -> Callable[[type[SourceAdapter]], type[SourceAdapter]]:
    """Class decorator: instantiate and register the adapter under ``name``."""

    def deco(cls: type[SourceAdapter]) -> type[SourceAdapter]:
        instance = cls()
        if not isinstance(instance, SourceAdapter):
            raise TypeError(f"{cls.__name__} does not implement SourceAdapter")
        _REGISTRY[name] = instance
        return cls

    return deco


def get(name: str) -> SourceAdapter:
    if name not in _REGISTRY:
        raise KeyError(f"no source adapter registered for {name!r}")
    return _REGISTRY[name]


def names() -> list[str]:
    return sorted(_REGISTRY)


class SourceFetchError(Exception):
    """Raised by adapters when an HTTP failure must be propagated as a typed error.

    The runner catches this so one source's failure does not abort the whole run.
    """
