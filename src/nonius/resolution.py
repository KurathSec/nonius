"""The resolution readout (ARCHITECTURE.md section 9).

What a practitioner actually wants to know: *how much between-system resolution did
composition buy, and at what depth*. Per depth this reports each system's accuracy, the
fraction of composites that are dead (every system perfect) and floored (every system
failing), the fraction that discriminate at all, the gap between the top two systems, and
``m*``, the smallest gap the composed instrument can resolve.

Two sources, never mixed and always labelled:

**A caveat on comparing rows.** ``dead``, ``floored`` and ``discriminating`` are counted by
the same tie test in every row, but they are not the same quantity across rows whose
effective replicate depth differs. A rate estimated from k draws is a coarse grid; two
systems tie more often on a coarse grid than on a fine one, so the discriminating fraction
moves with k as well as with the instrument. The singleton row counts ties among rates
each estimated from k draws; a predicted composite row counts ties among products of those
same rates, and multiplying them spreads the values apart, so the two rows do not tie at the
same rate even before composition does anything. A difference between them is therefore
partly an artifact of how each was computed. Read the between-system gap, which does not
have this problem, alongside them.

``predicted``  computed from the archive's singleton rates under the independence bound.
              Free, and available before anything is emitted or bought. It is a null, not
              a result: it cannot detect a shortcut, because a shortcut is by definition a
              departure from the model it uses.
``measured``   computed from real per-composite verdicts. Only this can answer whether
              composition preserved the construct.

Sampling is over the **constructible** population -- composites the link graph can
actually build (AUDIT-ALL-0002). Sampling components uniformly from the item set describes
a population the composer cannot emit, and on a real corpus the two differ enough to
change which depth looks best.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from nonius.archive import Archive
from nonius.bound import product_prediction
from nonius.model import Chain
from nonius.spec.registry import require
from nonius.stats import ci95_bootstrap, mean

_R_POPULATION = require("AUDIT-ALL-0002")
_R_CAPS = require("AUDIT-ALL-0004")

Source = Literal["predicted", "measured"]


@dataclass(frozen=True, slots=True)
class DepthReadout:
    """One depth's row of the resolution table."""

    depth: int
    n: int
    source: Source
    accuracy: Mapping[str, float]
    dead: float
    floored: float
    discriminating: float
    top_two_gap: float
    #: ``None`` when no system's mean has a non-degenerate bootstrap interval: either fewer
    #: than two composites, or every composite scoring identically for every system. Both
    #: yield a zero-width interval, and printing 0.0000 would claim the instrument resolves
    #: any difference at all -- on a row where it resolved nothing.
    #:
    #: Not comparable across rows. Its scale tracks the magnitude of the accuracies, so it
    #: shrinks as a row floors: reading down the column suggests resolution improving as
    #: the instrument stops discriminating.
    m_star: float | None
    #: Bounds applied while producing this row, reported never hidden (AUDIT-ALL-0004).
    caps: Mapping[str, object] = field(default_factory=dict)

    def leaders(self) -> tuple[str, str] | None:
        if len(self.accuracy) < 2:
            return None
        ranked = sorted(self.accuracy.items(), key=lambda kv: (-kv[1], kv[0]))
        return (ranked[0][0], ranked[1][0])


def ci95_for(values: Sequence[float], *, seed: int = 0) -> float:
    """Width of the seeded 95% bootstrap interval of the mean.

    This is the quantity ``m*`` is a maximum over: a between-system difference narrower
    than it sits inside the instrument's own noise.
    """
    lo, hi = ci95_bootstrap(values, seed=seed)
    return hi - lo


def _row(
    depth: int,
    source: Source,
    per_composite: Sequence[Mapping[str, float]],
    *,
    seed: int,
    caps: Mapping[str, object],
) -> DepthReadout:
    systems = sorted({s for row in per_composite for s in row})
    n = len(per_composite)
    if n == 0 or not systems:
        return DepthReadout(depth, 0, source, {}, 0.0, 0.0, 0.0, 0.0, None, caps)

    accuracy = {s: mean([row.get(s, 0.0) for row in per_composite]) for s in systems}

    dead = sum(1 for row in per_composite if all(row.get(s, 0.0) == 1.0 for s in systems))
    floored = sum(1 for row in per_composite if all(row.get(s, 0.0) == 0.0 for s in systems))
    disc = sum(1 for row in per_composite if len({round(row.get(s, 0.0), 12) for s in systems}) > 1)

    ranked = sorted(accuracy.values(), reverse=True)
    gap = ranked[0] - ranked[1] if len(ranked) > 1 else 0.0

    # m*: the widest 95% bootstrap interval on any system's mean. A gap narrower than that
    # is inside the instrument's own noise and must not be reported as a difference.
    #
    # The bootstrap collapses to a zero-width interval on two different degenerate inputs:
    # fewer than two composites (nothing to resample) and zero sample variance (every
    # composite scoring identically for every system). Both must yield None, because
    # publishing 0.0000 would claim the instrument resolves arbitrarily small differences
    # -- on a row where it resolved nothing at all. The reference asset's depth-8 row is
    # exactly that: four composites, every system at 0.0, discriminating 0.0000.
    #
    # The test is on the MAX, not per system: m* is defined as a max over systems, so one
    # degenerate system is harmless. Nulling per system would wrongly null depths 3 and 5,
    # which each have a system at exactly 0.0 -- including the depth-3 m* the
    # pre-registration pins as its yardstick.
    if n < 2:
        m_star: float | None = None
    else:
        widths = [
            ci95_for([row.get(s, 0.0) for row in per_composite], seed=seed) for s in systems
        ]
        m_star = max(widths) if widths and max(widths) > 0.0 else None

    return DepthReadout(
        depth=depth,
        n=n,
        source=source,
        accuracy=accuracy,
        dead=dead / n,
        floored=floored / n,
        discriminating=disc / n,
        top_two_gap=gap,
        m_star=m_star,
        caps=caps,
    )


def predict(
    chains: Sequence[Chain],
    archive: Archive,
    *,
    depth: int,
    seed: int = 0,
    sample: int | None = None,
) -> DepthReadout:
    """Predicted readout at one depth, under the independence bound (BOUND-ALL-0001).

    ``chains`` must already be the constructible population at this depth
    (AUDIT-ALL-0002). ``sample`` bounds how many are used and is reported.
    """
    pool = list(chains)
    truncated = False
    if sample is not None and len(pool) > sample:
        rng = random.Random(seed)
        pool = rng.sample(pool, sample)
        truncated = True

    rows: list[Mapping[str, float]] = []
    skipped = 0
    for chain in pool:
        row: dict[str, float] = {}
        for system in archive.systems:
            p = product_prediction(archive, system, chain.components)
            if p is None:
                break
            row[system] = p
        if len(row) == len(archive.systems):
            rows.append(row)
        else:
            skipped += 1

    return _row(
        depth,
        "predicted",
        rows,
        seed=seed,
        caps={
            "population": "constructible",
            "chains_available": len(chains),
            "chains_used": len(rows),
            "sampled": truncated,
            "sample_size": sample,
            "skipped_incomplete_archive": skipped,
        },
    )


def measure(
    observed: Mapping[str, Mapping[str, float]],
    *,
    depth: int,
    seed: int = 0,
    quarantined: Sequence[str] = (),
) -> DepthReadout:
    """Measured readout at one depth from real per-composite accuracies.

    ``observed`` is ``{composite_id: {system: accuracy}}``. Quarantined composites are
    excluded, not counted as successes (BOUND-ALL-0003), and the exclusion is reported.

    Every composite must carry a value for every system. A composite a system simply was
    not run on is *not* a composite it failed, and imputing zero would silently report
    an un-run system as the worst one. Ragged input is refused rather than averaged over.
    """
    drop = set(quarantined)
    kept = {cid: row for cid, row in sorted(observed.items()) if cid not in drop}
    systems = sorted({s for row in kept.values() for s in row})
    ragged = sorted(cid for cid, row in kept.items() if sorted(row) != systems)
    if ragged:
        raise ValueError(
            f"measure() got composites missing a system: {ragged[:5]}"
            f"{' ...' if len(ragged) > 5 else ''}. Every scored composite must carry a "
            f"value for all of {systems}; a missing system is not a failed one."
        )
    rows = list(kept.values())
    return _row(
        depth,
        "measured",
        rows,
        seed=seed,
        caps={
            "population": "measured",
            "composites_supplied": len(observed),
            "composites_quarantined": len(drop & set(observed)),
            "composites_scored": len(rows),
        },
    )


def singleton_row(archive: Archive, *, seed: int = 0) -> DepthReadout:
    """The depth-1 row: the source instrument, unchanged.

    This is the baseline every other row is read against, and it is computed from the
    archive alone -- no composition, no assumption, no sampling.
    """
    available = [archive.per_item(item) for item in archive.items]
    rows = [r for r in available if len(r) == len(archive.systems)]
    return _row(
        1,
        "predicted",
        rows,
        seed=seed,
        caps={
            "population": "singleton",
            "items_available": len(available),
            "items_used": len(rows),
            # Items missing for some system are dropped; saying so is the difference
            # between a filtered population and a silently truncated one (AUDIT-ALL-0004).
            "items_skipped_incomplete": len(available) - len(rows),
        },
    )


def table(rows: Sequence[DepthReadout]) -> str:
    """Render the readout as a fixed-width table."""
    systems = sorted({s for r in rows for s in r.accuracy})
    head = (
        f"{'depth':>5} {'n':>7} {'source':<10}"
        + "".join(f"{s[:16]:>17}" for s in systems)
        + f"{'dead':>8}{'floored':>9}{'discrim':>9}{'gap':>8}{'m*':>8}"
    )
    lines = [head, "-" * len(head)]
    for r in sorted(rows, key=lambda x: x.depth):
        lines.append(
            f"{r.depth:>5} {r.n:>7} {r.source:<10}"
            + "".join(f"{r.accuracy.get(s, float('nan')):>17.4f}" for s in systems)
            + f"{r.dead:>8.4f}{r.floored:>9.4f}{r.discriminating:>9.4f}"
            + f"{r.top_two_gap:>8.4f}"
            # m* is None on a degenerate row -- too few composites to resample, or no
            # variance to find. Printing 0.0000 there would read as "resolves any
            # difference", the exact claim the None exists to withhold, so the cell says so.
            + (f"{r.m_star:>8.4f}" if r.m_star is not None else f"{'n/a':>8}")
        )
    return "\n".join(lines)
