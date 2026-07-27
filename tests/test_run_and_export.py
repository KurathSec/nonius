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
    assert prereg.depths == (2, 3, 5)
    assert prereg.estimated_completions == 3 * 500 * 4 * 3


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


def test_plan_flags_depths_outside_the_preregistration() -> None:
    prereg = load_preregistration(PREREG)
    text = plan(prereg, [{"id": "x", "depth": 8}])
    assert "NOT in the pre-registered depth set" in text


def test_execute_refuses_without_authorisation(records: list[dict[str, object]]) -> None:
    prereg = load_preregistration(PREREG)

    def never_called(prompt: str) -> str:  # pragma: no cover - must not run
        raise AssertionError("execute() called the model without authorisation")

    with pytest.raises(NotAuthorised, match="authorised=True"):
        execute(prereg, records, never_called)

    # ...and still refuses when authorised, because the file says it is not.
    with pytest.raises(NotAuthorised, match="status"):
        execute(prereg, records, never_called, authorised=True)


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
