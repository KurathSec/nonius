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

from pathlib import Path

import pytest

from nonius.archive import Archive, Verdict
from nonius.bound import noise_band, unanimous_fraction
from nonius.bridge import build as build_bridge
from nonius.compose import make_chain
from nonius.resolution import ci95_for, predict, singleton_row

#: THREE systems, five items, k = 4. Deliberately asymmetric on every axis a mutation can
#: flip. Two systems is not enough: with two, changing a cell selector's `==` to `!=`
#: merely PERMUTES the cell set, so every aggregate over cells is unchanged and the mutant
#: survives. With three, `!=` merges two systems' draws into one cell and the aggregates
#: move. dead and floored are also given different items so a swapped comparison cannot
#: satisfy both.
#:
#: dead and floored have DIFFERENT COUNTS (2 vs 1), not merely different items: with one
#: each, flipping `== 1.0` to `!= 1.0` lands on the same total and survives.
#:
#:            i1        i2        i3        i4        i5        i6        mean
#:   A       4/4=1.0   2/4=0.5   0/4=0.0   4/4=1.0   3/4=0.75  4/4=1.0    0.708333
#:   B       4/4=1.0   4/4=1.0   0/4=0.0   0/4=0.0   1/4=0.25  4/4=1.0    0.541666
#:   C       4/4=1.0   0/4=0.0   0/4=0.0   2/4=0.5   4/4=1.0   4/4=1.0    0.583333
#:   stratum dead      discrim   floored   discrim   discrim   dead
CORRECT: dict[tuple[str, str], int] = {
    ("A", "i1"): 4, ("A", "i2"): 2, ("A", "i3"): 0, ("A", "i4"): 4, ("A", "i5"): 3, ("A", "i6"): 4,
    ("B", "i1"): 4, ("B", "i2"): 4, ("B", "i3"): 0, ("B", "i4"): 0, ("B", "i5"): 1, ("B", "i6"): 4,
    ("C", "i1"): 4, ("C", "i2"): 0, ("C", "i3"): 0, ("C", "i4"): 2, ("C", "i5"): 4, ("C", "i6"): 4,
}


def _archive() -> Archive:
    return Archive(
        tuple(
            Verdict(system, item, draw, 1 if draw < CORRECT[(system, item)] else 0)
            for system in ("A", "B", "C")
            for item in ("i1", "i2", "i3", "i4", "i5", "i6")
            for draw in range(4)
        )
    )


def test_archive_rates_and_strata_are_exact() -> None:
    arch = _archive()
    assert arch.k() == 4
    assert arch.items == ("i1", "i2", "i3", "i4", "i5", "i6")
    assert arch.rate("A", "i2") == 0.5  # 2 of 4
    assert arch.rate("B", "i2") == 1.0
    assert arch.per_item("i4") == {"A": 1.0, "B": 0.0, "C": 0.5}
    assert arch.stratum("i1") == "dead"
    assert arch.stratum("i2") == "discriminating"
    assert arch.stratum("i3") == "floored"
    assert arch.stratum("i4") == "discriminating"
    assert arch.stratum("i5") == "discriminating"  # 0.75 / 0.25 / 1.0
    assert arch.stratum("i6") == "dead"  # a SECOND dead item, so dead != floored in count


def test_the_singleton_readout_is_hand_computable() -> None:
    row = singleton_row(_archive(), seed=0)
    assert row.depth == 1
    assert row.n == 6
    # A: (1 + 0.5 + 0 + 1 + 0.75 + 1)/6 = 4.25/6 ; B: 3.25/6 ; C: 3.5/6
    assert row.accuracy == {
        "A": pytest.approx(4.25 / 6),
        "B": pytest.approx(3.25 / 6),
        "C": pytest.approx(3.5 / 6),
    }
    # top two, not top and bottom: 4.25/6 - 3.5/6 = 0.125, whereas the widest spread
    # (A minus B) is 0.1666...
    assert row.top_two_gap == pytest.approx(0.125)
    # dead and floored differ from each other AND from discriminating, so a mutant that
    # swaps the two comparisons cannot satisfy all three.
    assert row.dead == pytest.approx(2 / 6)  # i1, i6
    assert row.floored == pytest.approx(1 / 6)  # i3
    assert row.discriminating == 0.5  # i2, i4, i5
    # The caps are the AUDIT-ALL-0004 disclosure; pinning the row without them would
    # leave the thing the ruling exists to require unpinned.
    assert dict(row.caps) == {
        "population": "singleton",
        "items_available": 6,
        "items_used": 6,
        "items_skipped_incomplete": 0,
    }
    # Pinned as a literal, not as a relationship: an assertion computed *through* the
    # function under test is satisfied by a mutant that breaks both sides equally, which is
    # how `hi - lo` -> `hi + lo` survived every gate in this repo.
    assert row.m_star == pytest.approx(0.70833333)


def test_the_product_bound_is_hand_computable() -> None:
    """A depth-2 chain's predicted accuracy is the product of its components'."""
    arch = _archive()
    rows = {r.system: r for r in build_bridge([make_chain(("i2", "i4"), [])], arch, depth=2)}
    # A: 0.5 * 1.0 = 0.5 ; B: 1.0 * 0.0 = 0.0 ; C: 0.0 * 0.5 = 0.0
    assert rows["A"].predicted_composite == 0.5
    assert rows["B"].predicted_composite == 0.0
    assert rows["C"].predicted_composite == 0.0
    assert rows["A"].singleton == pytest.approx(4.25 / 6)
    assert rows["A"].chains_used == 1
    assert rows["A"].chains_available == 1

    readout = predict([make_chain(("i2", "i4"), [])], arch, depth=2, seed=0)
    assert readout.accuracy == {"A": 0.5, "B": 0.0, "C": 0.0}
    assert readout.top_two_gap == 0.5
    assert readout.discriminating == 1.0  # the one chain separates the systems


def test_the_noise_band_is_reported_with_the_share_that_is_structural_zero() -> None:
    """Fourteen of the eighteen cells are unanimous; A/i2, A/i5, B/i5 and C/i4 vary.

    The band is the mean half-width over cells, and a unanimous cell contributes exactly
    0.0 because the bootstrap has no variation to resample. Reporting the band without
    that fraction makes an artefact of saturation look like a measurement of noise.
    """
    arch = _archive()
    # 4 of 18 cells vary: A/i2, A/i5, B/i5, C/i4.
    assert unanimous_fraction(arch) == pytest.approx(14 / 18)

    assert noise_band(arch, seed=0) == pytest.approx(0.09722222)
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


def test_stdev_and_replicate_spread_have_literal_values() -> None:
    """`stdev` was asserted nowhere at all, so its body was free to be wrong.

    A mutation sweep replaced `(x - m) ** 2` with `(x + m) ** 2` and the whole suite
    stayed green. Sample standard deviation of 1, 2, 4, 8: mean 3.75, squared deviations
    7.5625 + 3.0625 + 0.0625 + 18.0625 = 28.75, /3 = 9.5833..., sqrt = 3.09569...
    """
    from nonius.stats import mean, stdev

    assert stdev([1.0, 2.0, 4.0, 8.0]) == pytest.approx(3.0956959)
    assert stdev([2.0, 2.0]) == 0.0  # no spread
    assert stdev([1.0]) == 0.0  # ddof 1 with one sample is undefined, reported as 0
    assert mean([1.0, 2.0, 6.0]) == 3.0

    # Four cells vary (A/i2, A/i5, B/i5, C/i4) and fourteen are unanimous at 0.0; the
    # mean over all eighteen is 0.1197055...
    assert _archive().replicate_spread() == pytest.approx(0.11970559, abs=1e-8)


def test_the_bootstrap_iteration_count_is_pinned() -> None:
    """`ci95_for` never passes `iters`, so every published m* rides on the default.

    Changing it silently moves every interval in the derived artifacts, and nothing else
    in the suite would notice.
    """
    import inspect

    from nonius.stats import ci95_bootstrap

    assert inspect.signature(ci95_bootstrap).parameters["iters"].default == 2000


def test_the_archive_loader_round_trips_every_supported_format(tmp_path: Path) -> None:
    """The whole input path was dead to the suite: replacing `load`'s body with a raise
    left every test passing.
    """
    import gzip

    from nonius.archive import dumps, load

    arch = _archive()
    jsonl = tmp_path / "a.jsonl"
    jsonl.write_text(dumps(arch), encoding="utf-8")
    assert load(jsonl).verdicts == arch.verdicts

    gz = tmp_path / "a.jsonl.gz"
    gz.write_bytes(gzip.compress(dumps(arch).encode("utf-8")))
    assert load(gz).verdicts == arch.verdicts

    csv_path = tmp_path / "a.csv"
    csv_path.write_text(
        "system,item,draw,correct\n"
        + "".join(f"{v.system},{v.item},{v.draw},{v.correct}\n" for v in arch.verdicts),
        encoding="utf-8",
    )
    assert load(csv_path).verdicts == arch.verdicts

    tsv = tmp_path / "a.tsv"
    tsv.write_text(
        "system\titem\tdraw\tcorrect\n"
        + "".join(f"{v.system}\t{v.item}\t{v.draw}\t{v.correct}\n" for v in arch.verdicts),
        encoding="utf-8",
    )
    assert load(tsv).verdicts == arch.verdicts


def test_the_archive_loader_refuses_what_it_cannot_read(tmp_path: Path) -> None:
    from nonius.archive import load
    from nonius.errors import ManifestError

    empty = tmp_path / "empty.csv"
    empty.write_text("system,item,draw,correct\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="no verdicts"):
        load(empty)

    torn = tmp_path / "torn.jsonl"
    torn.write_text('{"system":"A","item":"i","draw":0,"correct":1}\nnot json\n', encoding="utf-8")
    with pytest.raises(ManifestError, match="line 2"):
        load(torn)

    scored = tmp_path / "scored.jsonl"
    scored.write_text('{"system":"A","item":"i","draw":0,"correct":0.5}\n', encoding="utf-8")
    with pytest.raises(ManifestError, match="verdict is a verdict"):
        load(scored)
