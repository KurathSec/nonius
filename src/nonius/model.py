"""The benchmark-agnostic data model (ARCHITECTURE.md section 3).

Nothing here knows what a program is. An item is a thing with typed named input slots,
typed named results, and an oracle that maps the former to the latter. That is the whole
precondition, and it is the instrument's main limit on reach: a benchmark whose gold is a
stored constant with no callable behind it cannot be composed, because there is nothing
to re-run under a changed binding.

All public types are frozen and slotted, and every collection field is a tuple, so a
composite is hashable and its content hash is stable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

Scalar = str | int | float | bool | None

TypeTag = Literal["bool", "int", "float", "str", "null"]

#: Tags a link may carry (LINK-ALL-0001). ``float`` is excluded because exact equality on
#: floats is not a defensible link relation and a declared tolerance would make the
#: composite's gold approximate, which defeats the by-construction claim. ``null`` is
#: excluded because a null result carries no information to propagate. Both are declared
#: limitations, not oversights -- see docs/honesty.md.
COMPOSABLE_TAGS: frozenset[str] = frozenset({"bool", "int", "str"})


def tag_of(value: Scalar) -> TypeTag:
    """The type tag of a scalar (CORE-ALL-0001).

    ``bool`` is tested before ``int`` because ``bool`` is a subclass of ``int`` in
    Python, and a boolean answer that reported itself as an integer would silently
    become type-compatible with numeric slots.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    raise TypeError(f"not a scalar: {type(value).__name__}")


def _check_tags(values: tuple[Scalar, ...] | None, tag: TypeTag, where: str) -> None:
    """Every declared value must actually carry the declared tag (CORE-ALL-0001).

    Without this the tag is a label rather than a fact, and a declared codomain of
    booleans on an ``int`` result would make every numeric slot look type-compatible --
    the precise confusion CORE-ALL-0001 exists to prevent, arriving through the manifest
    instead of through the tag function.
    """
    for value in values or ():
        actual = tag_of(value)
        if actual != tag:
            raise ValueError(
                f"{where}: {value!r} is {actual}, but the declared tag is {tag}"
            )


@dataclass(frozen=True, slots=True)
class Slot:
    """A named, typed input slot of an item: somewhere an upstream answer can go."""

    name: str
    tag: TypeTag
    #: Values the slot is known to treat specially (a lookup table's keys, a
    #: collection's members). Informational for the audit's explanation of *why* a slot
    #: is dead. Liveness is measured by running the oracle, never taken from this field.
    accepts: tuple[Scalar, ...] | None = None
    #: Opaque, adapter-supplied label for whatever consumes this slot. Reported by the
    #: audit so a practitioner can see which construct kills their links.
    consumer: str = ""

    def __post_init__(self) -> None:
        _check_tags(self.accepts, self.tag, f"slot {self.name!r} accepts")


@dataclass(frozen=True, slots=True)
class ResultVar:
    """A named, typed result of an item: somewhere an answer comes from."""

    name: str
    tag: TypeTag
    #: The exact set of values this result can take, when the item declares one.
    #: ``None`` means unbounded, and liveness probing falls back to the declared probe
    #: set (LINK-ALL-0003).
    codomain: tuple[Scalar, ...] | None = None

    def __post_init__(self) -> None:
        _check_tags(self.codomain, self.tag, f"result {self.name!r} codomain")


@dataclass(frozen=True, slots=True)
class Item:
    """One benchmark item, as the composer sees it."""

    id: str
    slots: tuple[Slot, ...] = ()
    results: tuple[ResultVar, ...] = ()
    #: Difficulty/stratification label. Purely descriptive; the composer never uses it to
    #: decide correctness, only to stratify and to report.
    family: str = ""
    #: Adapter-private data (a program IR, a template, a file path). The core never looks
    #: inside it.
    payload: Mapping[str, object] = field(default_factory=dict)

    def slot(self, name: str) -> Slot:
        for s in self.slots:
            if s.name == name:
                return s
        raise KeyError(f"{self.id}: no slot {name!r}")

    def result(self, name: str) -> ResultVar:
        for r in self.results:
            if r.name == name:
                return r
        raise KeyError(f"{self.id}: no result {name!r}")


@dataclass(frozen=True, slots=True)
class Candidate:
    """A possible substitution between two *items*, as the link analysis reports it.

    Item-level, so it is a property of the corpus rather than of any one composite. A
    chain turns candidates into :class:`Link` s by binding them to component positions.
    """

    upstream_item: str
    result: str
    downstream_item: str
    slot: str
    tag: TypeTag


@dataclass(frozen=True, slots=True)
class Link:
    """One substitution inside a chain: an upstream result becomes a downstream slot.

    ``upstream`` and ``downstream`` are component *positions* within the chain, not item
    ids, because a chain may legitimately use the same item more than once and item ids
    would then be ambiguous.

    The link is symbolic. Realizing it must never print the upstream value into the
    downstream's presentation (EMIT-ALL-0001) -- if it did, a system could read the
    answer instead of computing it, and the chain would not bind.
    """

    upstream: int
    result: str
    downstream: int
    slot: str
    tag: TypeTag


@dataclass(frozen=True, slots=True)
class Chain:
    """Components plus the links between them, before realization.

    ``components`` holds item ids in topological order (LINK-ALL-0005); a link's
    endpoints index into it. The shape is a DAG, not only a path: fan-in -- several
    upstream components feeding distinct slots of one downstream component -- is a legal
    chain and is how component count grows on a corpus whose link graph is shallow
    (DEPTH-ALL-0002).
    """

    components: tuple[str, ...]
    links: tuple[Link, ...]

    @property
    def depth(self) -> int:
        """Depth is the number of components (DEPTH-ALL-0001), not the link count.

        The two coincide on a simple path and nowhere else. Fan-in gives depth-1 links
        into one sink; fan-out lets one component feed several slots, so a chain can carry
        more links than ``depth - 1``. Only the component count is what the product bound
        is taken over, which is why it is the one called depth.
        """
        return len(self.components)

    @property
    def path_depth(self) -> int:
        """Longest path in links, in components. Reported next to ``depth``, never as it."""
        best = {i: 1 for i in range(len(self.components))}
        for link in sorted(self.links, key=lambda x: (x.downstream, x.upstream)):
            best[link.downstream] = max(best[link.downstream], best[link.upstream] + 1)
        return max(best.values()) if best else 0


@dataclass(frozen=True, slots=True)
class Realization:
    """What a realizer produces: the composite's gold and its presentable form."""

    #: The composed gold, as an ordered mapping from qualified result name to value.
    gold: tuple[tuple[str, Scalar], ...]
    #: Presentation keyed by whatever dimension the adapter varies (language, format).
    rendering: Mapping[str, str]
    #: Every literal binding the presentation states, keyed by qualified slot name. This
    #: is how literal suppression is checked exactly rather than by grepping the text: a
    #: linked slot that still appears here has leaked its upstream's answer, and the
    #: realizer is the only party that can report this truthfully because it produced it.
    bindings: Mapping[str, Scalar] = field(default_factory=dict)
    #: Qualified slot names the realizer removed because a link feeds them.
    suppressed: tuple[str, ...] = ()
    #: Adapter-private extras carried through to the emitted record.
    meta: Mapping[str, object] = field(default_factory=dict)

    def gold_map(self) -> dict[str, Scalar]:
        return dict(self.gold)


@dataclass(frozen=True, slots=True)
class Composite:
    """An emitted composite item: a chain, its realization, and its identity."""

    id: str
    chain: Chain
    realization: Realization
    #: Per-component stratum labels, taken from the archive when one was supplied.
    strata: tuple[str, ...] = ()
    rulings_version: str = ""

    @property
    def depth(self) -> int:
        return self.chain.depth


Severity = Literal["info", "warning", "error"]

#: Closed set. A code outside it is a bug, not a new diagnostic.
DIAGNOSTIC_CODES: frozenset[str] = frozenset(
    {
        "slot-tag-not-composable",
        "result-tag-not-composable",
        "no-type-compatible-link",
        "link-dead",
        "oracle-raised",
        "codomain-unbounded",
        "component-reuse-above-ceiling",
        "literal-leak",
        "gold-disagreement",
        "gold-route-chained",
        "unfilled-slot",
    }
)


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A data-carrying finding. nonius has no logger; diagnostics are a typed output."""

    severity: Severity
    code: str
    message: str
    subject: str = ""
    ruling: str = ""

    def __post_init__(self) -> None:
        if self.code not in DIAGNOSTIC_CODES:
            raise ValueError(f"unknown diagnostic code: {self.code!r}")


def qualified(component_index: int, name: str) -> str:
    """The name a component's result carries in a composite's gold (EMIT-ALL-0003).

    Components are prefixed by position, not by item id, so two uses of the same item in
    one composite stay distinguishable and the gold's key set is a function of the
    chain's shape rather than of the corpus's naming.
    """
    return f"c{component_index}_{name}"


def topological_positions(n: int, links: Sequence[Link]) -> tuple[int, ...]:
    """Order ``n`` component positions so every link points forward (LINK-ALL-0005).

    Raises ``ValueError`` on a cycle. Deterministic: ties break on the given position
    order, never on set iteration.
    """
    incoming: dict[int, set[int]] = {i: set() for i in range(n)}
    for link in links:
        if link.upstream not in incoming or link.downstream not in incoming:
            raise ValueError(f"link references a component outside the chain: {link}")
        if link.upstream == link.downstream:
            raise ValueError(f"self-link on component {link.upstream}")
        incoming[link.downstream].add(link.upstream)

    order: list[int] = []
    placed: set[int] = set()
    remaining = list(range(n))
    while remaining:
        ready = [c for c in remaining if not (incoming[c] - placed)]
        if not ready:
            raise ValueError("cycle in chain links")
        nxt = ready[0]
        order.append(nxt)
        placed.add(nxt)
        remaining.remove(nxt)
    return tuple(order)
