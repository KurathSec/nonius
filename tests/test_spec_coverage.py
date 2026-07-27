"""Gate 2 of 3: every ruling is exercised, and every cited ruling exists.

Two directions, both mechanical:

* every **active** ruling is covered -- by a calibration case that names it, or by a named
  test for the refusal-shaped rulings that have no value to compute;
* every ruling-id-shaped string anywhere in ``src/`` resolves, including in comments and
  docstrings, so a citation cannot rot into a lie.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import ROOT, cases

from nonius.spec.registry import all_rulings, get, spec_version

SRC = ROOT.parent / "src"

RULING_RE = re.compile(r"\b(?:CORE|DEPTH|LINK|EMIT|BOUND|AUDIT)-(?:ALL)-\d{4}\b")

#: Rulings covered by a named test rather than a calibration case, because what they
#: assert is a refusal and there is no number to hand-compute. Each entry names the test
#: that covers it; the mapping is checked against the test files, so an entry pointing at
#: a test that no longer exists fails the build.
TEST_COVERED: dict[str, str] = {
    "CORE-ALL-0002": "tests/test_determinism.py::test_canonical_json_is_stable",
    "DEPTH-ALL-0002": "tests/test_corpus.py::test_case",
    "LINK-ALL-0004": "tests/test_refusals.py::test_slot_takes_one_link",
    "LINK-ALL-0005": "tests/test_refusals.py::test_cycles_are_refused",
    "LINK-ALL-0006": "tests/test_refusals.py::test_reuse_above_the_ceiling_is_refused",
    "EMIT-ALL-0004": "tests/test_refusals.py::test_composing_and_auditing_touch_no_network",
    "BOUND-ALL-0002": "tests/test_refusals.py::test_no_band_without_replicates",
    "BOUND-ALL-0004": "tests/test_refusals.py::test_quarantine_rate_is_reported_against_a_ceiling",
    "AUDIT-ALL-0003": "tests/test_refusals.py::test_composing_and_auditing_touch_no_network",
}

#: Shrink-only. Adding to this list is a review-visible act of debt; the 1.0 gate is an
#: empty list. It is empty today and should stay that way.
UNCOVERED: frozenset[str] = frozenset()


def test_every_active_ruling_is_covered() -> None:
    by_case: dict[str, list[str]] = {}
    for case in cases():
        for rid in case["rulings"]:
            by_case.setdefault(rid, []).append(case["id"])

    missing = []
    for ruling in all_rulings():
        if ruling.status != "active" or ruling.id in UNCOVERED:
            continue
        if ruling.id in by_case or ruling.id in TEST_COVERED:
            continue
        missing.append(ruling.id)
    assert not missing, f"rulings with no corpus case and no named test: {missing}"


def test_examples_cite_back() -> None:
    """A self-attested example is vacuous: the case must name the ruling too."""
    by_case = {c["id"]: set(c["rulings"]) for c in cases()}
    for ruling in all_rulings():
        for case_id in ruling.examples:
            assert case_id in by_case, f"{ruling.id} cites unknown case {case_id!r}"
            assert ruling.id in by_case[case_id], (
                f"{ruling.id} cites {case_id}, but that case does not name it"
            )


def test_cases_cite_real_rulings() -> None:
    for case in cases():
        for rid in case["rulings"]:
            assert get(rid).id == rid


def test_named_tests_exist() -> None:
    for rid, target in sorted(TEST_COVERED.items()):
        path, _, name = target.partition("::")
        source = (ROOT.parent / path).read_text(encoding="utf-8")
        assert f"def {name}(" in source, f"{rid} cites missing test {target}"


@pytest.mark.parametrize(
    "path", sorted(SRC.rglob("*.py")), ids=lambda p: str(p.relative_to(SRC))
)
def test_every_cited_ruling_resolves(path: Path) -> None:
    """Including in comments and docstrings: a citation that cannot rot is the point."""
    for rid in sorted(set(RULING_RE.findall(path.read_text(encoding="utf-8")))):
        assert get(rid).id == rid, f"{path}: phantom ruling {rid}"


def test_superseded_rulings_name_an_active_successor() -> None:
    for ruling in all_rulings():
        if ruling.status == "superseded":
            assert ruling.superseded_by, f"{ruling.id} is superseded by nothing"
            assert get(ruling.superseded_by).status == "active"
        else:
            assert not ruling.superseded_by, (
                f"{ruling.id} names a successor but is not superseded"
            )


def test_spec_version_is_semver() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", spec_version())
