"""The measurement layer, pinned on an archive that can actually discriminate.

Round 8's critic mutation-tested `src/` and found 129 one-character changes that move
library output while pytest, ruff, mypy, and all three mechanical gates stay green -- 31 in
`stats`, 17 in `resolution`, 17 in `bridge`, 8 in `bound`. One of them turns
`ci95_for`'s `hi - lo` into `hi + lo` and rewrites the reference report's headline m* from
0.0511 to 1.6763, a value impossible on an accuracy scale, with nothing objecting.

The root cause was structural. `tests/snapshots/corpus_values.json` pins 169 leaves and
every one is a *composition* decision; archive statistics, readouts, m*, the bridge and the
noise band were pinned by nothing. And the only Archive that reached `predict()` anywhere in
the suite had one system with every verdict correct, so every statistic it produced was
degenerate by construction and arithmetic errors were invisible.

These values are NOT in the composition drift snapshot, deliberately. That gate's rule is
"a changed value needs a spec MAJOR", and a moved m* is not a composition-spec change --
putting it there would make the drift gate say something false about what moved.

The archive below is hand-computed; the arithmetic is in the comments and the assertions are
exact. Only the bootstrap-derived values are pinned as reproducibility rather than as
hand-checked correctness, and they are labelled as such.
"""

from __future__ import annotations

import pytest

from nonius.archive import Archive, Verdict
from nonius.bound import noise_band, unanimous_fraction
from nonius.bridge import build as build_bridge
from nonius.compose import make_chain
from nonius.resolution import ci95_for, predict, singleton_row

#: Two systems, four items, k = 4. Chosen so every stratum is occupied and the two systems
#: rank differently on different items, which is what the degenerate fixture could not do.
#:
#:            i1        i2        i3        i4        mean
#:   A       4/4=1.0   2/4=0.5   0/4=0.0   4/4=1.0   0.625
#:   B       4/4=1.0   4/4=1.0   0/4=0.0   0/4=0.0   0.500
#:   stratum dead      discrim   floored   discrim
CORRECT: dict[tuple[str, str], int] = {
    ("A", "i1"): 4, ("A", "i2"): 2, ("A", "i3"): 0, ("A", "i4"): 4,
    ("B", "i1"): 4, ("B", "i2"): 4, ("B", "i3"): 0, ("B", "i4"): 0,
}


def _archive() -> Archive:
    return Archive(
        tuple(
            Verdict(system, item, draw, 1 if draw < CORRECT[(system, item)] else 0)
            for system in ("A", "B")
            for item in ("i1", "i2", "i3", "i4")
            for draw in range(4)
        )
    )


def test_archive_rates_and_strata_are_exact() -> None:
    arch = _archive()
    assert arch.k() == 4
    assert arch.rate("A", "i2") == 0.5  # 2 of 4
    assert arch.rate("B", "i2") == 1.0
    assert arch.per_item("i4") == {"A": 1.0, "B": 0.0}
    assert arch.stratum("i1") == "dead"
    assert arch.stratum("i2") == "discriminating"
    assert arch.stratum("i3") == "floored"
    assert arch.stratum("i4") == "discriminating"


def test_the_singleton_readout_is_hand_computable() -> None:
    row = singleton_row(_archive(), seed=0)
    assert row.depth == 1
    assert row.n == 4
    # (1.0 + 0.5 + 0.0 + 1.0) / 4 and (1.0 + 1.0 + 0.0 + 0.0) / 4
    assert row.accuracy == {"A": 0.625, "B": 0.5}
    assert row.top_two_gap == 0.125
    assert row.dead == 0.25  # i1
    assert row.floored == 0.25  # i3
    assert row.discriminating == 0.5  # i2, i4
    # Pinned as a literal, not as a relationship: an assertion computed *through* the
    # function under test is satisfied by a mutant that breaks both sides equally, which is
    # how `hi - lo` -> `hi + lo` survived every gate in this repo.
    assert row.m_star == 1.0


def test_the_product_bound_is_hand_computable() -> None:
    """A depth-2 chain's predicted accuracy is the product of its components'."""
    arch = _archive()
    rows = {r.system: r for r in build_bridge([make_chain(("i2", "i4"), [])], arch, depth=2)}
    # A: 0.5 * 1.0 = 0.5 ; B: 1.0 * 0.0 = 0.0
    assert rows["A"].predicted_composite == 0.5
    assert rows["B"].predicted_composite == 0.0
    assert rows["A"].singleton == 0.625
    assert rows["A"].chains_used == 1
    assert rows["A"].chains_available == 1

    readout = predict([make_chain(("i2", "i4"), [])], arch, depth=2, seed=0)
    assert readout.accuracy == {"A": 0.5, "B": 0.0}
    assert readout.top_two_gap == 0.5
    assert readout.discriminating == 1.0  # the one chain separates the two systems


def test_the_noise_band_is_reported_with_the_share_that_is_structural_zero() -> None:
    """Seven of the eight cells are unanimous; only A/i2 varies.

    The band is the mean half-width over cells, and a unanimous cell contributes exactly
    0.0 because the bootstrap has no variation to resample. Reporting the band without
    that fraction makes an artefact of saturation look like a measurement of noise.
    """
    arch = _archive()
    assert unanimous_fraction(arch) == 7 / 8

    # Only A/i2 varies. Its bootstrap interval spans [0, 1] at n = 4, so its half-width is
    # 0.5, and the band is that one contribution averaged over all eight cells: 0.5/8.
    assert noise_band(arch, seed=0) == 0.0625
    assert ci95_for([1.0, 1.0, 0.0, 0.0], seed=0) == 1.0

    # k = 1 supports no band at all, and nonius refuses rather than inventing one.
    single = Archive(tuple(Verdict("A", i, 0, 1) for i in ("i1", "i2")))
    assert noise_band(single) is None
    assert unanimous_fraction(single) is None


def test_bootstrap_widths_are_reproducible_and_bounded() -> None:
    """Reproducibility, not hand-checked correctness -- and labelled as such.

    A percentile bootstrap's endpoints are not computable on paper, so what is pinned here
    is that the same input and seed give the same width, that the width is a width, and
    that a unanimous sample collapses to zero (the mechanism the band's bias comes from).
    """
    # The seed is a real parameter, not decoration. It needs a sample large enough for the
    # resample to land differently: at n = 4 the interval spans [0, 1] under every seed.
    twenty = [1.0] * 13 + [0.0] * 7
    assert ci95_for(twenty, seed=0) == pytest.approx(0.4)
    assert ci95_for(twenty, seed=2) == pytest.approx(0.45)
    assert ci95_for(twenty, seed=0) == ci95_for(twenty, seed=0), "must be seeded, not random"

    assert ci95_for([1.0, 1.0, 1.0, 1.0], seed=0) == 0.0
    assert ci95_for([0.5], seed=0) == 0.0  # one draw supports no interval
