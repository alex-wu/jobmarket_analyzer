"""Benchmark adapter registry.

Mirror of :mod:`jobpipe.sources` for official wage / earnings statistics. Each
adapter subclasses :class:`BenchmarkConfig` and emits a DataFrame conforming to
:class:`jobpipe.schemas.BenchmarkSchema`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

import pandas as pd
from pydantic import BaseModel


class BenchmarkConfig(BaseModel):
    enabled: bool = True
    countries: list[str] = []
    isco_codes: list[str] = []


@runtime_checkable
class BenchmarkAdapter(Protocol):
    name: str
    config_model: type[BenchmarkConfig]

    def fetch(
        self,
        config: BenchmarkConfig,
        *,
        rates: dict[str, float] | None = None,
    ) -> pd.DataFrame: ...


_REGISTRY: dict[str, BenchmarkAdapter] = {}


def register(name: str) -> Callable[[type[BenchmarkAdapter]], type[BenchmarkAdapter]]:
    def deco(cls: type[BenchmarkAdapter]) -> type[BenchmarkAdapter]:
        instance = cls()
        if not isinstance(instance, BenchmarkAdapter):
            raise TypeError(f"{cls.__name__} does not implement BenchmarkAdapter")
        _REGISTRY[name] = instance
        return cls

    return deco


def get(name: str) -> BenchmarkAdapter:
    if name not in _REGISTRY:
        raise KeyError(f"no benchmark adapter registered for {name!r}")
    return _REGISTRY[name]


def names() -> list[str]:
    return sorted(_REGISTRY)


class BenchmarkFetchError(Exception):
    """Raised when a benchmark adapter cannot fetch its series."""
