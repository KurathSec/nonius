"""The rulings that are about refusing, not about a value.

These decisions have no calibration case because there is no number to compute by hand:
what they assert is that nonius declines to do something. The spec-coverage gate knows
about them by name (see ``TEST_COVERED`` in tests/test_spec_coverage.py), so a ruling can
never be covered by nothing at all.
"""

from __future__ import annotations

import socket
from collections.abc import Mapping
from typing import Any

import pytest
from conftest import corpus_items, corpus_oracle

from nonius.archive import Archive, Verdict
from nonius.audit import audit
from nonius.bound import ReuseCeilingExceeded, assess, guard_reuse, noise_band, summarize
from nonius.compose import analyze, make_chain, realize, reuse_multiplicity
from nonius.errors import GoldDisagreementError, LinkError, LiteralLeakError
from nonius.manifest import index
from nonius.model import Link, Realization
from nonius.realize import make_prompt_realizer


@pytest.fixture(scope="module")
def items() -> Any:
    return corpus_items()


@pytest.fixture(scope="module")
def oracle() -> Any:
    return corpus_oracle()


def test_slot_takes_one_link(items: Any) -> None:
    """LINK-ALL-0004: two sources for one slot is not a substitution."""
    links = [
        Link(0, "total", 2, "subject_a", "int"),
        Link(1, "total", 2, "subject_a", "int"),
    ]
    with pytest.raises(LinkError, match="more than one incoming link"):
        make_chain(("sum-a", "sum-b", "dual-a"), links)


def test_cycles_are_refused() -> None:
    """LINK-ALL-0005: a chain whose links form a cycle has no evaluation order."""
    links = [
        Link(0, "verdict", 1, "key", "str"),
        Link(1, "route", 0, "subject", "str"),
    ]
    with pytest.raises(LinkError, match="cycle"):
        make_chain(("thr-live", "lk-live"), links)


def test_self_link_is_refused() -> None:
    """LINK-ALL-0005: an item may not feed itself."""
    with pytest.raises(LinkError):
        make_chain(("thr-live",), [Link(0, "verdict", 0, "subject", "str")])


def test_reuse_multiplicity_is_counted() -> None:
    """LINK-ALL-0006: reuse is counted so a product bound cannot quietly over-count."""
    a = make_chain(("sum-a", "thr-live"), [Link(0, "total", 1, "subject", "int")])
    b = make_chain(("sum-b", "thr-live"), [Link(0, "total", 1, "subject", "int")])
    counts = reuse_multiplicity([a, b])
    assert counts == {"sum-a": 1, "sum-b": 1, "thr-live": 2}


def test_reuse_above_the_ceiling_is_refused() -> None:
    """LINK-ALL-0006: a set this correlated gets no product bound, only a refusal."""
    chains = [
        make_chain(("sum-a", "thr-live"), [Link(0, "total", 1, "subject", "int")]),
        make_chain(("sum-a", "thr-dead"), [Link(0, "total", 1, "subject", "int")]),
        make_chain(("sum-b", "thr-live"), [Link(0, "total", 1, "subject", "int")]),
    ]
    report = guard_reuse(chains, ceiling=2)
    assert report.worst == ("sum-a", 2)
    assert not report.exceeds_ceiling
    assert "within ceiling" in report.line()

    with pytest.raises(ReuseCeilingExceeded, match="LINK-ALL-0006"):
        guard_reuse(chains, ceiling=1)

    with pytest.raises(TypeError):
        guard_reuse(chains)  # type: ignore[call-arg]


def test_singleton_population_keeps_items_no_link_touches(items: Any, oracle: Any) -> None:
    """DEPTH-ALL-0003: a depth-1 composite is the item, link or no link."""
    from nonius.audit import constructible, singletons

    analysis = analyze(items, oracle)
    every = {c.components[0] for c in singletons(items)}
    linked = {c.components[0] for c in constructible(analysis, 1)}
    assert every == {i.id for i in items}
    # lk-miss carries no live link, so the link graph loses it -- but it is still a
    # perfectly good singleton, and the depth-1 baseline must not quietly change population.
    assert "lk-miss" in every and "lk-miss" not in linked


def test_a_refusing_oracle_is_not_reported_as_a_dead_link(items: Any) -> None:
    """LINK-ALL-0007: 'never varies' is a cause; it must not be asserted untested."""
    from nonius.model import Item, ResultVar, Scalar, Slot

    def picky(item: Item, bindings: Mapping[str, Scalar]) -> dict[str, Scalar]:
        if item.id == "down" and "n" in bindings:
            raise RuntimeError("this oracle refuses substituted values")
        return {"v": 1} if item.id == "up" else {"w": 2}

    up = Item(id="up", results=(ResultVar("v", "int", codomain=(1, 2)),))
    down = Item(
        id="down", slots=(Slot("n", "int"),), results=(ResultVar("w", "int", codomain=(2,)),)
    )
    analysis = analyze([up, down], picky)
    verdict = next(v for v in analysis.verdicts if v.candidate.downstream_item == "down")
    assert not verdict.live
    assert "refused" in verdict.reason
    codes = {d.code for d in analysis.diagnostics}
    assert "oracle-raised" in codes and "link-dead" not in codes


def test_literal_leak_is_refused(items: Any, oracle: Any) -> None:
    """EMIT-ALL-0001: a realizer that still binds a fed slot is refused, loudly."""
    chain = make_chain(("sum-a", "thr-live"), [Link(0, "total", 1, "subject", "int")])
    honest = make_prompt_realizer(oracle)

    def leaky(components: Any, links: Any) -> Realization:
        good = honest(components, links)
        # Put the upstream answer back where a system could read it.
        return Realization(
            gold=good.gold,
            rendering=good.rendering,
            bindings={**good.bindings, "c1_subject": 6},
            suppressed=good.suppressed,
            meta=good.meta,
        )

    with pytest.raises(LiteralLeakError, match="EMIT-ALL-0001"):
        realize(chain, index(items), oracle, leaky)


def test_gold_disagreement_is_refused(items: Any, oracle: Any) -> None:
    """EMIT-ALL-0002: a realizer whose gold does not match the chained oracles is refused."""
    chain = make_chain(("sum-a", "thr-live"), [Link(0, "total", 1, "subject", "int")])
    honest = make_prompt_realizer(oracle)

    def wrong(components: Any, links: Any) -> Realization:
        good = honest(components, links)
        bad = tuple((k, "WRONG" if k == "c1_verdict" else v) for k, v in good.gold)
        return Realization(
            gold=bad,
            rendering=good.rendering,
            bindings=good.bindings,
            suppressed=good.suppressed,
            meta=good.meta,
        )

    with pytest.raises(GoldDisagreementError, match="EMIT-ALL-0002"):
        realize(chain, index(items), oracle, wrong)


def test_composing_and_auditing_touch_no_network(
    items: Any, oracle: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EMIT-ALL-0004 and AUDIT-ALL-0003: offline is a tested property, not a promise."""

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("nonius opened a socket")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)

    report = audit(items, oracle, depths=(1, 2, 3))
    assert report.verdict.startswith("composable")

    analysis = analyze(items, oracle)
    chain = make_chain(("sum-a", "thr-live"), [Link(0, "total", 1, "subject", "int")])
    composite, _ = realize(chain, index(items), oracle, make_prompt_realizer(oracle))
    assert composite.id
    assert analysis.live


def test_no_band_without_replicates() -> None:
    """BOUND-ALL-0002: an archive with k = 1 supports no band, so none is invented."""
    single = Archive(tuple(Verdict("S", f"i{n}", 0, n % 2) for n in range(6)))
    assert single.k() == 1
    assert noise_band(single) is None

    chain = make_chain(("i0", "i1"), [])
    bounds = assess("c", chain, single, measured={"S": 1.0}, band=None)
    assert not any(b.quarantined for b in bounds)
    assert any("no noise band" in b.reason for b in bounds)


def test_quarantine_rate_is_reported_against_a_ceiling() -> None:
    """BOUND-ALL-0004: the ceiling is required, and printed next to the observed rate."""
    arch = Archive(
        tuple(
            Verdict("S", item, draw, 1 if draw < 2 else 0)
            for item in ("i0", "i1")
            for draw in range(4)
        )
    )
    chain = make_chain(("i0", "i1"), [])
    bounds = assess("c", chain, arch, measured={"S": 1.0}, band=0.05)
    report = summarize(bounds, depth=2, ceiling=0.20)

    assert report.assessed == 1
    assert report.quarantined == 1
    assert report.rate == 1.0
    assert report.exceeds_ceiling
    line = report.line()
    assert "0.2000" in line and "OVER CEILING" in line

    with pytest.raises(TypeError):
        summarize(bounds, depth=2)  # type: ignore[call-arg]
