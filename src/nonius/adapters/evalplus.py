"""The EvalPlus adapter: nonius pointed at HumanEval+ (ARCHITECTURE.md section 2).

The second subject, and the one the author did not build. EvalPlus supplies the items, the
oracle and (through its released raw samples) the verdict archive; nonius claims none of
them. See ../../../NOTICE for the boundary.

Why it qualifies. EvalPlus's gold is *computed*, never stored: ``get_groundtruth()`` runs
the canonical solution over the input tuples and caches the result, and grading compares a
candidate's output against that recomputation rather than against the ``test`` field's
asserts, which EvalPlus does not read. So an item is a program with separable arguments,
which is exactly ``oracle(item, bindings)``. Verified here rather than assumed: see
``tests/test_evalplus_adapter.py``.

Three facts about this subject that the audit must state rather than absorb:

* **Items carry no family label.** HumanEval ships none. Any stratum here is
  adapter-invented and is reported as such.
* **Results are anonymous.** Each item returns one unnamed value, so the result name is
  synthetic. There is nothing in the subject to name it after.
* **A ``str`` result carries no live link**, because ``PROBE_STR`` is empty by design
  (LINK-ALL-0003) and no honest finite codomain can be declared for a string-returning
  program. Manufacturing one from observed outputs would be a probe set wearing a
  codomain's name.

This adapter EXECUTES third-party code. ``tests/test_layering.py`` checks that the adapter
itself never opens a file for writing; it cannot see inside ``exec``. The isolation that
carries that guarantee is the subprocess in ``_evalplus_worker``.
"""

from __future__ import annotations

import ast
import gzip
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from nonius.errors import CompositionError, ManifestError, OracleError
from nonius.model import Item, Realization, ResultVar, Scalar, Slot, TypeTag, qualified

ENV_DATA = "NONIUS_EVALPLUS_DATA"

#: Excluded outright, with the reason recorded. The oracle protocol requires the same
#: bindings to give the same results in this process and the next (nonius.oracle); this
#: item's canonical solution calls ``random.randint`` in an unseeded Miller-Rabin test.
NONDETERMINISTIC: frozenset[str] = frozenset({"HumanEval/39"})

#: ``find_zero`` has no value gold at all: EvalPlus grades it with a property oracle
#: (|poly(xs, out)| <= atol) rather than by equality, so a composed value gold would be
#: meaningless for it.
PROPERTY_ORACLE: frozenset[str] = frozenset({"HumanEval/32"})

_TAGS: dict[type, TypeTag] = {bool: "bool", int: "int", str: "str", float: "float"}


def data_path() -> Path:
    raw = os.environ.get(ENV_DATA)
    if not raw:
        raise ManifestError(
            f"set {ENV_DATA} to HumanEvalPlus.jsonl.gz (released by evalplus, not shipped "
            f"here: this repository claims none of the subject's data)"
        )
    p = Path(raw)
    if not p.exists():
        raise ManifestError(f"{ENV_DATA}={raw} does not exist")
    return p


def _rows(path: Path) -> list[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _signature(prompt: str, entry_point: str) -> list[str] | None:
    """Parameter names of the entry point, from the prompt's own AST.

    Returns ``None`` when the signature is anything other than plain positional parameters:
    a ``*args``, ``**kwargs`` or defaulted parameter would make the positional call
    convention ambiguous, and guessing is how an adapter invents data.
    """
    try:
        tree = ast.parse(prompt)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == entry_point:
            a = node.args
            if a.vararg or a.kwarg or a.defaults or a.kwonlyargs or a.posonlyargs:
                return None
            return [x.arg for x in a.args]
    return None


def _tag_of(values: Sequence[Any]) -> TypeTag | None:
    """The scalar tag a parameter takes across every observed input, or None.

    bool before int, matching CORE-ALL-0001: ``isinstance(True, int)`` is true, and a bool
    slot fed an int is a different question from an int slot fed an int.
    """
    kinds = {type(v) for v in values}
    if len(kinds) != 1:
        return None
    return _TAGS.get(kinds.pop())


#: The single, synthetic result name. HumanEval items return one unnamed value; this name
#: comes from the adapter and not from the subject, and the audit reports it that way.
RESULT = "value"


def items(path: str | Path | None = None) -> tuple[Item, ...]:
    """The HumanEval+ manifest, read from the released dataset.

    A parameter becomes a *slot* only when it holds the same scalar type across every
    shipped input tuple. A ``List[int]`` parameter cannot be a slot at all -- nonius slots
    are ``Scalar`` -- so it stays in the payload as the item's own baked binding. That is a
    restriction on what this subject can compose, and it is reported rather than worked
    around.
    """
    rows = _rows(Path(path) if path is not None else data_path())
    out: list[Item] = []
    for r in rows:
        task_id = str(r["task_id"])
        if task_id in NONDETERMINISTIC or task_id in PROPERTY_ORACLE:
            continue
        names = _signature(str(r["prompt"]), str(r["entry_point"]))
        base = list(r.get("base_input") or [])
        if not names or not base:
            continue
        if any(len(tuple(t)) != len(names) for t in base):
            continue  # arity disagreement: the positional convention would be a guess

        slots: list[Slot] = []
        for i, name in enumerate(names):
            tag = _tag_of([t[i] for t in base])
            # float is a legal tag but carries no link (COMPOSABLE_TAGS), so recording it
            # keeps the audit's refusal honest rather than hiding the parameter.
            if tag is not None:
                slots.append(Slot(name=name, tag=tag, consumer=str(r["entry_point"])))

        result_tag = _result_tag(r)
        if result_tag is None:
            continue  # no observable scalar result: nothing to pipe onward
        out.append(
            Item(
                id=task_id,
                slots=tuple(slots),
                results=(ResultVar(name=RESULT, tag=result_tag, codomain=None),),
                # HumanEval ships no topic label. Empty, deliberately: an adapter-invented
                # stratum would put a made-up axis into the reachability table.
                family="",
                payload={
                    "prompt": r["prompt"],
                    "contract": r.get("contract", ""),
                    "canonical_solution": r["canonical_solution"],
                    "entry_point": r["entry_point"],
                    "parameters": names,
                    "bindings": {n: t for n, t in zip(names, base[0], strict=True)},
                    "atol": r.get("atol", 0),
                },
            )
        )
    return tuple(out)


def _result_tag(row: Mapping[str, Any]) -> TypeTag | None:
    """The tag of the item's return value, observed by running it on its own first input."""
    r = _run(
        str(row["prompt"]) + str(row["canonical_solution"]),
        str(row["entry_point"]),
        list(row["base_input"][0]),
    )
    if not r["ok"]:
        return None
    return _TAGS.get(type(r["value"]))


def _run(source: str, entry_point: str, args: Sequence[Any]) -> dict[str, Any]:
    """Execute the subject out of process, always. Never in this interpreter."""
    req = json.dumps({"source": source, "entry_point": entry_point, "args": list(args)})
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "nonius.adapters._evalplus_worker"],
            input=req, capture_output=True, text=True, timeout=10,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout: the subject did not terminate"}
    if proc.returncode != 0 or not proc.stdout:
        return {"ok": False, "error": f"worker exited {proc.returncode}: {proc.stderr[:200]}"}
    result: dict[str, Any] = json.loads(proc.stdout)
    return result


def oracle(item: Item, bindings: Mapping[str, Scalar]) -> Mapping[str, Scalar]:
    """``oracle(item, bindings) -> {"value": ...}``, EvalPlus's own recomputation.

    Bindings are overrides on the item's own first shipped input, which is the contract
    ``nonius.oracle`` states. The contract is prepended to the source, so an input outside
    the item's declared domain raises and the link is refused rather than silently graded
    against whatever the reference happened to return.
    """
    payload = item.payload
    raw_bindings = payload["bindings"]
    raw_params = payload["parameters"]
    if not isinstance(raw_bindings, dict) or not isinstance(raw_params, list):
        raise OracleError(f"{item.id}: payload is not an evalplus item")
    args: dict[str, Any] = dict(raw_bindings)
    for k, v in bindings.items():
        if k not in args:
            raise OracleError(f"{item.id}: no parameter named {k!r}")
        args[k] = v
    ordered = [args[str(n)] for n in raw_params]
    source = str(payload["prompt"]) + str(payload["contract"]) + str(payload["canonical_solution"])
    r = _run(source, str(payload["entry_point"]), ordered)
    if not r["ok"]:
        # Every failure is a refusal, never a gold. A contract rejection, a crash and a
        # timeout are indistinguishable in what they license: this composite has no gold.
        raise OracleError(f"{item.id}: {r['error']}")
    value = r["value"]
    if not isinstance(value, (bool, int, float, str)) and value is not None:
        raise OracleError(f"{item.id}: result is {type(value).__name__}, not a scalar")
    return {RESULT: value}


def _payload(item: Item) -> tuple[str, str, list[str], dict[str, Any]]:
    """The four payload fields the realizer needs, narrowed once and checked."""
    p = item.payload
    entry, params, binds = p.get("entry_point"), p.get("parameters"), p.get("bindings")
    if not isinstance(entry, str) or not isinstance(params, list) or not isinstance(binds, dict):
        raise CompositionError(f"{item.id}: payload is not an evalplus item")
    source = str(p["prompt"]) + str(p["contract"]) + str(p["canonical_solution"])
    return source, entry, [str(x) for x in params], dict(binds)


def _merged_source(components: Sequence[Item], links: Sequence[Any]) -> str:
    """One module inlining every component under a position-prefixed name.

    This is what makes the gold-agreement check (EMIT-ALL-0006) mean something here. The
    chained route evaluates each component's own callable in turn; this route builds a
    single program whose text no component wrote and runs that. Agreement between the two
    is then evidence rather than a tautology, which is exactly the case the default
    prompt realizer cannot offer.
    """
    parts = ["# merged composite: each component inlined under a c<pos>_ prefix"]
    for pos, item in enumerate(components):
        body, entry, _params, _binds = _payload(item)
        parts.append(f"\n# --- component {pos}: {item.id} ---")
        # exec the component in its own namespace, then bind the entry point to a
        # prefixed name. Renaming by text substitution would rewrite string literals.
        parts.append(f"_ns{pos} = {{}}")
        parts.append(f"exec({body!r}, _ns{pos})")
        parts.append(f"c{pos}_{entry} = _ns{pos}[{entry!r}]")

    parts.append("\n# --- wiring ---")
    incoming = {int(link.downstream): link for link in links}
    for pos, item in enumerate(components):
        _body, entry, params, args = _payload(item)
        call = []
        for name in params:
            link = incoming.get(pos)
            if link is not None and str(link.slot) == str(name):
                # the upstream RESULT, never its value: a literal here would be the
                # literal-suppression bug EMIT-ALL-0001 exists to refuse
                call.append(f"c{int(link.upstream)}_value")
            else:
                call.append(repr(args[str(name)]))
        parts.append(f"c{pos}_value = c{pos}_{entry}({', '.join(call)})")
    return "\n".join(parts) + "\n"


def make_realizer(*, language: str = "python") -> object:
    """Build a realizer that presents the composite as a CODE-SYNTHESIS task.

    The framing is load-bearing and is chosen rather than defaulted. Each component is
    shown as its own signature and docstring verbatim, followed by a clause naming which
    upstream result feeds which downstream parameter. The upstream *value* appears nowhere,
    so literal suppression holds by construction rather than by a check.

    The alternative framing, "predict the output", would make the released EvalPlus samples
    an archive for a different task and kill the product-bound arm. That is the whole
    reason this is a decision and not a detail.
    """

    def realizer(components: Sequence[Item], links: Sequence[Any]) -> Realization:
        incoming = {int(link.downstream): link for link in links}
        gold: list[tuple[str, Scalar]] = []
        bindings: dict[str, Scalar] = {}
        suppressed: list[str] = []
        parts: list[str] = []

        values: list[Scalar] = []
        for pos, item in enumerate(components):
            _src, _entry, _params, own = _payload(item)
            override: dict[str, Scalar] = {}
            link = incoming.get(pos)
            if link is not None:
                slot = str(link.slot)
                override[slot] = values[int(link.upstream)]
                suppressed.append(qualified(pos, slot))
            else:
                for k, v in own.items():
                    bindings[qualified(pos, str(k))] = v
            out = oracle(item, override)
            values.append(out[RESULT])
            gold.append((qualified(pos, RESULT), out[RESULT]))

            head = str(item.payload["prompt"]).rstrip()
            wiring = ""
            if link is not None:
                wiring = (
                    f"\n# The `{link.slot}` argument of this function is the "
                    f"value returned by Part {int(link.upstream) + 1}."
                )
            parts.append(f"# Part {pos + 1}.\n{head}{wiring}")

        text = (
            "\n\n".join(parts)
            + "\n\n# Implement every part. Each part's remaining arguments take the values "
            "shown in its own docstring examples.\n"
        )
        return Realization(
            gold=tuple(gold),
            rendering={language: text, "merged": _merged_source(components, links)},
            bindings=bindings,
            suppressed=tuple(suppressed),
            # NOT "chained": the merged rendering reaches the gold by its own route, so the
            # agreement check has force here and no vacuity diagnostic is emitted.
            meta={"realizer": "evalplus-code-synthesis", "gold_route": "merged"},
        )

    return realizer
