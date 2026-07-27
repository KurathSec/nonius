"""The paid-run guard rails, and the harness exporters.

The run module is the only place in nonius that can spend money, so what is tested here is
mostly that it refuses.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import ROOT, corpus_items, corpus_oracle

from nonius.adapters.harness import inspect_ai_dataset, lm_eval_dataset, lm_eval_task_yaml
from nonius.compose import composite_record, make_chain, realize
from nonius.errors import NoniusError
from nonius.manifest import index
from nonius.model import Link
from nonius.realize import make_prompt_realizer
from nonius.run import NotAuthorised, execute, load_preregistration, plan

PREREG = ROOT.parent / "preregistration" / "run-01.toml"


@pytest.fixture(scope="module")
def records() -> list[dict[str, object]]:
    items, oracle = corpus_items(), corpus_oracle()
    chain = make_chain(
        ("sum-a", "thr-live", "lk-live"),
        [Link(0, "total", 1, "subject", "int"), Link(1, "verdict", 2, "key", "str")],
    )
    composite, _ = realize(chain, index(items), oracle, make_prompt_realizer(oracle))
    return [composite_record(composite)]


def test_preregistration_loads_and_declares_a_ceiling() -> None:
    prereg = load_preregistration(PREREG)
    assert prereg.id == "run-01"
    assert prereg.quarantine_ceiling == 0.20
    assert prereg.depths == (1, 2, 3, 5)  # depth 1 is KT-0's positive control
    assert prereg.reuse_ceiling == 100

    # The cap does not bind at depth 3: the link graph holds only 134 chains there, so a
    # budget computed from the cap alone would overstate the run by a third.
    assert prereg.ceiling_completions == 4 * 500 * 4 * 3
    assert prereg.planned_composites == {1: 55, 2: 500, 3: 134, 5: 500}
    assert prereg.planned_completions == (55 + 500 + 134 + 500) * 4 * 3 == 14268
    declared = int(str(prereg.raw["budget"]["estimated_completions"]))  # type: ignore[index]
    assert declared == prereg.planned_completions


def test_a_second_quarantine_ceiling_is_refused(tmp_path: Path) -> None:
    """Selected by the ruling it cites, not by position.

    The loader used to take the last threshold carrying a key named `ceiling`, so an
    unrelated threshold could silently replace the quarantine one. Six review rounds
    documented that footgun in three places; this removes it.
    """
    two = tmp_path / "two-ceilings.toml"
    two.write_text(
        '[run]\nid = "x"\nstatus = "designed_not_executed"\n'
        "[population]\ndepths = [2]\ncomposites_per_depth = 1\n"
        '[systems]\nmodels = ["m"]\nk = 1\n'
        '[[threshold]]\nid = "a"\nruling = "BOUND-ALL-0004"\nceiling = 0.20\n'
        '[[threshold]]\nid = "b"\nruling = "BOUND-ALL-0004"\nceiling = 0.99\n',
        encoding="utf-8",
    )
    with pytest.raises(NotAuthorised, match="2 quarantine ceilings"):
        load_preregistration(two)

    # A `ceiling` key that cites no ruling is not the quarantine ceiling, and saying so is
    # better than silently adopting it.
    unnamed = tmp_path / "unnamed.toml"
    unnamed.write_text(
        '[run]\nid = "x"\nstatus = "designed_not_executed"\n'
        "[population]\ndepths = [2]\ncomposites_per_depth = 1\n"
        '[systems]\nmodels = ["m"]\nk = 1\n'
        '[[threshold]]\nid = "reuse-ish"\nceiling = 120\n',
        encoding="utf-8",
    )
    with pytest.raises(NotAuthorised, match="none cites"):
        load_preregistration(unnamed)


def test_preregistration_without_a_ceiling_is_refused(tmp_path: Path) -> None:
    """BOUND-ALL-0004: no ceiling means the gate could only ever confirm itself."""
    bad = tmp_path / "no-ceiling.toml"
    bad.write_text(
        '[run]\nid = "x"\nstatus = "designed_not_executed"\n'
        "[population]\ndepths = [2]\ncomposites_per_depth = 1\n"
        '[systems]\nmodels = ["m"]\nk = 1\n',
        encoding="utf-8",
    )
    with pytest.raises(NotAuthorised, match="quarantine ceiling"):
        load_preregistration(bad)


def test_plan_spends_nothing_and_says_so(records: list[dict[str, object]]) -> None:
    text = plan(load_preregistration(PREREG), records)
    assert "NOTHING HAS BEEN RUN" in text
    assert "quarantine ceiling: 0.20" in text
    # depth 3 is in the pre-registered set; a depth outside it must be flagged, not run
    assert "depth  3" in text


def test_plan_forecasts_the_refusals_execute_enforces() -> None:
    """plan() and execute() must agree, or the plan describes a different run."""
    prereg = load_preregistration(PREREG)

    off_depth = plan(prereg, [{"id": "x", "depth": 8}])
    assert "REFUSED: not in the pre-registered depth set" in off_depth
    assert "execute() WOULD REFUSE this set" in off_depth

    over_cap = plan(
        prereg, [{"id": f"c{n}", "depth": 2} for n in range(prereg.composites_per_depth + 1)]
    )
    assert "over the 500 cap" in over_cap
    assert "execute() WOULD REFUSE this set" in over_cap

    ok = plan(prereg, [{"id": "c", "depth": 2}])
    assert "WOULD REFUSE" not in ok


def test_execute_refuses_without_authorisation(records: list[dict[str, object]]) -> None:
    prereg = load_preregistration(PREREG)

    def never_called(prompt: str) -> str:  # pragma: no cover - must not run
        raise AssertionError("execute() called the model without authorisation")

    with pytest.raises(NotAuthorised, match="authorised=True"):
        execute(prereg, records, never_called)

    # ...and still refuses when authorised, because the file says it is not.
    with pytest.raises(NotAuthorised, match="status"):
        execute(prereg, records, never_called, authorised=True)


def test_a_dead_run_is_distinguishable_from_a_null_one() -> None:
    """KT-0 exists because the other arms provably cannot tell those apart.

    product(p_i) <= max(p_i) for any p_i in [0,1], so a measured 0.0 is never strictly
    closer to the max than to the product: KT-1 cannot fire on a dead harness. KT-2
    quarantines only what beats its bound, and 0.0 beats nothing.
    """
    import tomllib

    from nonius.archive import Archive, Verdict
    from nonius.bound import assess, max_prediction, product_prediction, summarize

    arch = Archive(
        tuple(Verdict("S", item, d, 1 if d < 3 else 0) for item in ("x", "y") for d in range(4))
    )
    chain = make_chain(("x", "y"), [])
    product = product_prediction(arch, "S", chain.components)
    assert product is not None
    maximum = max_prediction(arch, "S", chain.components)
    assert maximum is not None
    assert abs(0.0 - product) <= abs(0.0 - maximum), "product must never exceed the max"

    bounds = assess("c", chain, arch, measured={"S": 0.0}, band=0.05)
    assert not any(b.quarantined for b in bounds)
    assert summarize(bounds, depth=2, ceiling=0.20).rate == 0.0

    # ...which is why the pre-registration carries an arm that CAN fire on a dead run.
    raw = tomllib.loads(PREREG.read_bytes().decode("utf-8"))
    kt0 = [t for t in raw["threshold"] if t["id"] == "KT-0-execution-validity"]
    assert kt0, "no execution-validity arm is registered"
    assert "ceiling" not in kt0[0], (
        "KT-0 must not use a key named 'ceiling': load_preregistration takes the last "
        "one it finds as the quarantine ceiling"
    )
    assert kt0[0]["floor_accuracy"] < 0.8385, "the floor must sit below the archive's own mean"


def test_the_shipped_preregistration_is_not_authorised() -> None:
    """A committed pre-registration that says 'authorised' would be a loaded gun."""
    prereg = load_preregistration(PREREG)
    assert prereg.status == "designed_not_executed"
    assert isinstance(NotAuthorised("x"), NoniusError)


def test_lm_eval_export(records: list[dict[str, object]]) -> None:
    out = lm_eval_dataset(records, language="text")
    row = json.loads(out.strip())
    assert row["depth"] == 3
    assert row["components"] == ["sum-a", "thr-live", "lk-live"]
    assert json.loads(row["answer"]) == {
        "c0_total": 6,
        "c1_verdict": "low",
        "c2_route": "ignore",
    }
    # What makes the chain bind: every linked slot is a *reference* to where the value
    # comes from, and the computed value itself is nowhere in the text. Asserted on the
    # numeric answer, because the string answer ("low") is also a word the lookup item's
    # own prompt legitimately contains -- absence of that would be the wrong test.
    answer = json.loads(row["answer"])
    assert "the value of `total` computed in Part 1" in row["prompt"]
    assert "the value of `verdict` computed in Part 2" in row["prompt"]
    assert str(answer["c0_total"]) not in row["prompt"]

    yaml = lm_eval_task_yaml(dataset_path="composites.jsonl")
    assert "exact_match" in yaml and "temperature: 0.0" in yaml


def test_inspect_export(records: list[dict[str, object]]) -> None:
    row = json.loads(inspect_ai_dataset(records, language="text").strip())
    assert set(row) == {"id", "input", "target", "metadata"}
    assert row["metadata"]["depth"] == 3
    assert json.loads(row["target"])["c2_route"] == "ignore"


def test_exporters_skip_a_missing_rendering(records: list[dict[str, object]]) -> None:
    assert lm_eval_dataset(records, language="klingon") == ""
    assert inspect_ai_dataset(records, language="klingon") == ""
