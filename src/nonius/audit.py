"""The composability audit (ARCHITECTURE.md section 11).

The pre-flight. Given items and an oracle, and before a single composite is emitted or a
single completion is bought, it answers: **can this benchmark be composed at all, and how
far?**

Nothing in the twelve instruments surveyed for this problem does this. They compose, or
they do not; none of them declines with a reason. On real corpora declining is the common
answer, and the reason is rarely the one a practitioner expects -- type compatibility
usually looks fine while liveness has quietly killed most of the graph.

The audit issues no model calls, spends nothing, and emits no composites (AUDIT-ALL-0003).
Every bound it applies to its own search is reported (AUDIT-ALL-0004).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from nonius.archive import Archive
from nonius.canonical import canonical_json
from nonius.compose import (
    LinkAnalysis,
    analyze,
    enumerate_fanins,
    enumerate_paths,
    make_chain,
)
from nonius.model import Chain, Diagnostic, Item, Link
from nonius.oracle import Oracle
from nonius.resolution import DepthReadout, predict, singleton_row, table
from nonius.spec.registry import require, spec_version

_R_VERDICT = require("AUDIT-ALL-0001")
_R_POPULATION = require("AUDIT-ALL-0002")
_R_OFFLINE = require("AUDIT-ALL-0003")
_R_CAPS = require("AUDIT-ALL-0004")

#: Hard stop on the upward depth search, so a densely linked corpus cannot spin forever.
#: Reached-the-cap is reported as a bound, never as the answer.
MAX_DEPTH_SEARCH = 32


@dataclass(frozen=True, slots=True)
class FamilyReach:
    """What a stratum of items can do in a chain."""

    family: str
    items: int
    can_start: int
    can_continue: int
    isolated: int

    @property
    def composable(self) -> bool:
        return self.isolated < self.items


@dataclass(frozen=True, slots=True)
class AuditReport:
    """The audit's answer."""

    verdict: str
    max_depth: int
    spec: str

    items: int
    ordered_pairs: int
    candidate_links: int
    live_links: int
    live_pairs: int

    reach: tuple[FamilyReach, ...]
    chains_at_depth: Mapping[int, int]
    fanins_at_depth: Mapping[int, int]

    reasons: tuple[str, ...] = ()
    readouts: tuple[DepthReadout, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    caps: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "max_depth": self.max_depth,
            "spec": self.spec,
            "items": self.items,
            "ordered_pairs": self.ordered_pairs,
            "candidate_links": self.candidate_links,
            "live_links": self.live_links,
            "live_pairs": self.live_pairs,
            "reach": [
                {
                    "family": r.family,
                    "items": r.items,
                    "can_start": r.can_start,
                    "can_continue": r.can_continue,
                    "isolated": r.isolated,
                }
                for r in self.reach
            ],
            "chains_at_depth": {str(k): v for k, v in sorted(self.chains_at_depth.items())},
            "fanins_at_depth": {str(k): v for k, v in sorted(self.fanins_at_depth.items())},
            "reasons": list(self.reasons),
            "readouts": [
                {
                    "depth": r.depth,
                    "n": r.n,
                    "source": r.source,
                    "accuracy": dict(sorted(r.accuracy.items())),
                    "dead": r.dead,
                    "floored": r.floored,
                    "discriminating": r.discriminating,
                    "top_two_gap": r.top_two_gap,
                    "m_star": r.m_star,
                    "caps": dict(r.caps),
                }
                for r in self.readouts
            ],
            "diagnostics": [
                {
                    "severity": d.severity,
                    "code": d.code,
                    "message": d.message,
                    "subject": d.subject,
                    "ruling": d.ruling,
                }
                for d in self.diagnostics
            ],
            "caps": dict(self.caps),
        }

    def to_json(self) -> str:
        return canonical_json(self.to_dict(), indent=2)

    def render(self) -> str:
        lines = [f"verdict: {self.verdict}", ""]
        pct = (
            f"{self.live_links / self.candidate_links:.1%}" if self.candidate_links else "n/a"
        )
        ppct = f"{self.live_pairs / self.ordered_pairs:.1%}" if self.ordered_pairs else "n/a"
        lines += [
            f"  items            {self.items:>8}",
            f"  candidate links  {self.candidate_links:>8}   type-compatible (LINK-ALL-0001)",
            f"  live links       {self.live_links:>8}   {pct:>6}   admissible (LINK-ALL-0002)",
            f"  live pairs       {self.live_pairs:>8}   {ppct:>6} of {self.ordered_pairs} "
            f"ordered pairs carry a live link",
            f"  max components   {self.max_depth:>8}",
            "",
        ]
        if self.reach:
            lines.append(
                f"  {'family':<24}{'items':>7}{'can start':>11}{'can continue':>14}"
                f"{'isolated':>10}"
            )
            for r in self.reach:
                lines.append(
                    f"  {r.family[:24]:<24}{r.items:>7}{r.can_start:>11}"
                    f"{r.can_continue:>14}{r.isolated:>10}"
                )
            lines.append("")
        if self.chains_at_depth or self.fanins_at_depth:
            depths = sorted(set(self.chains_at_depth) | set(self.fanins_at_depth))
            lines.append(f"  {'depth':>6}{'paths':>10}{'fan-ins':>10}")
            for d in depths:
                lines.append(
                    f"  {d:>6}{self.chains_at_depth.get(d, 0):>10}"
                    f"{self.fanins_at_depth.get(d, 0):>10}"
                )
            lines.append("")
        for reason in self.reasons:
            lines.append(f"  {reason}")
        if self.readouts:
            lines += ["", table(self.readouts)]
        return "\n".join(lines)


def _reach(items: Sequence[Item], analysis: LinkAnalysis) -> tuple[FamilyReach, ...]:
    starts = {c.upstream_item for c in analysis.live}
    conts = {c.downstream_item for c in analysis.live}
    by_family: dict[str, list[Item]] = {}
    for item in items:
        by_family.setdefault(item.family or "(unlabelled)", []).append(item)

    out: list[FamilyReach] = []
    for family in sorted(by_family):
        members = by_family[family]
        can_start = sum(1 for i in members if i.id in starts)
        can_cont = sum(1 for i in members if i.id in conts)
        isolated = sum(1 for i in members if i.id not in starts and i.id not in conts)
        out.append(FamilyReach(family, len(members), can_start, can_cont, isolated))
    return tuple(out)


#: The chain shapes the audit enumerates. A composite may legally be any DAG
#: (``make_chain`` accepts one), but the audit searches these two, so the component count
#: it reports is a lower bound on what is constructible, not the maximum over all shapes.
#: Declared here and reported in every audit's ``caps`` (AUDIT-ALL-0004).
ENUMERATED_SHAPES: tuple[str, ...] = ("path", "fan-in")


def _max_depth(analysis: LinkAnalysis, *, path_cap: int) -> tuple[int, bool]:
    """Largest component count over the enumerated shapes, and whether the search capped.

    Not the maximum over all DAG shapes: a mixed shape -- a fan-in whose sink then feeds a
    further component -- can exceed this, and such a chain is perfectly legal. What is
    reported is therefore a floor with its search space declared, which is the honest
    reading of AUDIT-ALL-0004 rather than a claim of completeness.
    """
    if not analysis.live:
        return 1, False
    best = 1
    for depth in range(2, MAX_DEPTH_SEARCH + 1):
        paths = enumerate_paths(analysis, depth, cap=1)
        fans = enumerate_fanins(analysis, depth, cap=1)
        if not paths and not fans:
            return best, False
        best = depth
    return best, True


def _reasons(items: Sequence[Item], analysis: LinkAnalysis) -> tuple[str, ...]:
    starts = {c.upstream_item for c in analysis.live}
    conts = {c.downstream_item for c in analysis.live}
    by_family: dict[str, list[Item]] = {}
    for item in items:
        by_family.setdefault(item.family or "(unlabelled)", []).append(item)

    isolated = sorted(
        f
        for f, members in by_family.items()
        if all(i.id not in starts and i.id not in conts for i in members)
    )
    sinks = sorted(
        f
        for f, members in by_family.items()
        if any(i.id in conts for i in members)
        and all(i.id not in starts for i in members)
    )

    out: list[str] = []
    if isolated:
        out.append(
            "cannot compose in either direction: " + ", ".join(isolated)
        )
    if sinks:
        out.append("can only terminate a chain, never start one: " + ", ".join(sinks))

    live_tags: set[str] = {c.tag for c in analysis.live}
    tested: dict[str, int] = {}
    unprobed: dict[str, int] = {}
    for v in analysis.verdicts:
        if v.live:
            continue
        bucket = tested if v.probed else unprobed
        bucket[v.candidate.tag] = bucket.get(v.candidate.tag, 0) + 1

    for tag in sorted(set(tested) | set(unprobed)):
        if tag in live_tags:
            continue
        if tested.get(tag):
            out.append(
                f"every {tag} link is dead ({tested[tag]} candidates): the downstream "
                f"answer never varies over the upstream codomain"
            )
        if unprobed.get(tag):
            # Never probed is not the same as probed and found constant; claiming the
            # latter would assert a cause that was never tested.
            out.append(
                f"{unprobed[tag]} {tag} candidates were never probed: their upstream "
                f"result declares no codomain and {tag} has no probe set (LINK-ALL-0003)"
            )
    return tuple(out)


def _paths_as_chains(analysis: LinkAnalysis, paths: Sequence[tuple[str, ...]]) -> list[Chain]:
    chains: list[Chain] = []
    for path in paths:
        links: list[Link] = []
        ok = True
        used: set[tuple[int, str]] = set()
        for pos in range(len(path) - 1):
            options = analysis.live_for(path[pos], path[pos + 1])
            choice = next(
                (c for c in options if (pos + 1, c.slot) not in used),
                None,
            )
            if choice is None:
                ok = False
                break
            used.add((pos + 1, choice.slot))
            links.append(Link(pos, choice.result, pos + 1, choice.slot, choice.tag))
        if ok:
            chains.append(make_chain(path, links))
    return chains


def singletons(items: Sequence[Item]) -> tuple[Chain, ...]:
    """The depth-1 population: every item, composed with nothing.

    A depth-1 composite is the original item (DEPTH-ALL-0001), which is true of every
    item regardless of whether any link touches it. This is deliberately NOT the
    live-link graph's node set -- an item nothing can chain to is still a perfectly good
    singleton, and dropping it would make the depth-1 baseline a different population
    from the one the source instrument scored.
    """
    return tuple(make_chain((i.id,), []) for i in items)


def constructible(
    analysis: LinkAnalysis, depth: int, *, cap: int = 10_000
) -> tuple[Chain, ...]:
    """Chains of exactly ``depth`` components, over the shapes the audit enumerates.

    Paths first, then fan-ins (DEPTH-ALL-0002), deduplicated on shape *and* links -- two
    chains over the same components with different links are different composites with
    different gold. One chain is materialised per node sequence: alternative (result,
    slot) assignments along the same sequence are not enumerated, which is why
    ``ENUMERATED_SHAPES`` is reported rather than assumed away.

    At depth 1 this returns only items the live-link graph touches; for the singleton
    baseline use :func:`singletons`, which does not filter. Bounded by ``cap``.
    """
    if depth == 1:
        ids = sorted(
            {c.upstream_item for c in analysis.live} | {c.downstream_item for c in analysis.live}
        )
        return tuple(make_chain((i,), []) for i in ids[:cap])
    chains = _paths_as_chains(analysis, enumerate_paths(analysis, depth, cap=cap))
    # Key on links as well as components: a fan-in and a path can visit the same items in
    # the same order while joining them differently, and those are not the same composite.
    seen = {(c.components, c.links) for c in chains}
    for fan in enumerate_fanins(analysis, depth, cap=cap):
        if (fan.components, fan.links) not in seen:
            chains.append(fan)
            seen.add((fan.components, fan.links))
    return tuple(chains[:cap])


def audit(
    items: Sequence[Item],
    oracle: Oracle,
    *,
    archive: Archive | None = None,
    depths: Sequence[int] = (1, 2, 3, 5, 8),
    probe_cap: int = 64,
    path_cap: int = 10_000,
    sample: int | None = 20_000,
    seed: int = 0,
) -> AuditReport:
    """Run the composability audit. No model calls, no composites emitted."""
    analysis = analyze(items, oracle, probe_cap=probe_cap)

    n = len(items)
    ordered_pairs = n * (n - 1)
    live_pairs = len(analysis.live_pairs())
    max_depth, capped = _max_depth(analysis, path_cap=path_cap)

    chains_at: dict[int, int] = {}
    fanins_at: dict[int, int] = {}
    readouts: list[DepthReadout] = []
    # Depths where enumeration stopped at the cap rather than running out of chains. A
    # truncated search reads as "covered everything" unless it says so (AUDIT-ALL-0004).
    truncated: list[int] = []

    wanted = sorted({d for d in depths if d >= 1} | {1})
    for depth in wanted:
        if depth == 1:
            chains_at[1] = n
            fanins_at[1] = 0
            if archive is not None:
                readouts.append(singleton_row(archive, seed=seed))
            continue
        paths = enumerate_paths(analysis, depth, cap=path_cap)
        fans = enumerate_fanins(analysis, depth, cap=path_cap)
        chains_at[depth] = len(paths)
        fanins_at[depth] = len(fans)
        if len(paths) >= path_cap or len(fans) >= path_cap:
            truncated.append(depth)
        if archive is not None:
            pool = constructible(analysis, depth, cap=path_cap)
            if pool:
                readouts.append(
                    predict(pool, archive, depth=depth, seed=seed, sample=sample)
                )

    if not analysis.live:
        verdict = "not_composable"
    elif capped:
        verdict = "composable"
    else:
        verdict = f"composable_to_depth_{max_depth}"

    return AuditReport(
        verdict=verdict,
        max_depth=max_depth,
        spec=spec_version(),
        items=n,
        ordered_pairs=ordered_pairs,
        candidate_links=len(analysis.candidates),
        live_links=len(analysis.live),
        live_pairs=live_pairs,
        reach=_reach(items, analysis),
        chains_at_depth=chains_at,
        fanins_at_depth=fanins_at,
        reasons=_reasons(items, analysis),
        readouts=tuple(readouts),
        diagnostics=analysis.diagnostics,
        caps={
            **dict(analysis.caps),
            "path_cap": path_cap,
            "path_cap_reached_at_depths": truncated,
            "sample": sample,
            "enumerated_shapes": list(ENUMERATED_SHAPES),
            "max_depth_search": MAX_DEPTH_SEARCH,
            "max_depth_search_hit_cap": capped,
            "seed": seed,
        },
    )
