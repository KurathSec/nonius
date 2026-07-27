"""The default, benchmark-agnostic realizer (ARCHITECTURE.md section 6.3).

Works for any manifest whose items carry a slotted prompt template. Each component is
presented as a numbered part; an unlinked slot is filled with its own value, and a linked
slot is replaced by a *reference* to the upstream part's result rather than by that
result's value. That is what makes the chain bind: nothing in the text states the
upstream answer, so a system has to compute it.

**What this realizer cannot give you.** It computes the composite's gold by chaining the
component oracles -- which is the same computation the EMIT-ALL-0002 agreement check uses
as its reference. So for this realizer that check is vacuous, and it says so: the
realization is tagged ``gold_route="chained"`` and nonius emits an info diagnostic rather
than letting a tautology read as evidence. The check has force only for a realizer that
reaches the gold by an independent route -- as the Spaghetti Architect adapter does, by
merging the components into one program and running that program's own oracle.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from nonius.errors import CompositionError
from nonius.model import Item, Link, Realization, Scalar, qualified
from nonius.oracle import Oracle, evaluate
from nonius.spec.registry import require

_R_SUPPRESS = require("EMIT-ALL-0001")

PROMPT_KEY = "prompt"
BINDINGS_KEY = "bindings"


def _base_bindings(item: Item) -> dict[str, Scalar]:
    """The item's own value for each slot.

    Taken from ``payload.bindings`` when the manifest supplies one, and otherwise from
    top-level payload keys matching slot names -- which is the shape a benchmark whose
    payload already *is* its input record naturally has. Bindings are overrides on these,
    never a replacement for them.
    """
    raw = item.payload.get(BINDINGS_KEY)
    if raw is not None:
        if not isinstance(raw, dict):
            raise CompositionError(f"{item.id}: payload.{BINDINGS_KEY} must be an object")
        return {str(k): v for k, v in raw.items()}
    return {
        s.name: item.payload[s.name]  # type: ignore[misc]
        for s in item.slots
        if s.name in item.payload
    }


def _template(item: Item) -> str:
    raw = item.payload.get(PROMPT_KEY)
    if not isinstance(raw, str):
        raise CompositionError(
            f"{item.id}: the default realizer needs payload.{PROMPT_KEY} to be a string; "
            f"supply an adapter realizer for items shaped otherwise"
        )
    return raw


def _fill(template: str, values: Mapping[str, str]) -> str:
    out = template
    for name, text in values.items():
        out = out.replace("{" + name + "}", text)
    return out


def make_prompt_realizer(oracle: Oracle) -> object:
    """Build a :class:`~nonius.oracle.Realizer` over slotted prompt templates."""

    def realizer(components: Sequence[Item], links: Sequence[Link]) -> Realization:
        incoming: dict[int, list[Link]] = {}
        for link in links:
            incoming.setdefault(link.downstream, []).append(link)

        gold: list[tuple[str, Scalar]] = []
        per_position: list[Mapping[str, Scalar]] = []
        bindings: dict[str, Scalar] = {}
        suppressed: list[str] = []
        parts: list[str] = []

        for pos, item in enumerate(components):
            base = _base_bindings(item)
            overrides: dict[str, Scalar] = {}
            shown: dict[str, str] = {}

            for slot in item.slots:
                fed = next(
                    (x for x in incoming.get(pos, ()) if x.slot == slot.name), None
                )
                if fed is None:
                    if slot.name in base:
                        bindings[qualified(pos, slot.name)] = base[slot.name]
                        shown[slot.name] = repr(base[slot.name])
                else:
                    # The value is never rendered -- only a reference to where it comes
                    # from. This is literal suppression (EMIT-ALL-0001).
                    suppressed.append(qualified(pos, slot.name))
                    overrides[slot.name] = per_position[fed.upstream][fed.result]
                    shown[slot.name] = (
                        f"<the value of `{fed.result}` computed in Part {fed.upstream + 1}>"
                    )

            results = evaluate(oracle, item, overrides)
            per_position.append(results)
            for name, value in results.items():
                gold.append((qualified(pos, name), value))

            rendered = _fill(_template(item), shown)
            missing = [s.name for s in item.slots if "{" + s.name + "}" in rendered]
            if missing:
                raise CompositionError(
                    f"{item.id}: slots {missing} have no value and no incoming link, so "
                    f"their placeholders would ship unfilled; give the item a binding for "
                    f"them in payload, or drop them from the manifest"
                )
            parts.append(f"Part {pos + 1}.\n{rendered}")

        wanted = ", ".join(f'"{k}"' for k, _ in gold)
        text = (
            "\n\n".join(parts)
            + "\n\nRespond with ONLY a JSON object whose keys are exactly "
            + f"[{wanted}] and whose values are the computed results."
        )

        return Realization(
            gold=tuple(gold),
            rendering={"text": text},
            bindings=bindings,
            suppressed=tuple(suppressed),
            meta={"realizer": "prompt", "gold_route": "chained"},
        )

    return realizer
