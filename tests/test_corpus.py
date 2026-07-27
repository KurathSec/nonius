"""The calibration corpus: every case, checked against hand-computed values.

Failure messages name the case and the rulings in dispute, because a corpus failure is a
disagreement about a decision, not about an implementation detail.
"""

from __future__ import annotations

from typing import Any

import pytest
from conftest import cases, corpus_items, corpus_oracle

from nonius.archive import Archive, Verdict
from nonius.audit import audit
from nonius.bound import assess, max_prediction, product_prediction
from nonius.compose import analyze, composite_id, make_chain, realize
from nonius.manifest import dumps, index, loads
from nonius.model import Link
from nonius.realize import make_prompt_realizer

CASES = cases()
IDS = [c["id"] for c in CASES]


@pytest.fixture(scope="module")
def items() -> Any:
    return corpus_items()


@pytest.fixture(scope="module")
def oracle() -> Any:
    return corpus_oracle()


@pytest.fixture(scope="module")
def analysis(items: Any, oracle: Any) -> Any:
    return analyze(items, oracle)


def _hdr(case: dict[str, Any]) -> str:
    return f"[{case['id']}] rulings in dispute: {', '.join(case['rulings'])}"


def _chain(case: dict[str, Any]) -> Any:
    exp = case["expect"]
    links = [Link(u, r, d, s, "") for u, r, d, s in exp["links"]]
    return make_chain(tuple(exp["components"]), links)


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_case(case: dict[str, Any], items: Any, oracle: Any, analysis: Any) -> None:
    kind = case["kind"]
    exp = case["expect"]
    hdr = _hdr(case)

    if kind == "manifest":
        assert len(items) == exp["items"], hdr
        assert sum(len(i.slots) for i in items) == exp["slots"], hdr
        assert sum(len(i.results) for i in items) == exp["results"], hdr
        for tag, n in exp["slot_tags"].items():
            assert sum(1 for i in items for s in i.slots if s.tag == tag) == n, f"{hdr} slot {tag}"
        for tag, n in exp["result_tags"].items():
            assert sum(1 for i in items for r in i.results if r.tag == tag) == n, (
                f"{hdr} result {tag}"
            )
        if exp.get("roundtrips"):
            assert loads(dumps(items)) == items, f"{hdr} manifest does not round-trip"

    elif kind == "link":
        found = [
            v
            for v in analysis.verdicts
            if v.candidate.upstream_item == exp["upstream"]
            and v.candidate.result == exp["result"]
            and v.candidate.downstream_item == exp["downstream"]
            and v.candidate.slot == exp["slot"]
        ]
        assert len(found) == 1, f"{hdr} expected exactly one candidate, got {len(found)}"
        v = found[0]
        assert v.live is exp["live"], f"{hdr} liveness: {v.reason}"
        assert v.distinct_outcomes == exp["distinct_outcomes"], hdr
        assert v.probed == exp["probed"], hdr
        if "diagnostic" in exp:
            codes = {d.code for d in analysis.diagnostics}
            assert exp["diagnostic"] in codes, f"{hdr} expected diagnostic {exp['diagnostic']}"

    elif kind == "no-candidate":
        found = [
            v
            for v in analysis.verdicts
            if v.candidate.downstream_item == exp["downstream"]
            and v.candidate.slot == exp["slot"]
            and (
                "upstream" not in exp
                or (
                    v.candidate.upstream_item == exp["upstream"]
                    and v.candidate.result == exp["result"]
                )
            )
        ]
        assert len(found) == exp["candidates"], f"{hdr} expected no candidate, got {found}"
        if "diagnostic" in exp:
            codes = {d.code for d in analysis.diagnostics}
            assert exp["diagnostic"] in codes, f"{hdr} expected diagnostic {exp['diagnostic']}"

    elif kind == "chain":
        chain = _chain(case)
        assert chain.depth == exp["depth"], f"{hdr} depth"
        assert chain.path_depth == exp["path_depth"], f"{hdr} path depth"
        assert len(chain.links) == exp["n_links"], f"{hdr} link count"
        composite, _ = realize(chain, index(items), oracle, make_prompt_realizer(oracle))
        assert composite.realization.gold_map() == exp["gold"], f"{hdr} gold"
        assert list(composite.realization.suppressed) == exp["suppressed"], f"{hdr} suppressed"
        assert composite.id == composite_id(chain), f"{hdr} id is not the content hash"

    elif kind == "suppression":
        chain = _chain(case)
        composite, _ = realize(chain, index(items), oracle, make_prompt_realizer(oracle))
        r = composite.realization
        if exp.get("bindings_empty"):
            assert dict(r.bindings) == {}, f"{hdr} bindings should be empty, got {r.bindings}"
        assert list(r.suppressed) == exp["suppressed"], hdr
        text = r.rendering["text"]
        for needle in exp.get("present_in_text", []):
            assert needle in text, f"{hdr} missing reference: {needle!r}"
        for needle in exp.get("absent_from_text", []):
            assert needle not in text, f"{hdr} unexpected text: {needle!r}"
        # The upstream answers must not be quoted as bindings anywhere.
        for name in r.suppressed:
            assert name not in r.bindings, f"{hdr} {name} leaked into bindings"

    elif kind == "bound":
        chain = make_chain(tuple(exp["components"]), [])
        arch = Archive(
            tuple(
                Verdict(system, item, draw, 1 if draw < hits else 0)
                for system, hits_by_item in (
                    ("A", {"sum-a": 4, "thr-live": 2, "lk-live": 4}),
                    ("B", {"sum-a": 2, "thr-live": 2, "lk-live": 2}),
                )
                for item, hits in hits_by_item.items()
                for draw in range(4)
            )
        )
        for system, want in exp["product"].items():
            got = product_prediction(arch, system, chain.components)
            assert got == pytest.approx(want), f"{hdr} product for {system}"
        for system, want in exp["maximum"].items():
            got = max_prediction(arch, system, chain.components)
            assert got == pytest.approx(want), f"{hdr} maximum for {system}"
        bounds = assess(
            "case", chain, arch, measured=dict(exp["measured"]), band=exp["band"]
        )
        quarantined = sorted(b.system for b in bounds if b.quarantined)
        assert quarantined == sorted(exp["quarantined"]), f"{hdr} quarantine"

    elif kind == "audit":
        report = audit(items, oracle, depths=(1, 2, 3), seed=0)
        assert report.verdict == exp["verdict"], hdr
        assert report.max_depth == exp["max_depth"], hdr
        assert report.items == exp["items"], hdr
        for key in exp.get("caps_present", []):
            assert key in report.caps, f"{hdr} caps missing {key} (AUDIT-ALL-0004)"

    elif kind == "audit-population":
        arch = Archive(
            tuple(
                Verdict("S", item.id, draw, 1)
                for item in items
                for draw in range(2)
            )
        )
        report = audit(items, oracle, archive=arch, depths=(2, 3), seed=0)
        predicted = [r for r in report.readouts if r.depth > 1]
        assert predicted, f"{hdr} no predicted readouts produced"
        for row in predicted:
            assert row.caps.get("population") == exp["population"], f"{hdr} depth {row.depth}"
            for key in exp.get("caps_present", []):
                assert key in row.caps, f"{hdr} depth {row.depth} caps missing {key}"

    else:  # pragma: no cover - a new kind must be added here deliberately
        raise AssertionError(f"{hdr} unknown case kind {kind!r}")


def test_every_case_shows_its_working() -> None:
    """A calibration case without hand arithmetic is not calibration, it is a snapshot."""
    for case in CASES:
        assert case.get("computed_by") == "hand", case["id"]
        assert len(case.get("notes", "").strip()) > 80, (
            f"{case['id']}: notes must show the arithmetic, not just assert the answer"
        )
        assert case.get("rulings"), f"{case['id']}: a case must name the rulings it exercises"
