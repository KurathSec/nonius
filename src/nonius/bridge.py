"""The bridge table (ARCHITECTURE.md section 10).

PF-11's second horn: switching instruments destroys comparability with every previously
published number, and no bridging procedure exists. This table is nonius's answer, and it
is a modest one.

For each system it puts three numbers side by side: the score the *old* instrument gave,
the score the composed instrument predicts under the independence bound, and -- when a
measurement exists -- the singleton accuracy the measured composite score implies. So a
historical number can be read on the new scale and a new number on the old one.

**What this is not.** It is an arithmetic re-expression under a stated assumption, not a
proof of measurement equivalence. Every failure of independence is inherited. If the
residual column is large, the assumption is wrong and the re-expression is wrong with it;
that column exists so the failure is visible rather than buried.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from nonius.archive import Archive
from nonius.bound import product_prediction
from nonius.model import Chain
from nonius.stats import mean


@dataclass(frozen=True, slots=True)
class BridgeRow:
    """One system, one depth: the old score and the new one, each in both currencies."""

    system: str
    depth: int
    singleton: float
    predicted_composite: float
    measured_composite: float | None
    #: The singleton accuracy the measured composite score implies, ``c ** (1/depth)``.
    #: Comparable to ``singleton`` only under independence and component exchangeability.
    implied_singleton: float | None
    #: measured - predicted. Zero means the independence assumption held on this set.
    residual: float | None

    def line(self) -> str:
        meas = "     --" if self.measured_composite is None else f"{self.measured_composite:7.4f}"
        impl = "     --" if self.implied_singleton is None else f"{self.implied_singleton:7.4f}"
        resid = "      --" if self.residual is None else f"{self.residual:+8.4f}"
        return (
            f"{self.system[:28]:<28} d={self.depth:<2} "
            f"singleton {self.singleton:7.4f}  predicted {self.predicted_composite:7.4f}  "
            f"measured {meas}  implies {impl}  residual {resid}"
        )


def reexpress(singleton: float, depth: int) -> float:
    """A historical singleton score, expressed on the composed instrument's scale.

    ``p ** depth`` -- the independence bound read forwards. Exact at depth 1 by
    construction (DEPTH-ALL-0001), and increasingly assumption-laden after that.
    """
    if not 0.0 <= singleton <= 1.0:
        raise ValueError(f"singleton accuracy out of range: {singleton}")
    if depth < 1:
        raise ValueError("depth must be >= 1")
    return singleton**depth


def imply_singleton(composite: float, depth: int) -> float:
    """The composed instrument's score, expressed on the old scale: ``c ** (1/depth)``."""
    if not 0.0 <= composite <= 1.0:
        raise ValueError(f"composite accuracy out of range: {composite}")
    if depth < 1:
        raise ValueError("depth must be >= 1")
    return float(composite ** (1.0 / depth))


def build(
    chains: Sequence[Chain],
    archive: Archive,
    *,
    depth: int,
    measured: Mapping[str, float] | None = None,
) -> tuple[BridgeRow, ...]:
    """The bridge table for one depth over one emitted set.

    ``measured`` is the observed mean composite accuracy per system, when one exists.
    """
    rows: list[BridgeRow] = []
    for system in archive.systems:
        singleton = mean(
            [r for i in archive.items if (r := archive.rate(system, i)) is not None]
        )
        preds = [
            p
            for chain in chains
            if (p := product_prediction(archive, system, chain.components)) is not None
        ]
        predicted = mean(preds)
        obs = (measured or {}).get(system)
        rows.append(
            BridgeRow(
                system=system,
                depth=depth,
                singleton=singleton,
                predicted_composite=predicted,
                measured_composite=obs,
                implied_singleton=None if obs is None else imply_singleton(obs, depth),
                residual=None if obs is None else obs - predicted,
            )
        )
    return tuple(rows)


def render(rows: Sequence[BridgeRow]) -> str:
    header = (
        "Bridge table -- an arithmetic re-expression under an independence assumption,\n"
        "not a proof of measurement equivalence. A large residual means the assumption\n"
        "failed and both directions of the re-expression failed with it.\n"
    )
    return header + "\n".join(r.line() for r in sorted(rows, key=lambda r: (r.depth, r.system)))
