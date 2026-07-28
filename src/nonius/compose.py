"""The composition operator (ARCHITECTURE.md section 6).

Three stages, in order, and each is refusable:

1. **Analysis** -- enumerate every type-compatible substitution between items
   (LINK-ALL-0001), then decide which of them are *live*: a link is admissible only if
   the downstream's answer actually varies as the substituted slot ranges over the
   upstream result's codomain (LINK-ALL-0007). This is the stage that does the work. On a
   real corpus most type-compatible links are dead, and a composer that skips this stage
   emits conjunctions of items while calling them chains.

2. **Construction** -- assemble chains and fan-ins from live links, acyclic and in
   topological order (LINK-ALL-0004, LINK-ALL-0005).

3. **Realization** -- hand the chain to the benchmark's realizer, then check by
   construction what came back: the gold must agree with the independently chained
   component oracles (EMIT-ALL-0006), and no linked slot may survive as a literal
   binding (EMIT-ALL-0001).

No stage contacts a model or a network (EMIT-ALL-0004).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from nonius.canonical import canonical_json, content_hash
from nonius.errors import CompositionError, GoldDisagreementError, LinkError, LiteralLeakError
from nonius.model import (
    COMPOSABLE_TAGS,
    Candidate,
    Chain,
    Composite,
    Diagnostic,
    Item,
    Link,
    Realization,
    Scalar,
    qualified,
    topological_positions,
)
from nonius.oracle import Oracle, Realizer, evaluate
from nonius.spec.registry import require, spec_version

_R_TYPE = require("LINK-ALL-0001")
_R_LIVE = require("LINK-ALL-0007")
_R_PROBE = require("LINK-ALL-0003")
_R_SLOT_ONCE = require("LINK-ALL-0004")
_R_ACYCLIC = require("LINK-ALL-0005")
_R_SUPPRESS = require("EMIT-ALL-0001")
_R_AGREE = require("EMIT-ALL-0006")
_R_HASH = require("EMIT-ALL-0005")

#: The versioned probe set for an unbounded int codomain (LINK-ALL-0003). Changing it is
#: a spec-major change: it can move a link from dead to live and therefore change which
#: composites exist at all.
PROBE_INT: tuple[int, ...] = (0, 1, 2, 5, 10, 50, 100, 1000, 10000, 60000, -1)
PROBE_BOOL: tuple[bool, ...] = (False, True)
#: str has no meaningful unbounded probe set -- an arbitrary string tells you only that a
#: lookup misses, which every arbitrary string does. A str result with no declared
#: codomain is reported ``codomain-unbounded`` and carries no live link.
PROBE_STR: tuple[str, ...] = ()


def codomain_values(item: Item, result: str, *, cap: int = 64) -> tuple[Scalar, ...]:
    """The values a result can take, for liveness probing (LINK-ALL-0007/LINK-ALL-0003)."""
    rv = item.result(result)
    if rv.codomain is not None:
        return tuple(rv.codomain[:cap])
    if rv.tag == "int":
        return PROBE_INT[:cap]
    if rv.tag == "bool":
        return PROBE_BOOL[:cap]
    return PROBE_STR[:cap]


@dataclass(frozen=True, slots=True)
class LinkVerdict:
    """Why a candidate substitution is, or is not, admissible."""

    candidate: Candidate
    live: bool
    distinct_outcomes: int
    probed: int
    reason: str


@dataclass(frozen=True, slots=True)
class LinkAnalysis:
    """The corpus's link structure: what could be substituted, and what actually binds."""

    verdicts: tuple[LinkVerdict, ...]
    diagnostics: tuple[Diagnostic, ...] = ()
    #: Bounds applied to this analysis, reported rather than silently applied
    #: (AUDIT-ALL-0004).
    caps: Mapping[str, object] = field(default_factory=dict)

    @property
    def candidates(self) -> tuple[Candidate, ...]:
        return tuple(v.candidate for v in self.verdicts)

    @property
    def live(self) -> tuple[Candidate, ...]:
        return tuple(v.candidate for v in self.verdicts if v.live)

    @property
    def dead(self) -> tuple[Candidate, ...]:
        return tuple(v.candidate for v in self.verdicts if not v.live)

    def live_pairs(self) -> frozenset[tuple[str, str]]:
        """Ordered ``(upstream_item, downstream_item)`` pairs carrying at least one live link."""
        return frozenset((c.upstream_item, c.downstream_item) for c in self.live)

    def adjacency(self) -> dict[str, tuple[str, ...]]:
        """Live-link adjacency, item id -> downstream item ids, deterministically ordered."""
        out: dict[str, set[str]] = {}
        for c in self.live:
            out.setdefault(c.upstream_item, set()).add(c.downstream_item)
        return {k: tuple(sorted(v)) for k, v in sorted(out.items())}

    def live_for(self, upstream: str, downstream: str) -> tuple[Candidate, ...]:
        return tuple(
            c for c in self.live if c.upstream_item == upstream and c.downstream_item == downstream
        )


_PROBE_ERROR = "\x00error"


def _probe_outcome(
    oracle: Oracle,
    item: Item,
    slot: str,
    value: Scalar,
    cache: dict[tuple[str, str, str], tuple[str, str]],
) -> tuple[str, str]:
    """The downstream answer for one probed value, and why the probe failed if it did.

    Returns ``(outcome, error)``. A refusing oracle is a dead probe, not a crash -- but it
    is also not evidence that the downstream ignores its input, so the reason is carried
    out rather than flattened into the outcome.
    """
    key = (item.id, slot, canonical_json(value))
    hit = cache.get(key)
    if hit is not None:
        return hit
    try:
        out = (canonical_json(dict(evaluate(oracle, item, {slot: value}))), "")
    except Exception as exc:  # noqa: BLE001 - reported, not swallowed and not fatal
        out = (_PROBE_ERROR, repr(exc))
    cache[key] = out
    return out


def analyze(
    items: Sequence[Item],
    oracle: Oracle,
    *,
    probe_cap: int = 64,
    diagnostic_cap: int = 25,
) -> LinkAnalysis:
    """Enumerate candidate substitutions and decide which are live.

    ``probe_cap`` bounds how many codomain values are tried per link. ``diagnostic_cap``
    bounds how many diagnostics are retained *per code*: a corpus with ten thousand dead
    links would otherwise produce ten thousand identical-shaped messages and bury the
    three that matter. Both bounds, and the full per-code counts, are reported in ``caps``
    (AUDIT-ALL-0004) -- the verdicts themselves are never truncated.

    ``probe_cap`` must be at least 1. A cap of 0 empties every probe set, which would make
    every link dead and report the cause as an unprobeable codomain -- a bound rewriting
    the reason instead of being reported beside it.
    """
    if probe_cap < 1:
        raise CompositionError(
            f"probe_cap must be at least 1, got {probe_cap}; a cap of 0 withholds every "
            f"probe and would be reported as an unprobeable codomain (AUDIT-ALL-0004)"
        )
    verdicts: list[LinkVerdict] = []
    diags: list[Diagnostic] = []
    counts: dict[str, int] = {}
    cache: dict[tuple[str, str, str], tuple[str, str]] = {}
    seen_unbounded: set[str] = set()

    def note(diag: Diagnostic) -> None:
        counts[diag.code] = counts.get(diag.code, 0) + 1
        if counts[diag.code] <= diagnostic_cap:
            diags.append(diag)

    for down in items:
        for slot in down.slots:
            if slot.tag not in COMPOSABLE_TAGS:
                note(
                    Diagnostic(
                        "info",
                        "slot-tag-not-composable",
                        f"slot {slot.name!r} has tag {slot.tag!r}, which carries no link",
                        subject=down.id,
                        ruling="CORE-ALL-0004",
                    )
                )
                continue

            for up in items:
                if up.id == down.id:
                    continue
                for rv in up.results:
                    if rv.tag != slot.tag:
                        continue
                    if rv.tag not in COMPOSABLE_TAGS:
                        continue

                    cand = Candidate(up.id, rv.name, down.id, slot.name, slot.tag)
                    values = codomain_values(up, rv.name, cap=probe_cap)

                    if not values:
                        key = f"{up.id}.{rv.name}"
                        if key not in seen_unbounded:
                            seen_unbounded.add(key)
                            # Name which of the two causes it actually is. Saying "declares
                            # no codomain" about a result that declared an empty one states
                            # a cause that was never the case.
                            cause = (
                                "declares an empty codomain"
                                if up.result(rv.name).codomain is not None
                                else f"declares no codomain and its tag {rv.tag!r} has no "
                                f"probe set"
                            )
                            note(
                                Diagnostic(
                                    "warning",
                                    "codomain-unbounded",
                                    f"result {rv.name!r} {cause}, so liveness cannot be "
                                    f"decided and every link from it is refused",
                                    subject=up.id,
                                    ruling="LINK-ALL-0003",
                                )
                            )
                        verdicts.append(
                            LinkVerdict(cand, False, 0, 0, "codomain unbounded and unprobeable")
                        )
                        continue

                    probed = [
                        _probe_outcome(oracle, down, slot.name, v, cache) for v in values
                    ]
                    real = {o for o, err in probed if o != _PROBE_ERROR}
                    errors = [err for o, err in probed if o == _PROBE_ERROR]
                    live = len(real) > 1

                    if not live and errors and not real:
                        # Every probe was refused. The downstream did not ignore the
                        # upstream answer; it was never given a usable one, and saying
                        # otherwise would assert a cause that was never tested.
                        note(
                            Diagnostic(
                                "warning",
                                "oracle-raised",
                                f"{up.id}.{rv.name} -> {down.id}.{slot.name}: the oracle "
                                f"refused all {len(values)} probed values, so liveness "
                                f"could not be decided; first error: {errors[0][:120]}",
                                subject=f"{up.id}->{down.id}",
                                ruling="LINK-ALL-0007",
                            )
                        )
                        reason = "oracle refused every probed value; liveness undecided"
                    elif not live:
                        note(
                            Diagnostic(
                                "info",
                                "link-dead",
                                f"{up.id}.{rv.name} -> {down.id}.{slot.name}: downstream answer "
                                f"is constant over {len(values) - len(errors)} probed values"
                                + (f" ({slot.consumer})" if slot.consumer else ""),
                                subject=f"{up.id}->{down.id}",
                                ruling="LINK-ALL-0007",
                            )
                        )
                        reason = "downstream answer constant over codomain"
                    else:
                        reason = "live"

                    verdicts.append(
                        LinkVerdict(cand, live, len(real), len(values), reason)
                    )

    return LinkAnalysis(
        verdicts=tuple(verdicts),
        diagnostics=tuple(diags),
        caps={
            "probe_cap": probe_cap,
            "probe_int": list(PROBE_INT),
            "probe_bool": list(PROBE_BOOL),
            "probe_str": list(PROBE_STR),
            # Not `str_unbounded_refused`: a result of any tag lands here when its probe
            # set comes out empty, and on the calibration corpus this fills with `int`
            # results that declared an empty codomain. The old name asserted a cause.
            "unprobeable_results": sorted(seen_unbounded),
            "diagnostic_cap": diagnostic_cap,
            "diagnostic_counts": dict(sorted(counts.items())),
            "diagnostics_withheld": sum(
                max(0, n - diagnostic_cap) for n in counts.values()
            ),
        },
    )


# --------------------------------------------------------------------------- #
# construction
# --------------------------------------------------------------------------- #
def make_chain(components: Sequence[str], links: Sequence[Link]) -> Chain:
    """Validate and normalise a chain into topological order (LINK-ALL-0004/0005)."""
    n = len(components)
    if n == 0:
        raise LinkError("a chain needs at least one component")

    fed: set[tuple[int, str]] = set()
    for link in links:
        key = (link.downstream, link.slot)
        if key in fed:
            raise LinkError(
                f"slot {link.slot!r} on component {link.downstream} has more than one "
                f"incoming link ({_R_SLOT_ONCE})"
            )
        fed.add(key)

    try:
        order = topological_positions(n, links)
    except ValueError as exc:
        raise LinkError(f"{exc} ({_R_ACYCLIC})") from exc

    remap = {old: new for new, old in enumerate(order)}
    return Chain(
        components=tuple(components[i] for i in order),
        links=tuple(
            sorted(
                (
                    Link(remap[x.upstream], x.result, remap[x.downstream], x.slot, x.tag)
                    for x in links
                ),
                key=lambda x: (x.downstream, x.slot, x.upstream, x.result),
            )
        ),
    )


def singleton(item_id: str) -> Chain:
    """A depth-1 chain: the original item, unchanged (DEPTH-ALL-0003)."""
    return Chain(components=(item_id,), links=())


def chain_from_candidates(candidates: Sequence[Candidate]) -> Chain:
    """Build a chain from item-level candidates, one component per distinct item.

    Only valid when no item repeats; reuse must be expressed with explicit positions.
    """
    order: list[str] = []
    for c in candidates:
        for name in (c.upstream_item, c.downstream_item):
            if name not in order:
                order.append(name)
    pos = {name: i for i, name in enumerate(order)}
    links = [
        Link(pos[c.upstream_item], c.result, pos[c.downstream_item], c.slot, c.tag)
        for c in candidates
    ]
    return make_chain(tuple(order), links)


def enumerate_paths(
    analysis: LinkAnalysis, depth: int, *, cap: int = 10_000
) -> tuple[tuple[str, ...], ...]:
    """Node-distinct paths of exactly ``depth`` components over the live-link graph.

    Bounded by ``cap``; the caller is expected to report the bound (AUDIT-ALL-0004).
    """
    if depth < 1:
        raise ValueError("depth must be >= 1")
    adj = analysis.adjacency()
    nodes = sorted({c.upstream_item for c in analysis.live} | {c.downstream_item for c in analysis.live})
    if depth == 1:
        return tuple((n,) for n in nodes[:cap])

    out: list[tuple[str, ...]] = []
    stack: list[tuple[tuple[str, ...], frozenset[str]]] = [((n,), frozenset({n})) for n in nodes]
    while stack and len(out) < cap:
        path, seen = stack.pop()
        if len(path) == depth:
            out.append(path)
            continue
        for nxt in adj.get(path[-1], ()):
            if nxt not in seen:
                stack.append((path + (nxt,), seen | {nxt}))
    return tuple(sorted(out))


def _match_slots(
    slots: Sequence[str],
    options: Mapping[str, Sequence[Candidate]],
    *,
    exclude: str,
    want: int,
) -> dict[str, Candidate]:
    """Assign distinct upstream components to distinct slots of one sink.

    This is a bipartite matching, and first-fit greedy solves it only when the graph is
    fortunate: if an early slot consumes the only upstream a later slot could have used,
    greedy abandons a fan-in that exists. So a short greedy result is repaired with
    augmenting paths (Kuhn's algorithm). Deterministic: slots and options are both already
    in sorted order, and the search visits them in that order.
    """
    taken: dict[str, Candidate] = {}
    owner: dict[str, str] = {}

    def augment(slot: str, seen: set[str]) -> bool:
        for cand in options[slot]:
            if cand.upstream_item == exclude or cand.upstream_item in seen:
                continue
            seen.add(cand.upstream_item)
            held = owner.get(cand.upstream_item)
            if held is None or augment(held, seen):
                taken[slot] = cand
                owner[cand.upstream_item] = slot
                return True
        return False

    for slot in slots:
        if len(taken) == want:
            break
        augment(slot, set())
    return taken


def enumerate_fanins(
    analysis: LinkAnalysis, depth: int, *, cap: int = 10_000
) -> tuple[Chain, ...]:
    """Fan-in composites: one sink fed by ``depth - 1`` distinct upstream components.

    On a corpus whose live-link graph is shallow this is the only way to raise component
    count without authoring items (DEPTH-ALL-0002).
    """
    if depth < 2:
        raise ValueError("a fan-in needs at least 2 components")

    by_sink: dict[str, dict[str, list[Candidate]]] = {}
    for c in analysis.live:
        by_sink.setdefault(c.downstream_item, {}).setdefault(c.slot, []).append(c)

    out: list[Chain] = []
    for sink in sorted(by_sink):
        slots = sorted(by_sink[sink])
        if len(slots) < depth - 1:
            continue

        options = {
            slot: sorted(by_sink[sink][slot], key=lambda c: (c.upstream_item, c.result))
            for slot in slots
        }
        taken = _match_slots(slots, options, exclude=sink, want=depth - 1)
        chosen = [taken[slot] for slot in slots if slot in taken][: depth - 1]
        if len(chosen) != depth - 1:
            continue
        order = [c.upstream_item for c in chosen] + [sink]
        pos = {name: i for i, name in enumerate(order)}
        links = [
            Link(pos[c.upstream_item], c.result, pos[sink], c.slot, c.tag) for c in chosen
        ]
        out.append(make_chain(tuple(order), links))
        if len(out) >= cap:
            break
    return tuple(out)


# --------------------------------------------------------------------------- #
# gold and realization
# --------------------------------------------------------------------------- #
def chained_gold(
    chain: Chain, items: Mapping[str, Item], oracle: Oracle
) -> dict[str, Scalar]:
    """Evaluate the components one at a time, substituting along links (EMIT-ALL-0006).

    This is the reference computation. It never sees the realized composite, which is
    exactly why agreeing with it is evidence rather than tautology.
    """
    per_position: list[Mapping[str, Scalar]] = []
    gold: dict[str, Scalar] = {}
    for pos, item_id in enumerate(chain.components):
        item = items[item_id]
        overrides: dict[str, Scalar] = {}
        for link in chain.links:
            if link.downstream == pos:
                overrides[link.slot] = per_position[link.upstream][link.result]
        results = evaluate(oracle, item, overrides)
        per_position.append(results)
        for name, value in results.items():
            gold[qualified(pos, name)] = value
    return gold


def check_realization(
    chain: Chain, items: Mapping[str, Item], oracle: Oracle, realization: Realization
) -> tuple[Diagnostic, ...]:
    """The two by-construction checks. Raises rather than emitting an invalid composite."""
    expected = chained_gold(chain, items, oracle)
    got = realization.gold_map()
    if canonical_json(expected) != canonical_json(got):
        raise GoldDisagreementError(
            f"{_R_AGREE}: realized gold disagrees with the chained component oracles.\n"
            f"  chained : {canonical_json(expected)}\n"
            f"  realized: {canonical_json(got)}"
        )

    diags: list[Diagnostic] = []
    if realization.meta.get("gold_route") == "chained":
        diags.append(
            Diagnostic(
                "info",
                "gold-route-chained",
                "this realizer computes the gold by chaining the component oracles, which "
                "is the same computation the agreement check uses as its reference, so the "
                "check is vacuous here; it has force only for a realizer that reaches the "
                "gold by an independent route",
                subject=str(realization.meta.get("realizer", "?")),
                ruling="EMIT-ALL-0006",
            )
        )
    for link in chain.links:
        name = qualified(link.downstream, link.slot)
        if name in realization.bindings:
            raise LiteralLeakError(
                f"{_R_SUPPRESS}: slot {link.slot!r} on component {link.downstream} is fed by a "
                f"link but the realization still binds it to "
                f"{realization.bindings[name]!r}; a system could read the upstream answer "
                f"instead of computing it"
            )
        if name not in realization.suppressed:
            diags.append(
                Diagnostic(
                    "warning",
                    "literal-leak",
                    f"realizer did not declare {name!r} suppressed, though it is linked",
                    subject=name,
                    ruling="EMIT-ALL-0001",
                )
            )
    return tuple(diags)


def composite_id(chain: Chain) -> str:
    """Content hash over the composite's shape and links (EMIT-ALL-0005).

    The spec version is deliberately NOT hashed. It is recorded alongside the id, in the
    emitted record, because it is a stamp on how the composite was decided rather than
    part of what the composite is. Hashing it would move every id on an editorial spec
    patch -- a change that by definition alters no decision -- and so would break the
    "only if" half of the rule. (That is not hypothetical: an earlier spec did hash it.
    See EMIT-ALL-0005's rationale for the supersession.)
    """
    return content_hash(
        {
            "components": list(chain.components),
            "links": [
                [x.upstream, x.result, x.downstream, x.slot, x.tag] for x in chain.links
            ],
        }
    )


def realize(
    chain: Chain,
    items: Mapping[str, Item],
    oracle: Oracle,
    realizer: Realizer,
    *,
    strata: Sequence[str] = (),
) -> tuple[Composite, tuple[Diagnostic, ...]]:
    """Realize a chain and accept it only if it passes both by-construction checks."""
    components = [items[cid] for cid in chain.components]
    try:
        realization = realizer(components, list(chain.links))
    except Exception as exc:  # noqa: BLE001 - a user realizer, reported not swallowed
        raise CompositionError(
            f"realizer failed on chain {'+'.join(chain.components)}: {exc!r}"
        ) from exc

    diags = check_realization(chain, items, oracle, realization)
    return (
        Composite(
            id=composite_id(chain),
            chain=chain,
            realization=realization,
            strata=tuple(strata),
            rulings_version=spec_version(),
        ),
        diags,
    )


def reuse_multiplicity(chains: Iterable[Chain]) -> dict[str, int]:
    """How many composites each component appears in (LINK-ALL-0006)."""
    counts: dict[str, int] = {}
    for chain in chains:
        for cid in set(chain.components):
            counts[cid] = counts.get(cid, 0) + 1
    return dict(sorted(counts.items()))


def composite_record(composite: Composite) -> dict[str, object]:
    """The emitted JSONL record for one composite.

    Carries everything needed to score it, to reproduce it, and to check it later: the
    component ids, the links, the depth and path depth, the per-component strata, the
    gold, the presentation, and the rulings version that produced it.
    """
    chain = composite.chain
    return {
        "id": composite.id,
        "depth": chain.depth,
        "path_depth": chain.path_depth,
        "components": list(chain.components),
        "links": [
            {
                "upstream": x.upstream,
                "result": x.result,
                "downstream": x.downstream,
                "slot": x.slot,
                "tag": x.tag,
            }
            for x in chain.links
        ],
        "strata": list(composite.strata),
        "gold": dict(composite.realization.gold),
        "rendering": dict(composite.realization.rendering),
        "suppressed": list(composite.realization.suppressed),
        "meta": dict(composite.realization.meta),
        "spec": composite.rulings_version,
    }
