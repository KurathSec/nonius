"""Determinism is a tested contract, not a sentence (CORE-ALL-0002).

The claim is per-platform: the same inputs give byte-identical output in this process and
the next, under any hash seed. Cross-OS byte-identity is explicitly not claimed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from conftest import CORPUS, ROOT, corpus_items, corpus_oracle

from nonius.canonical import canonical_json, content_hash, qfloat
from nonius.compose import analyze, composite_id, make_chain, realize
from nonius.manifest import index
from nonius.model import Link
from nonius.realize import make_prompt_realizer


def test_canonical_json_is_stable() -> None:
    """CORE-ALL-0002: sorted keys, quantized floats, no dict-order dependence."""
    a = {"b": 1, "a": 2, "c": {"z": 0.1 + 0.2, "y": [3, 1]}}
    b = {"c": {"y": [3, 1], "z": 0.1 + 0.2}, "a": 2, "b": 1}
    assert canonical_json(a) == canonical_json(b)
    assert canonical_json(a) == '{"a":2,"b":1,"c":{"y":[3,1],"z":0.3}}'
    assert qfloat(1 / 3) == 0.333333333333
    assert content_hash(a) == content_hash(b)
    assert len(content_hash(a)) == 16


def test_composite_id_depends_only_on_meaning() -> None:
    """The hash moves when the composite's meaning moves, and not otherwise."""
    one = make_chain(("sum-a", "thr-live"), [Link(0, "total", 1, "subject", "int")])
    same = make_chain(("sum-a", "thr-live"), [Link(0, "total", 1, "subject", "int")])
    other = make_chain(("sum-b", "thr-live"), [Link(0, "total", 1, "subject", "int")])
    assert composite_id(one) == composite_id(same)
    assert composite_id(one) != composite_id(other)


def test_analysis_and_realization_repeat_exactly() -> None:
    items, oracle = corpus_items(), corpus_oracle()
    idx = index(items)
    first = analyze(items, oracle)
    second = analyze(items, oracle)
    assert [v.candidate for v in first.verdicts] == [v.candidate for v in second.verdicts]
    assert [v.live for v in first.verdicts] == [v.live for v in second.verdicts]

    chain = make_chain(
        ("sum-a", "thr-live", "lk-live"),
        [Link(0, "total", 1, "subject", "int"), Link(1, "verdict", 2, "key", "str")],
    )
    a, _ = realize(chain, idx, oracle, make_prompt_realizer(oracle))
    b, _ = realize(chain, idx, oracle, make_prompt_realizer(oracle))
    assert a.id == b.id
    assert a.realization.gold == b.realization.gold
    assert a.realization.rendering == b.realization.rendering


def _run(seed: str, args: list[str]) -> str:
    env = {
        "PYTHONHASHSEED": seed,
        "PYTHONPATH": str(CORPUS),
        "PATH": "/usr/bin:/bin",
        "HOME": str(Path.home()),
    }
    out = subprocess.run(
        [sys.executable, "-m", "nonius.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT.parent,
        check=True,
    )
    return out.stdout


def test_cli_output_is_byte_identical_under_two_hash_seeds() -> None:
    """A subprocess test: hash-order dependence only shows across processes."""
    args = [
        "audit",
        "--items",
        str(CORPUS / "items.jsonl"),
        "--oracle",
        "oracle:answer",
        "--json",
    ]
    a, b = _run("0", args), _run("1", args)
    assert a == b
    parsed: Any = json.loads(a)
    assert parsed["verdict"] == "composable_to_depth_3"


def test_compose_output_is_byte_identical_under_two_hash_seeds() -> None:
    args = [
        "compose",
        "--items",
        str(CORPUS / "items.jsonl"),
        "--oracle",
        "oracle:answer",
        "--depths",
        "2,3",
        "--limit",
        "20",
    ]
    assert _run("0", args) == _run("1", args)
