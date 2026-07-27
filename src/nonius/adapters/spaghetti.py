"""The Spaghetti Architect reference adapter (ARCHITECTURE.md section 12).

**This module is the only place in nonius that may import Spaghetti Architect, and it
never writes to it.** Every path it touches is opened read-only. The layering test
(tests/test_layering.py) enforces the first half of that sentence mechanically; the second
is a rule this module keeps by never opening a file for writing.

Spaghetti Architect is a separate project with its own DOI and its own paper. nonius uses
its generator, IR, execution oracle and committed archive **as instruments**, and claims
none of them. See NOTICE for the boundary in both directions.

What this adapter provides, and why each one is interesting:

``items``      one :class:`~nonius.model.Item` per committed program, with slots and
               result codomains derived from the IR's four operation types.
``oracle``     the benchmark's own execution oracle, re-run under a changed input binding.
``realizer``   a **native** realizer: it merges the components into one program and takes
               the gold from that merged program's own oracle. That is an independent
               route to the answer, so the EMIT-ALL-0002 agreement check has real force
               here -- unlike the default prompt realizer, where it is vacuous.
``archive``    the committed four-model, k=8, temperature-0 ladder, re-graded offline.

The merged program is built as an ``IRProgram`` directly rather than through the
project's ``parse()``, because that parser requires every operation operand to be an
*input* and a composite's whole point is that one operand is another operation's result.
Nothing is patched to allow this: nonius constructs the dataclass, then re-establishes the
invariants ``parse()`` would have checked that still apply, and finally verifies the
result by running it.
"""

from __future__ import annotations

import copy
import dataclasses
import functools
import glob
import gzip
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from nonius.archive import Archive, Verdict
from nonius.errors import CompositionError, ManifestError, OracleError
from nonius.model import Item, Link, Realization, ResultVar, Scalar, Slot, TypeTag, qualified

ENV_HOME = "NONIUS_SPAGHETTI_HOME"

PROFILES = ("minimal", "standard", "max")
LANGUAGES = ("python", "javascript", "go", "java", "cpp")


def home(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Locate the Spaghetti Architect checkout, without importing anything."""
    raw = explicit or os.environ.get(ENV_HOME)
    if not raw:
        raise ManifestError(
            f"set {ENV_HOME} to a Spaghetti Architect checkout, or pass home=..."
        )
    path = Path(raw).expanduser().resolve()
    if not (path / "src" / "ir_models.py").is_file():
        raise ManifestError(f"{path} does not look like a Spaghetti Architect checkout")
    return path


@functools.lru_cache(maxsize=4)
def _sa(root: str) -> Any:
    """Import the project's modules from a checkout, once."""
    if root not in sys.path:
        sys.path.insert(0, root)
    from src.generators import REGISTRY  # noqa: TID253
    from src.ir_models import IRProgram, scalar_tag  # noqa: TID253
    from src.nodes.parser import parse  # noqa: TID253
    from src.nodes.planner import Planner  # noqa: TID253
    from src.nodes.validator import oracle as sa_oracle  # noqa: TID253

    return {
        "IRProgram": IRProgram,
        "scalar_tag": scalar_tag,
        "parse": parse,
        "Planner": Planner,
        "REGISTRY": REGISTRY,
        "oracle": sa_oracle,
        "db": str(Path(root) / "config" / "anti_patterns_db.json"),
    }


# --------------------------------------------------------------------------- #
# items
# --------------------------------------------------------------------------- #
def _elem_tag(sa: Any, values: list[Any]) -> TypeTag:
    tag: TypeTag = sa["scalar_tag"](values[0]) if values else "int"
    return tag


def _describe(sa: Any, raw_ir: Mapping[str, Any]) -> tuple[tuple[Slot, ...], tuple[ResultVar, ...]]:
    """Derive slots and result codomains from the IR's four operation types.

    The codomains are exact, not estimated: a lookup can only return one of its own table
    values or its default; a conditional can only return one of its two branch values; a
    membership check can only return true or false. Only an aggregate is unbounded, and
    that is the one case that falls back to the versioned probe set (LINK-ALL-0003).
    """
    inputs = dict(raw_ir.get("inputs", {}))
    slots: dict[str, Slot] = {}
    results: list[ResultVar] = []

    for op in raw_ir.get("operations", []):
        kind = op.get("operation")
        if kind == "MEMBERSHIP_CHECK":
            col = inputs.get(op["collection_name"], [])
            slots.setdefault(
                op["target_var"],
                Slot(
                    op["target_var"],
                    _elem_tag(sa, col),
                    accepts=tuple(col),
                    consumer="MEMBERSHIP_CHECK.target_var",
                ),
            )
            results.append(ResultVar(op["result_var"], "bool", codomain=(False, True)))
        elif kind == "KEY_VALUE_LOOKUP":
            pairs = dict(op.get("pairs", {}))
            slots.setdefault(
                op["key_var"],
                Slot(
                    op["key_var"],
                    "str",
                    accepts=tuple(sorted(pairs)),
                    consumer="KEY_VALUE_LOOKUP.key_var",
                ),
            )
            values = sorted(
                {*pairs.values(), op["default_value"]}, key=lambda v: (str(type(v)), str(v))
            )
            results.append(
                ResultVar(
                    op["result_var"],
                    sa["scalar_tag"](op["default_value"]),
                    codomain=tuple(values),
                )
            )
        elif kind == "AGGREGATE":
            # No scalar slot: an aggregate reads a collection, and a scalar result cannot
            # stand in for a list. Its own result is an unbounded int.
            results.append(ResultVar(op["result_var"], "int", codomain=None))
        elif kind == "CONDITIONAL_SELECT":
            slots.setdefault(
                op["subject_var"],
                Slot(op["subject_var"], "int", consumer="CONDITIONAL_SELECT.subject_var"),
            )
            branches = sorted(
                {op["then_value"], op["else_value"]}, key=lambda v: (str(type(v)), str(v))
            )
            results.append(
                ResultVar(
                    op["result_var"],
                    sa["scalar_tag"](op["then_value"]),
                    codomain=tuple(branches),
                )
            )
        else:
            raise ManifestError(f"unknown operation in IR: {kind!r}")

    # A slot must be an actual input to be substitutable; an operand that is itself a
    # result of an earlier operation is already bound and is not a free slot.
    return tuple(s for name, s in sorted(slots.items()) if name in inputs), tuple(results)


def items(home_path: str | os.PathLike[str] | None = None) -> tuple[Item, ...]:
    """One item per committed program in the public dev split.

    Reads ``bench/data/dev/<stem>.json``, which carries the frozen IR. Nothing is minted
    and nothing is rendered here.
    """
    root = home(home_path)
    sa = _sa(str(root))
    out: list[Item] = []
    for path in sorted(glob.glob(str(root / "bench" / "data" / "dev" / "*.json"))):
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        slots, results = _describe(sa, rec["ir"])
        out.append(
            Item(
                id=str(rec["stem"]),
                slots=slots,
                results=results,
                family=str(rec.get("family", "")),
                payload={"ir": rec["ir"], "home": str(root)},
            )
        )
    if not out:
        raise ManifestError(f"no committed programs under {root}/bench/data/dev/")
    return tuple(out)


# --------------------------------------------------------------------------- #
# oracle
# --------------------------------------------------------------------------- #
def oracle(item: Item, bindings: Mapping[str, Scalar]) -> dict[str, Scalar]:
    """The project's own execution oracle, re-run under a changed input binding."""
    raw = item.payload.get("ir")
    root = item.payload.get("home")
    if not isinstance(raw, dict) or not isinstance(root, str):
        raise OracleError(f"{item.id}: payload lacks an 'ir' and a 'home'")
    sa = _sa(root)

    ir = copy.deepcopy(raw)
    for name, value in bindings.items():
        if name not in ir.get("inputs", {}):
            raise OracleError(f"{item.id}: {name!r} is not an input of this program")
        ir["inputs"][name] = value
    try:
        return dict(sa["oracle"](sa["parse"](ir)))
    except Exception as exc:  # noqa: BLE001 - a rejected binding is a dead probe
        raise OracleError(f"{item.id}: {exc!r}") from exc


# --------------------------------------------------------------------------- #
# the native realizer: merge into one program
# --------------------------------------------------------------------------- #
_OPERAND_FIELDS = ("collection_name", "target_var", "map_name", "key_var", "subject_var")


def _rename(sa: Any, program: Any, prefix: str) -> tuple[Any, dict[str, str]]:
    mapping = {name: prefix + name for name in program.inputs}
    for op in program.operations:
        mapping[op.result_var] = prefix + op.result_var

    ops = []
    for op in program.operations:
        fields = {f.name: getattr(op, f.name) for f in dataclasses.fields(op)}
        for key in (*_OPERAND_FIELDS, "result_var"):
            if key in fields:
                fields[key] = mapping[fields[key]]
        ops.append(type(op)(**{k: v for k, v in fields.items() if k != "op"}))

    renamed = sa["IRProgram"](
        program.version,
        program.module_name,
        {mapping[k]: v for k, v in program.inputs.items()},
        ops,
    )
    return renamed, mapping


def _merge(sa: Any, programs: Sequence[Any], links: Sequence[Link]) -> tuple[Any, tuple[str, ...]]:
    """Build the composite program. Returns it and the slots that were suppressed."""
    renamed: list[Any] = []
    maps: list[dict[str, str]] = []
    for pos, program in enumerate(programs):
        r, m = _rename(sa, program, f"c{pos}_")
        renamed.append(r)
        maps.append(m)

    inputs: dict[str, object] = {}
    for r in renamed:
        inputs.update(r.inputs)
    ops: list[Any] = []
    for r in renamed:
        ops.extend(r.operations)

    suppressed: list[str] = []
    for link in links:
        upstream = maps[link.upstream][link.result]
        target = maps[link.downstream][link.slot]
        suppressed.append(target)

        rewritten = []
        for op in ops:
            fields = {f.name: getattr(op, f.name) for f in dataclasses.fields(op)}
            touched = False
            # Only scalar operands can take a scalar result. A collection operand names a
            # list input and is never a substitution target.
            for key in ("target_var", "key_var", "subject_var"):
                if fields.get(key) == target:
                    fields[key] = upstream
                    touched = True
            rewritten.append(
                type(op)(**{k: v for k, v in fields.items() if k != "op"}) if touched else op
            )
        ops = rewritten
        # Dropping the slot from inputs is literal suppression (EMIT-ALL-0001): the value
        # is not declared anywhere, so it cannot be read out of the rendered source.
        inputs.pop(target, None)

    merged = sa["IRProgram"]("1.0", "composite", inputs, ops)
    _check_merged(merged, inputs)
    return merged, tuple(suppressed)


def _check_merged(merged: Any, inputs: Mapping[str, object]) -> None:
    """Re-establish the parser invariants that still apply to a merged program.

    ``parse()`` cannot be used on a composite (it requires every operand to be an input),
    so the checks it would have run are restated here for everything except that one rule.
    """
    declared = set(inputs)
    for i, op in enumerate(merged.operations):
        if op.result_var in declared:
            raise CompositionError(f"merged[{i}]: result_var {op.result_var!r} collides")
        for key in ("collection_name", "map_name"):
            name = getattr(op, key, None)
            if name is not None and name not in inputs:
                raise CompositionError(
                    f"merged[{i}]: {key} {name!r} must still point at an input; a "
                    f"collection operand is never a substitution target"
                )
        for key in ("target_var", "key_var", "subject_var"):
            name = getattr(op, key, None)
            if name is not None and name not in declared:
                raise CompositionError(
                    f"merged[{i}]: operand {name!r} is neither an input nor an earlier result"
                )
        declared.add(op.result_var)


def make_realizer(
    home_path: str | os.PathLike[str] | None = None,
    *,
    profile: str = "max",
    languages: Sequence[str] = LANGUAGES,
    annotate: bool = True,
) -> Any:
    """A native realizer that merges components into one program.

    The gold comes from the merged program's own execution oracle, which is an
    independent route to the answer -- so the agreement check against the chained
    component oracles (EMIT-ALL-0002) is a real test here rather than a tautology.
    """
    root = home(home_path)
    sa = _sa(str(root))
    if profile not in PROFILES:
        raise ValueError(f"profile must be one of {PROFILES}, got {profile!r}")

    def realizer(components: Sequence[Item], links: Sequence[Link]) -> Realization:
        programs = [sa["parse"](copy.deepcopy(c.payload["ir"])) for c in components]
        merged, suppressed = _merge(sa, programs, links)

        gold_raw = dict(sa["oracle"](merged))
        # The merge prefixes every identifier with its component position, so the merged
        # program's own result names already are the composite's qualified names.
        gold = tuple((k, gold_raw[k]) for k in gold_raw)

        plan = sa["Planner"](sa["db"], profile).plan(merged)
        rendering = {
            lang: sa["REGISTRY"][lang].generate(merged, plan, annotate=annotate)
            for lang in languages
        }

        bindings: dict[str, Scalar] = {}
        for pos, component in enumerate(components):
            for slot in component.slots:
                name = qualified(pos, slot.name)
                if name in merged.inputs:
                    bindings[name] = merged.inputs[name]

        return Realization(
            gold=gold,
            rendering=rendering,
            bindings=bindings,
            suppressed=suppressed,
            meta={
                "realizer": "spaghetti-merge",
                "gold_route": "independent",
                "profile": profile,
                "result_vars": [k for k, _ in gold],
                "module_name": merged.module_name,
            },
        )

    return realizer


# --------------------------------------------------------------------------- #
# archive
# --------------------------------------------------------------------------- #
def archive(
    home_path: str | os.PathLike[str] | None = None,
    *,
    profile: str | None = None,
    language: str | None = None,
) -> Archive:
    """The committed four-model ladder, re-graded offline with zero API calls.

    Items are keyed by program stem. The ladder varies two further dimensions -- three
    messiness profiles and five target languages -- and by default all fifteen cells are
    pooled, giving 120 draws per (system, program). Pooling is a choice: it treats a
    rendering cell as a replicate, which is defensible because composition happens at the
    program level, but it does average over cells whose difficulty differs. Pass
    ``profile`` and ``language`` to restrict to one cell instead.
    """
    root = home(home_path)
    sa = _sa(str(root))

    programs: dict[str, Any] = {}
    for path in sorted(glob.glob(str(root / "bench" / "data" / "dev" / "*.json"))):
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        programs[str(rec["stem"])] = sa["parse"](rec["ir"])

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from bench.grade import _match, extract_json_obj  # noqa: TID253

    golds = {stem: sa["oracle"](program) for stem, program in programs.items()}

    verdicts: list[Verdict] = []
    draws: dict[tuple[str, str], int] = {}
    pattern = str(root / "bench" / "out" / "ladder" / "comprehend__*.jsonl.gz")
    for path in sorted(glob.glob(pattern)):
        system = Path(path).name[len("comprehend__") : -len(".jsonl.gz")]
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                if profile and rec["profile"] != profile:
                    continue
                if language and rec["language"] != language:
                    continue
                variant = rec.get("variant", "base")
                stem = rec["sample"] if variant == "base" else f"{rec['sample']}_{variant}"
                expected = golds[stem]
                for out in rec["raw_outputs"]:
                    key = (system, stem)
                    draw = draws.get(key, 0)
                    draws[key] = draw + 1
                    verdicts.append(
                        Verdict(
                            system=system,
                            item=stem,
                            draw=draw,
                            correct=1 if _match(extract_json_obj(out), expected) else 0,
                        )
                    )
    if not verdicts:
        raise ManifestError(f"no ladder records matched under {root}/bench/out/ladder/")
    return Archive(tuple(verdicts))
