"""The calibration corpus's oracle.

**This is a fixture, not a benchmark.** Its purpose is to exercise the composer against
values a human can verify with arithmetic on paper. It makes no claim about model
capability, it is not an item set anyone should score a system on, and nothing derived
from it is a finding. See tests/corpus/README.md and NOTICE.

Four operations, chosen to cover the composable tags and both liveness outcomes:

    sum       values: list[int]                       -> total: int
    threshold subject: int, cut: int, hi: str, lo: str -> verdict: str
    lookup    key: str, table: dict[str,str], default  -> route: str
    member    probe: int, pool: list[int]              -> present: bool

Bindings are *overrides*: a slot named in ``bindings`` replaces the item's own payload
value for that key, and every other key keeps the item's value. That is the contract the
whole composer relies on -- it is how a component is re-run under a changed input without
the item being rewritten.

Deterministic, total, and free of I/O.
"""

from __future__ import annotations

from collections.abc import Mapping

from nonius.model import Item, Scalar


def answer(item: Item, bindings: Mapping[str, Scalar]) -> dict[str, Scalar]:
    p: dict[str, object] = dict(item.payload)
    p.update(bindings)
    op = p.get("op")

    if op == "sum":
        values = p["values"]
        assert isinstance(values, list)
        return {"total": sum(int(v) for v in values)}

    if op == "threshold":
        subject, cut = int(p["subject"]), int(p["cut"])  # type: ignore[arg-type]
        return {"verdict": str(p["hi"]) if subject >= cut else str(p["lo"])}

    if op == "lookup":
        table = p["table"]
        assert isinstance(table, dict)
        return {"route": str(table.get(str(p["key"]), p["default"]))}

    if op == "member":
        pool = p["pool"]
        assert isinstance(pool, list)
        return {"present": int(p["probe"]) in [int(x) for x in pool]}  # type: ignore[arg-type]

    if op == "dual":
        # Two independent int slots on one item, so a single sink can absorb two upstream
        # components. That is the fan-in shape (DEPTH-ALL-0002), and without an item like
        # this a corpus whose link graph is shallow cannot reach higher component counts.
        cut = int(p["cut"])  # type: ignore[arg-type]
        return {
            "verdict_a": str(p["hi"]) if int(p["subject_a"]) >= cut else str(p["lo"]),  # type: ignore[arg-type]
            "verdict_b": str(p["hi"]) if int(p["subject_b"]) >= cut else str(p["lo"]),  # type: ignore[arg-type]
        }

    raise ValueError(f"unknown op: {op!r}")
