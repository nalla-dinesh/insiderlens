"""Seeded RNG plumbing — the determinism law made code.

One PCG64 generator threads the entire build. `choose()` additionally SORTS its
input so that Python set-iteration order can never leak into the output.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np


def make_rng(seed: int | None) -> np.random.Generator:
    if seed is None:
        raise ValueError("generator requires an explicit seed (determinism law)")
    if not isinstance(seed, int):
        raise TypeError(f"seed must be int, got {type(seed)}")
    return np.random.Generator(np.random.PCG64(seed))


def choose(
    rng: np.random.Generator,
    seq: Iterable[Any] | Sequence[Any],
    size: int | None = None,
    replace: bool = False,
    p: Sequence[float] | None = None,
):
    """Deterministic choice: input is sorted first (sets are made safe).
    size=None -> single scalar; size=n -> ndarray of n."""
    arr = np.asarray(sorted(seq))
    return rng.choice(arr, size=size, replace=replace, p=p)


def lognormal_amounts(
    rng: np.random.Generator, median: float, sigma: float, size: int, lo: float, hi: float
) -> np.ndarray:
    """Clipped, 2-decimal log-normal amounts (rupees)."""
    vals = rng.lognormal(mean=float(np.log(median)), sigma=sigma, size=size)
    return np.round(np.clip(vals, lo, hi), 2)
