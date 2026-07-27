"""Pure-stdlib statistics.

Adapted from codecaliper ``validation/bw_faithfulness/stats.py``, which in turn was ported
from Spaghetti Architect ``bench/grade.py`` (MIT, same author; see NOTICE). Same
definitions; the bodies are re-typed so ``mypy --strict`` passes without ignore comments.
Kept as a copy rather than a dependency for the same reason it was copied the first time:
these five functions are the only statistics the instrument needs, and adding a numeric
stack to get them would put a floating-point implementation detail between the archive
and a published number.

Deterministic: the bootstrap is seeded, and every caller passes the seed explicitly.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence


def mean(xs: Sequence[float]) -> float:
    if not xs:
        return 0.0
    total = 0.0
    for x in xs:
        total += x
    return total / len(xs)


def stdev(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    ss = 0.0
    for x in xs:
        ss += (x - m) ** 2
    return math.sqrt(ss / (len(xs) - 1))


def ci95_bootstrap(xs: Sequence[float], iters: int = 2000, seed: int = 0) -> tuple[float, float]:
    """Deterministic percentile bootstrap 95% CI of the mean."""
    if len(xs) < 2 or stdev(xs) == 0.0:
        return (mean(xs), mean(xs))
    rng = random.Random(seed)
    n = len(xs)
    means = sorted(mean([xs[rng.randrange(n)] for _ in range(n)]) for _ in range(iters))
    return (means[int(0.025 * iters)], means[int(0.975 * iters)])


def _ranks(xs: Sequence[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = r
        i = j + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    """Spearman rank correlation (ties share mean rank); 0.0 on degenerate input."""
    if len(x) != len(y) or len(x) < 2:
        return 0.0
    rx, ry = _ranks(x), _ranks(y)
    mx, my = mean(rx), mean(ry)
    sx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    sy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if sx == 0 or sy == 0:
        return 0.0
    return float(sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True)) / (sx * sy))
