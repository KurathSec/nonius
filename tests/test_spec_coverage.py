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

#: Superseded means FROZEN. The text of a retired ruling is the historical record of a
#: decision someone could already have published a number under, so it is never edited --
#: a new meaning gets a new id (ARCHITECTURE.md section 4). These digests make that
#: mechanical rather than a habit, because the way it actually got broken was a blind
#: string replacement that matched the same sentence in a retired ruling and its
#: successor and rewrote both. Changing a digest here is almost always the bug, not the
#: fix; pin a new entry only at the moment a ruling is superseded.
FROZEN_SUPERSEDED: dict[str, str] = {
    "AUDIT-ALL-0001": "acac3f28d14283e1",
    "DEPTH-ALL-0001": "6bc41821b5f0d4f7",
    "EMIT-ALL-0003": "e39f581463cf26e0",
    "LINK-ALL-0002": "5c0c324e9cf715b1",
}


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
    """Including in comments and docstrings: a citation that cannot rot is the point.

    Existence is not enough. A superseded id in a docstring reads as the current rule just
    as a phantom one reads as a real one, and only ``require()`` calls were status-checked.
    """
    for rid in sorted(set(RULING_RE.findall(path.read_text(encoding="utf-8")))):
        ruling = get(rid)
        assert ruling.id == rid, f"{path}: phantom ruling {rid}"
        assert ruling.status == "active", (
            f"{path.relative_to(SRC)} cites {rid}, which is {ruling.status} "
            f"(successor: {ruling.superseded_by}). Cite the successor."
        )


#: Files whose ruling citations are HISTORY, not current-tense claims, and so may name a
#: superseded id: the spec's own changelog and ruling text (a supersession has to name what
#: it replaced), the package changelog's record of what each version decided, and the corpus
#: cases, which list both a retired ruling and its successor so the example still cites back.
HISTORICAL_CITATIONS: frozenset[str] = frozenset(
    {
        "CHANGELOG.md",
        "src/nonius/spec/rulings/index.toml",
        "src/nonius/spec/rulings/audit.toml",
        "src/nonius/spec/rulings/core.toml",
        "src/nonius/spec/rulings/bound.toml",
        "src/nonius/spec/rulings/depth.toml",
        "src/nonius/spec/rulings/emit.toml",
        "src/nonius/spec/rulings/link.toml",
        "docs/spec/rulings.md",
    }
)

#: Shipped prose whose ruling citations are read as the current rule. Selected by suffix
#: and by name, because two of the files that matter carry no matching extension: NOTICE
#: states the claim boundary and CITATION.cff is what a reader cites.
PROSE_SUFFIXES: frozenset[str] = frozenset({".md", ".toml", ".cff", ".yml", ".yaml"})
PROSE_NAMES: frozenset[str] = frozenset({"NOTICE", "LICENSE"})


def _frozen_digest(ruling: object) -> str:
    import hashlib

    # Everything tools/render_rulings.py publishes for a retired ruling, including the
    # section it appears under and the successor it names: a record whose heading or
    # successor could be rewritten unnoticed is not frozen.
    parts = (
        ruling.id,  # type: ignore[attr-defined]
        ruling.topic,  # type: ignore[attr-defined]
        ruling.title,  # type: ignore[attr-defined]
        ruling.statement,  # type: ignore[attr-defined]
        ruling.rationale,  # type: ignore[attr-defined]
        ruling.superseded_by,  # type: ignore[attr-defined]
        *ruling.examples,  # type: ignore[attr-defined]
    )
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:16]


def test_prose_cites_live_rulings() -> None:
    """A superseded id in current-tense prose reads as the current rule, and is not.

    ``require()`` guards code citations; nothing guarded prose. Round 3 of this project's
    own review found five documents still presenting retired rulings as live, including the
    one whose stated argument the spec had explicitly retracted as wrong.
    """
    root = ROOT.parent
    stale: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in PROSE_SUFFIXES and path.name not in PROSE_NAMES:
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith((".venv/", "site/", "tests/corpus/cases/")) or rel in HISTORICAL_CITATIONS:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for rid in RULING_RE.findall(line):
                if get(rid).status == "superseded":
                    stale.append(f"{rel}:{n} cites {rid} (-> {get(rid).superseded_by})")
    assert not stale, "prose cites superseded rulings as current:\n  " + "\n  ".join(stale)


def test_superseded_ruling_text_is_frozen() -> None:
    """A retired ruling's words are a record, not a draft.

    Round 3 of this project's own review found DEPTH-ALL-0001's statement had been rewritten
    in place while it was already superseded -- collateral from a string replacement that
    matched both it and its successor. Nothing caught it, because the only check on retired
    rulings was that they named a live successor.
    """
    superseded = {r.id: r for r in all_rulings() if r.status == "superseded"}
    assert set(superseded) == set(FROZEN_SUPERSEDED), (
        "a ruling was superseded without pinning its text (or a pin outlived its ruling): "
        f"{sorted(set(superseded) ^ set(FROZEN_SUPERSEDED))}"
    )
    for rid, ruling in sorted(superseded.items()):
        assert _frozen_digest(ruling) == FROZEN_SUPERSEDED[rid], (
            f"{rid} is superseded, so its text is frozen history, and it changed. "
            f"Restore it; if the decision needs restating, supersede the successor."
        )


def test_superseded_rulings_name_an_active_successor() -> None:
    for ruling in all_rulings():
        if ruling.status == "superseded":
            assert ruling.superseded_by, f"{ruling.id} is superseded by nothing"
            assert get(ruling.superseded_by).status == "active"
        else:
            assert not ruling.superseded_by, (
                f"{ruling.id} names a successor but is not superseded"
            )


def test_require_refuses_a_superseded_ruling() -> None:
    """A decision that moved must take its citations with it.

    Round 2 of the project's own review found three modules still bound to rulings that had
    been superseded in round 1, because `require()` only checked existence. This is that
    hole closed, and the test that keeps it closed.
    """
    from nonius.errors import SpecError
    from nonius.spec.registry import require

    superseded = [r for r in all_rulings() if r.status == "superseded"]
    assert superseded, "expected at least one superseded ruling to test against"
    for ruling in superseded:
        with pytest.raises(SpecError, match="superseded"):
            require(ruling.id)


def test_no_module_binds_itself_to_a_superseded_ruling() -> None:
    """Every ``require(...)`` argument in src/ names an active ruling."""
    call = re.compile(r'require\(\s*"([A-Z]+-ALL-\d{4})"\s*\)')
    for path in sorted(SRC.rglob("*.py")):
        for rid in call.findall(path.read_text(encoding="utf-8")):
            assert get(rid).status == "active", (
                f"{path.relative_to(SRC)} binds to {rid}, which is "
                f"{get(rid).status} (successor: {get(rid).superseded_by})"
            )


def test_changelog_stamp_matches_the_live_spec() -> None:
    """The [Unreleased] entry states two versions; both must be the real ones.

    CHANGELOG.md's own preamble makes the stamp load-bearing and RELEASING.md cuts a
    release by promoting that exact line, so a stale stamp ships a wrong claim. Round 2
    rewrote the prose under this stamp and left the stamp itself behind.
    """
    from nonius._version import __version__

    text = (ROOT.parent / "CHANGELOG.md").read_text(encoding="utf-8")
    stamps = re.findall(r"^- package (\S+) . spec (\S+)$", text, re.M)
    assert stamps, "CHANGELOG.md has no `- package X . spec Y` stamp"
    package, spec = stamps[0]
    assert package == __version__, f"changelog says package {package}, code says {__version__}"
    assert spec == spec_version(), f"changelog says spec {spec}, registry says {spec_version()}"


def test_spec_version_is_semver() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", spec_version())
