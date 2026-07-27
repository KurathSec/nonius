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

from nonius.errors import NoniusError
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
    raw: Mapping[str, object] = field(default_factory=dict)

    @property
    def estimated_completions(self) -> int:
        return len(self.depths) * self.composites_per_depth * len(self.models) * self.k


def load_preregistration(path: str | Path) -> Preregistration:
    data = tomllib.loads(Path(path).read_bytes().decode("utf-8"))
    run = data.get("run", {})
    pop = data.get("population", {})
    systems = data.get("systems", {})

    ceiling = None
    for threshold in data.get("threshold", []):
        if "ceiling" in threshold:
            ceiling = float(threshold["ceiling"])
    if ceiling is None:
        raise NotAuthorised(
            f"{path} declares no quarantine ceiling; without one the validity gate can "
            f"only confirm itself ({_R_CEILING})"
        )

    return Preregistration(
        id=str(run.get("id", "")),
        status=str(run.get("status", "")),
        depths=tuple(int(d) for d in pop.get("depths", ())),
        composites_per_depth=int(pop.get("composites_per_depth", 0)),
        models=tuple(str(m) for m in systems.get("models", ())),
        k=int(systems.get("k", 0)),
        quarantine_ceiling=ceiling,
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
        f"systems          : {len(prereg.models)} x k={prereg.k}",
        f"depths           : {', '.join(str(d) for d in prereg.depths)}",
        "",
        "composites supplied, by depth:",
    ]
    total = 0
    for depth in sorted(by_depth):
        planned = min(by_depth[depth], prereg.composites_per_depth)
        calls = planned * len(prereg.models) * prereg.k
        total += calls
        mark = "" if depth in prereg.depths else "   [NOT in the pre-registered depth set]"
        lines.append(f"  depth {depth:>2}: {by_depth[depth]:>5} available, {planned:>5} planned"
                     f" -> {calls:>7} completions{mark}")
    lines += [
        "",
        f"total completions: {total}",
        "",
        "NOTHING HAS BEEN RUN. Pass an explicit authorisation to execute.",
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

    out: list[dict[str, object]] = []
    for record in composites:
        rendering = record.get("rendering", {})
        assert isinstance(rendering, dict)
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
