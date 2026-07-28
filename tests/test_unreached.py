"""The regions no test executed.

Round 10's critic measured it: 538 executable lines in ``src/nonius`` were run by nothing,
and rounds 7-10 had been discovering, one hand-driven invocation at a time, what a coverage
run enumerates in ninety seconds. Five regions had never executed at all -- ``execute()``
past its guards, the ``run`` CLI verb, the archive loader, ``measure()``, and the bridge's
re-expression. Every finding those rounds produced in them was a symptom of that, not an
independent defect, so this file closes the generator rather than the symptoms.

``execute()`` is the only function in nonius that can spend money. It is exercised here
with a fake completer that records what it was asked and buys nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nonius.bridge import BridgeRow, imply_singleton, reexpress, render
from nonius.errors import ManifestError, NoniusError
from nonius.resolution import measure
from nonius.run import NotAuthorised, execute, load_preregistration

AUTHORISED = """
[run]
id = "test-run"
status = "authorised"
[population]
depths = [2]
composites_per_depth = 4
[systems]
models = ["m"]
k = 2
[[threshold]]
id = "q"
ruling = "BOUND-ALL-0004"
ceiling = 0.20
"""


def _prereg(tmp_path: Path, body: str = AUTHORISED) -> object:
    p = tmp_path / "prereg.toml"
    p.write_text(body, encoding="utf-8")
    return load_preregistration(p)


def _record(cid: str, depth: int = 2, text: str = "prompt") -> dict[str, object]:
    return {"id": cid, "depth": depth, "rendering": {"python": text}}


def test_execute_buys_exactly_k_draws_per_composite(tmp_path: Path) -> None:
    asked: list[str] = []

    def complete(prompt: str) -> str:
        asked.append(prompt)
        return f"answer to {prompt}"

    rows = execute(
        _prereg(tmp_path),  # type: ignore[arg-type]
        [_record("c1", text="one"), _record("c2", text="two")],
        complete,
        authorised=True,
    )
    # 2 composites x k=2. The count is the budget, so an off-by-one here is money.
    assert asked == ["one", "one", "two", "two"]
    assert [(r["composite"], r["draw"]) for r in rows] == [
        ("c1", 0), ("c1", 1), ("c2", 0), ("c2", 1),
    ]
    assert all(r["depth"] == 2 for r in rows)
    assert rows[0]["raw_output"] == "answer to one"


def test_execute_refuses_the_whole_set_before_spending_anything(tmp_path: Path) -> None:
    """A mid-loop refusal has already bought the records it got through."""
    spent: list[str] = []

    def complete(prompt: str) -> str:  # pragma: no cover - the point is it is not called
        spent.append(prompt)
        return ""

    bad_sets: list[tuple[list[object], type[NoniusError], str]] = [
        ([_record("ok"), {"depth": 2, "rendering": {"python": "x"}}], ManifestError, "'id'"),
        ([_record("ok"), _record("bad", depth=9)], NotAuthorised, "not in the pre-registered"),
        ([_record("ok"), {"id": "b", "depth": 2, "rendering": []}], ManifestError, "rendering"),
        ([_record("ok"), {"id": "b", "depth": "2", "rendering": {"python": "x"}}],
         ManifestError, "'depth' must be an integer"),
        ([_record("ok"), {"id": "b", "depth": 2, "rendering": {"python": 7}}],
         ManifestError, "must be a string"),
        ([_record("ok"), "not a record"], ManifestError, "not an object"),
        ([_record(f"c{n}") for n in range(5)], NotAuthorised, "more composites supplied"),
    ]
    for records, exc, match in bad_sets:
        with pytest.raises(exc, match=match):
            execute(_prereg(tmp_path), records, complete, authorised=True)  # type: ignore[arg-type]
    assert spent == [], "execute() bought completions from a set it went on to refuse"


def test_measure_refuses_ragged_input_rather_than_imputing_zero() -> None:
    """A composite a system was not run on is not a composite it failed."""
    observed = {
        "c1": {"A": 1.0, "B": 0.0},
        "c2": {"A": 0.0, "B": 1.0},
        "c3": {"A": 1.0},  # B never ran
    }
    with pytest.raises(ValueError, match="missing a system"):
        measure(observed, depth=2, quarantined=(), seed=0)

    # Quarantined composites are dropped before the raggedness check, so quarantining the
    # incomplete one makes the same input measurable.
    row = measure(observed, depth=2, quarantined=("c3",), seed=0)
    assert row.source == "measured"
    assert row.n == 2
    assert row.accuracy == {"A": 0.5, "B": 0.5}
    assert row.discriminating == 1.0  # both composites separate the two systems


def test_the_bridge_re_expression_is_exact_at_depth_one_and_inverts() -> None:
    assert reexpress(0.8, depth=1) == 0.8  # DEPTH-ALL-0003
    assert reexpress(0.5, depth=3) == 0.125
    assert imply_singleton(0.125, depth=3) == pytest.approx(0.5)
    assert imply_singleton(reexpress(0.7, 4), 4) == pytest.approx(0.7)

    for bad in (-0.1, 1.1):
        with pytest.raises(ValueError, match="out of range"):
            reexpress(bad, depth=2)
        with pytest.raises(ValueError, match="out of range"):
            imply_singleton(bad, depth=2)
    with pytest.raises(ValueError, match="depth must be"):
        reexpress(0.5, depth=0)
    with pytest.raises(ValueError, match="depth must be"):
        imply_singleton(0.5, depth=0)


def test_the_bridge_renders_absent_measurements_as_absent() -> None:
    """The measured half has never run, so its columns must read as missing, not as zero."""
    rows = [
        BridgeRow("sys", 2, 0.8, 0.64, None, 10, 10, None, None),
        BridgeRow("sys", 3, 0.8, 0.512, 0.6, 10, 10, 0.8434, 0.088),
    ]
    text = render(rows)
    assert "not a proof of measurement equivalence" in text
    unmeasured, measured = text.splitlines()[-2:]
    assert "measured      --" in unmeasured and "residual       --" in unmeasured
    assert "0.0000" not in unmeasured.split("predicted")[1].split("measured")[0][8:]
    assert "+0.0880" in measured


def test_the_run_verb_plans_without_spending(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from nonius.cli import main

    composites = tmp_path / "c.jsonl"
    composites.write_text(
        '{"id": "c1", "depth": 2, "rendering": {"python": "x"}}\n', encoding="utf-8"
    )
    prereg = tmp_path / "p.toml"
    prereg.write_text(AUTHORISED.replace('status = "authorised"', 'status = "designed"'), encoding="utf-8")

    assert main(["run", "--composites", str(composites), "--prereg", str(prereg)]) == 0
    out = capsys.readouterr().out
    assert "NOTHING HAS BEEN RUN" in out
    assert "quarantine ceiling: 0.20" in out


def test_the_run_verb_reports_a_torn_composites_file(tmp_path: Path) -> None:
    from nonius.cli import main

    composites = tmp_path / "c.jsonl"
    composites.write_text('{"id": "c1", "depth": 2}\nnot json\n', encoding="utf-8")
    prereg = tmp_path / "p.toml"
    prereg.write_text(AUTHORISED, encoding="utf-8")
    # 1, not 2: a refusal is a refusal (exit 1); exit 2 means the run completed with
    # errors, which would be a false report about a file that was never read.
    assert main(["run", "--composites", str(composites), "--prereg", str(prereg)]) == 1
