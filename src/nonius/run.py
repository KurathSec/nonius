"""Running composites against systems -- the one part of nonius that can spend money.

Everything else in this package is offline and free (EMIT-ALL-0004, AUDIT-ALL-0003). This
module is the exception, so it is built to refuse by default:

* it requires a pre-registration file, so the thresholds a run will be read against are
  fixed before the first completion is bought;
* it requires an explicit authorisation flag, because a default that spends is a bug;
* without both, it prints the plan and the completion count and does nothing else.

nonius does not ship a model client. The caller supplies ``complete(prompt) -> str``,
which keeps this module free of network code and keeps the choice of provider, retry
policy and rate limit where it belongs -- with the person paying.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from nonius.errors import ManifestError, NoniusError
from nonius.spec.registry import require

_R_OFFLINE = require("EMIT-ALL-0004")
_R_CEILING = require("BOUND-ALL-0004")

Completer = Callable[[str], str]


class NotAuthorised(NoniusError):
    """A run was requested without a pre-registration or without authorisation."""


@dataclass(frozen=True, slots=True)
class Preregistration:
    """The thresholds a run will be read against, fixed before it starts."""

    id: str
    status: str
    depths: tuple[int, ...]
    composites_per_depth: int
    models: tuple[str, ...]
    k: int
    quarantine_ceiling: float
    #: How many composites are actually planned per depth, when the file declares it. The
    #: cap does not bind at every depth: a link graph can simply not contain that many
    #: chains, and a budget computed from the cap alone would overstate the run.
    planned_composites: Mapping[int, int] = field(default_factory=dict)
    #: LINK-ALL-0006's reuse ceiling, when declared. ``None`` means the file declares none,
    #: and `guard_reuse` then has nothing to enforce.
    reuse_ceiling: int | None = None
    raw: Mapping[str, object] = field(default_factory=dict)

    @property
    def ceiling_completions(self) -> int:
        """The most this run could buy: every depth filled to the cap."""
        return len(self.depths) * self.composites_per_depth * len(self.models) * self.k

    @property
    def planned_completions(self) -> int:
        """What the run actually plans to buy, from the declared per-depth populations.

        Falls back to the ceiling when the file declares no per-depth plan.
        """
        if not self.planned_composites:
            return self.ceiling_completions
        planned = sum(
            min(self.planned_composites.get(d, self.composites_per_depth), self.composites_per_depth)
            for d in self.depths
        )
        return planned * len(self.models) * self.k


def load_preregistration(path: str | Path) -> Preregistration:
    data = tomllib.loads(Path(path).read_bytes().decode("utf-8"))
    run = data.get("run", {})
    pop = data.get("population", {})
    systems = data.get("systems", {})

    # Selected by the ruling the threshold cites, not by position. An earlier version took
    # the LAST threshold carrying a key named `ceiling`, so adding an unrelated threshold
    # with a `ceiling` key silently replaced the quarantine one -- a footgun that was
    # documented in three places instead of removed.
    quarantine = [
        t
        for t in data.get("threshold", [])
        if "ceiling" in t and str(t.get("ruling", "")) == _R_CEILING
    ]
    if len(quarantine) > 1:
        raise NotAuthorised(
            f"{path} declares {len(quarantine)} quarantine ceilings "
            f"({[t.get('id') for t in quarantine]}); exactly one threshold may cite "
            f"{_R_CEILING}"
        )
    if not quarantine:
        stray = [t.get("id") for t in data.get("threshold", []) if "ceiling" in t]
        raise NotAuthorised(
            f"{path} declares no quarantine ceiling; without one the validity gate can "
            f"only confirm itself ({_R_CEILING})."
            + (
                f" Thresholds {stray} carry a `ceiling` key but none cites {_R_CEILING}; "
                f"a ceiling that names no ruling is not the quarantine ceiling."
                if stray
                else ""
            )
        )
    ceiling = float(quarantine[0]["ceiling"])

    planned = {
        int(str(key).removeprefix("depth_")): int(value)
        for key, value in dict(pop.get("planned_composites", {})).items()
    }
    reuse = data.get("reuse", {})

    return Preregistration(
        id=str(run.get("id", "")),
        status=str(run.get("status", "")),
        depths=tuple(int(d) for d in pop.get("depths", ())),
        composites_per_depth=int(pop.get("composites_per_depth", 0)),
        models=tuple(str(m) for m in systems.get("models", ())),
        k=int(systems.get("k", 0)),
        quarantine_ceiling=ceiling,
        planned_composites=planned,
        reuse_ceiling=int(reuse["ceiling"]) if "ceiling" in reuse else None,
        raw=data,
    )


def plan(prereg: Preregistration, composites: Sequence[Mapping[str, object]]) -> str:
    """What a run would do, and what it would cost. Spends nothing."""
    by_depth: dict[int, int] = {}
    for record in composites:
        depth = int(record["depth"])  # type: ignore[call-overload]
        by_depth[depth] = by_depth.get(depth, 0) + 1

    lines = [
        f"pre-registration : {prereg.id}  (status: {prereg.status})",
        f"quarantine ceiling: {prereg.quarantine_ceiling:.2f}  (BOUND-ALL-0004)",
        "reuse ceiling     : "
        + ("not declared" if prereg.reuse_ceiling is None else str(prereg.reuse_ceiling))
        + "  (LINK-ALL-0006)",
        f"systems          : {len(prereg.models)} x k={prereg.k}",
        f"depths           : {', '.join(str(d) for d in prereg.depths)}",
        "",
        "composites supplied, by depth:",
    ]
    total = 0
    refusals: list[str] = []
    for depth in sorted(by_depth):
        supplied = by_depth[depth]
        calls = supplied * len(prereg.models) * prereg.k
        total += calls
        mark = ""
        if depth not in prereg.depths:
            mark = "   [REFUSED: not in the pre-registered depth set]"
            refusals.append(f"depth {depth} is not pre-registered")
        elif supplied > prereg.composites_per_depth:
            mark = f"   [REFUSED: over the {prereg.composites_per_depth} cap]"
            refusals.append(f"depth {depth} supplies {supplied} > {prereg.composites_per_depth}")
        lines.append(
            f"  depth {depth:>2}: {supplied:>5} supplied -> {calls:>7} completions{mark}"
        )
    lines += ["", f"total completions if all were runnable: {total}"]
    if refusals:
        # plan() and execute() must agree. Forecasting a silent trim that execute() would
        # refuse outright is how a plan stops describing the run it precedes.
        lines += [
            "",
            "execute() WOULD REFUSE this set: " + "; ".join(refusals) + ".",
            "Trim the set deliberately rather than letting the run decide what to drop.",
        ]
    if prereg.status != "authorised":
        lines += [
            "",
            f"execute() would also refuse on status: this file says {prereg.status!r}, and "
            f"only 'authorised' runs. Changing it is a deliberate act in the file, not a "
            f"flag on the command line.",
        ]
    lines += [
        "",
        "NOTHING HAS BEEN RUN, and this verb cannot run anything. Executing means calling "
        "nonius.run.execute() from your own code, with your own model client.",
    ]
    return "\n".join(lines)


def execute(
    prereg: Preregistration,
    composites: Sequence[Mapping[str, object]],
    complete: Completer,
    *,
    authorised: bool = False,
    language: str = "python",
) -> list[dict[str, object]]:
    """Run composites against a system. Refuses unless explicitly authorised.

    Returns raw completion records; grading is the caller's, using the composite's own
    gold. nonius does not decide what a system meant to say.
    """
    if not authorised:
        raise NotAuthorised(
            "execute() requires authorised=True. This is the only function in nonius that "
            "can spend money, and it does not do so by default."
        )
    if prereg.status != "authorised":
        raise NotAuthorised(
            f"pre-registration {prereg.id!r} has status {prereg.status!r}; set it to "
            f"'authorised' deliberately, in the file, before running"
        )

    # Validate the whole set BEFORE buying anything. A mid-loop refusal has already spent
    # money on the records it got through, which defeats the point of refusing.
    by_depth: dict[int, int] = {}
    for n, record in enumerate(composites):
        rendering = record.get("rendering", {})
        if not isinstance(rendering, dict):
            raise ManifestError(
                f"composite {record.get('id', n)!r}: 'rendering' must be an object, "
                f"got {type(rendering).__name__}"
            )
        try:
            depth = int(record["depth"])  # type: ignore[call-overload]
        except (KeyError, TypeError, ValueError) as exc:
            raise ManifestError(f"composite {record.get('id', n)!r}: bad 'depth': {exc}") from exc
        if depth not in prereg.depths:
            raise NotAuthorised(
                f"composite {record.get('id', n)!r} is depth {depth}, which is not in the "
                f"pre-registered depth set {list(prereg.depths)}. The run must buy the "
                f"population that was registered, or the thresholds are read against "
                f"something else."
            )
        by_depth[depth] = by_depth.get(depth, 0) + 1

    over = {d: n for d, n in sorted(by_depth.items()) if n > prereg.composites_per_depth}
    if over:
        raise NotAuthorised(
            f"more composites supplied than pre-registered: {over} against "
            f"composites_per_depth={prereg.composites_per_depth}. Trim the set "
            f"deliberately rather than letting the run decide what to drop."
        )

    out: list[dict[str, object]] = []
    for record in composites:
        rendering = record.get("rendering", {})
        assert isinstance(rendering, dict)  # re-established by the pre-pass above
        prompt = rendering.get(language)
        if prompt is None:
            continue
        for draw in range(prereg.k):
            out.append(
                {
                    "composite": record["id"],
                    "depth": record["depth"],
                    "draw": draw,
                    "raw_output": complete(str(prompt)),
                }
            )
    return out
