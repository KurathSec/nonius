"""The independence product bound and the quarantine rule (ARCHITECTURE.md section 8).

A composite is failed if any component is failed, so under independence a system's
composite accuracy is the product of its accuracies on the components. That product is
the **null the measurement is read against** -- never the gold, and never a verdict about
a system (BOUND-ALL-0001).

The rule has one direction with teeth. A composite whose *measured* accuracy exceeds its
product prediction by more than the archive's own replicate noise band is doing better
than composition allows, which means the chain did not bind: a shortcut exists, and the
item is quarantined as invalid rather than counted as a success (BOUND-ALL-0003).

The rule also has a way of being self-serving, and nonius refuses to let it be. If items
that beat the bound are discarded as invalid and items that match it are reported as
confirmation, the gate can only ever confirm itself. So the quarantine ceiling is a
required parameter, declared before measurement, and it is printed next to the observed
rate every time (BOUND-ALL-0004).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from nonius.archive import Archive
from nonius.compose import reuse_multiplicity
from nonius.errors import NoniusError
from nonius.model import Chain
from nonius.spec.registry import require
from nonius.stats import ci95_bootstrap, mean

_R_PRODUCT = require("BOUND-ALL-0001")
_R_REUSE = require("LINK-ALL-0006")
_R_BAND = require("BOUND-ALL-0002")
_R_QUARANTINE = require("BOUND-ALL-0003")
_R_CEILING = require("BOUND-ALL-0004")


class ReuseCeilingExceeded(NoniusError):
    """A component appears in more composites than the declared ceiling allows."""


@dataclass(frozen=True, slots=True)
class ReuseReport:
    """How often each component is reused across an emitted set (LINK-ALL-0006)."""

    ceiling: int
    multiplicity: Mapping[str, int]

    @property
    def worst(self) -> tuple[str, int]:
        if not self.multiplicity:
            return ("", 0)
        item, count = max(sorted(self.multiplicity.items()), key=lambda kv: kv[1])
        return (item, count)

    @property
    def exceeds_ceiling(self) -> bool:
        return self.worst[1] > self.ceiling

    def line(self) -> str:
        item, count = self.worst
        verdict = "OVER CEILING" if self.exceeds_ceiling else "within ceiling"
        return (
            f"component reuse: worst is {item or '(none)'} in {count} composites "
            f"against declared ceiling {self.ceiling} [{verdict}]"
        )


def guard_reuse(chains: Sequence[Chain], *, ceiling: int) -> ReuseReport:
    """Refuse to price a set whose components are reused past the declared ceiling.

    A component appearing in many composites makes the per-item accuracies the product
    bound multiplies non-exchangeable, so the bound over-counts. ``ceiling`` has no
    default on purpose: how much reuse is tolerable depends on how the bound will be read,
    so the caller has to say (LINK-ALL-0006).

    Raises :class:`ReuseCeilingExceeded` rather than returning a bound nobody should
    quote.
    """
    report = ReuseReport(ceiling=ceiling, multiplicity=reuse_multiplicity(chains))
    if report.exceeds_ceiling:
        item, count = report.worst
        raise ReuseCeilingExceeded(
            f"{_R_REUSE}: component {item!r} appears in {count} of {len(list(chains))} "
            f"composites, above the declared reuse ceiling of {ceiling}. The independence "
            f"product bound over-counts on a set this correlated; raise the ceiling "
            f"deliberately or emit a less reused set."
        )
    return report


def product_prediction(
    archive: Archive, system: str, components: Sequence[str]
) -> float | None:
    """The independence prediction for one system on one chain (BOUND-ALL-0001).

    ``None`` when any component is missing from the archive: a bound computed over the
    components that happen to be present would silently be a bound for a different, easier
    composite.
    """
    product = 1.0
    for item in components:
        rate = archive.rate(system, item)
        if rate is None:
            return None
        product *= rate
    return product


def max_prediction(archive: Archive, system: str, components: Sequence[str]) -> float | None:
    """The competing hypothesis: accuracy tracks the *easiest* component, not the product.

    If measured composite accuracy sits near this rather than near the product, the chain
    did not bind and the restored headroom is headroom on a different measurand.
    """
    rates = [archive.rate(system, item) for item in components]
    if any(r is None for r in rates):
        return None
    return max(r for r in rates if r is not None)


def noise_band(archive: Archive, *, seed: int = 0, iters: int = 2000) -> float | None:
    """The replicate noise band, derived from the archive's own draws (BOUND-ALL-0002).

    For every (system, item) cell the per-draw verdicts are bootstrapped to a 95% interval
    for that cell's rate; the band is the mean half-width over cells. It is not a chosen
    constant, and an archive with k = 1 supports no band at all -- in which case this
    returns ``None`` and nonius refuses to quarantine rather than inventing one.

    **This estimator is biased toward zero, and the bias is not conservative.** A cell
    whose draws are unanimous has zero sample variance, so ``ci95_bootstrap`` returns a
    point interval and the cell contributes a structural 0.0 to the mean. On a saturated
    archive most cells are unanimous -- 315 of 400 on the reference asset -- so the band is
    dominated by zeros that record "the resampler saw no variation", not "this cell has no
    uncertainty". k identical draws is weak evidence of zero variance and the bootstrap
    cannot express uncertainty it never observed; an interval that can, such as Wilson,
    gives a materially wider band on the same data.

    The direction matters because quarantine fires on ``observed - predicted > band``: a
    band biased small quarantines *more*, and the quarantine rate is what the pre-registered
    ceiling is read against. Use :func:`unanimous_fraction` to report how much of the band
    is structural zeros, and say so next to the number.
    """
    if archive.k() < 2:
        return None
    halves: list[float] = []
    for system in archive.systems:
        for item in archive.items:
            draws = [
                float(v.correct)
                for v in archive.verdicts
                if v.system == system and v.item == item
            ]
            if len(draws) > 1:
                lo, hi = ci95_bootstrap(draws, iters=iters, seed=seed)
                halves.append((hi - lo) / 2.0)
    return mean(halves) if halves else None


def unanimous_fraction(archive: Archive) -> float | None:
    """Share of (system, item) cells whose draws are unanimous.

    How much of :func:`noise_band` is structural zeros rather than measured spread. A band
    reported without it looks like an estimate of replicate noise; at 0.79 it is mostly a
    statement that a saturated archive stopped varying (BOUND-ALL-0002, AUDIT-ALL-0004).
    """
    cells = 0
    unanimous = 0
    for system in archive.systems:
        for item in archive.items:
            draws = [
                v.correct for v in archive.verdicts if v.system == system and v.item == item
            ]
            if len(draws) > 1:
                cells += 1
                if len(set(draws)) == 1:
                    unanimous += 1
    return unanimous / cells if cells else None


@dataclass(frozen=True, slots=True)
class CompositeBound:
    """One composite's prediction, its measurement, and the resulting verdict."""

    composite: str
    system: str
    components: tuple[str, ...]
    predicted: float | None
    predicted_max: float | None
    measured: float | None
    band: float | None
    quarantined: bool
    reason: str


def assess(
    composite_id: str,
    chain: Chain,
    archive: Archive,
    *,
    measured: dict[str, float] | None = None,
    band: float | None = None,
) -> tuple[CompositeBound, ...]:
    """Assess one composite against the bound, for every system in the archive.

    ``measured`` is the observed composite accuracy per system. Without it the assessment
    is a prediction only and nothing is quarantined -- a prediction cannot exceed itself.
    """
    # Computed once, not per system: k() is O(systems x items x verdicts), and the
    # message must describe the archive rather than assume why the band is missing.
    no_band_reason = ""
    if band is None:
        k = archive.k()
        no_band_reason = (
            f"no noise band supplied; the archive supports none (k={k} < 2), so no quarantine"
            if k < 2
            else f"no noise band supplied (the archive would support one at k={k}), "
            f"so no quarantine"
        )

    out: list[CompositeBound] = []
    for system in archive.systems:
        predicted = product_prediction(archive, system, chain.components)
        pmax = max_prediction(archive, system, chain.components)
        obs = (measured or {}).get(system)

        quarantined = False
        if obs is None:
            reason = "prediction only; no measurement supplied"
        elif predicted is None:
            reason = "no prediction; a component is missing from the archive"
        elif band is None:
            reason = no_band_reason
        elif obs - predicted > band:
            quarantined = True
            reason = (
                f"measured {obs:.4f} exceeds product {predicted:.4f} by "
                f"{obs - predicted:.4f} > band {band:.4f}: the chain did not bind"
            )
        else:
            reason = f"within band ({obs - predicted:+.4f}, band {band:.4f})"

        out.append(
            CompositeBound(
                composite=composite_id,
                system=system,
                components=chain.components,
                predicted=predicted,
                predicted_max=pmax,
                measured=obs,
                band=band,
                quarantined=quarantined,
                reason=reason,
            )
        )
    return tuple(out)


@dataclass(frozen=True, slots=True)
class QuarantineReport:
    """The quarantine rate, always shown against the ceiling declared beforehand."""

    depth: int
    assessed: int
    quarantined: int
    ceiling: float
    band: float | None

    @property
    def rate(self) -> float:
        return self.quarantined / self.assessed if self.assessed else 0.0

    @property
    def exceeds_ceiling(self) -> bool:
        """Whether the observed rate is over the ceiling. False when nothing was assessed.

        Read it with :attr:`assessed`: a depth where nothing could be assessed has a rate
        of 0.0 and so is not "over", but it is not a pass either. :meth:`line` says which.
        """
        return self.rate > self.ceiling

    def line(self) -> str:
        band = "n/a" if self.band is None else f"{self.band:.4f}"
        if not self.assessed:
            # Never print "within ceiling" for a depth nothing was measured at: an
            # unassessed depth looks exactly like a clean one otherwise. Name the
            # missing input rather than guessing -- summarize() requires all three, so
            # a depth that had measurements and predictions but no band lands here too,
            # and blaming the measurement would be false about its own data.
            cause = (
                "no noise band was available, so no composite could be assessed"
                if self.band is None
                else "no composite carried both a measurement and a prediction"
            )
            return (
                f"depth {self.depth}: NOT ASSESSED -- {cause}, so the "
                f"{self.ceiling:.4f} ceiling says nothing here. Band {band}."
            )
        verdict = "OVER CEILING" if self.exceeds_ceiling else "within ceiling"
        return (
            f"depth {self.depth}: quarantined {self.quarantined}/{self.assessed} "
            f"= {self.rate:.4f} against declared ceiling {self.ceiling:.4f} "
            f"[{verdict}], band {band}"
        )


def summarize(
    bounds: Sequence[CompositeBound], *, depth: int, ceiling: float
) -> QuarantineReport:
    """Aggregate per-composite verdicts. ``ceiling`` is required (BOUND-ALL-0004)."""
    # A composite the rule could not be applied to is not an assessed one. Without the
    # band requirement a depth where quarantine was impossible reports rate 0.0, which
    # reads as a clean pass.
    assessed = [
        b
        for b in bounds
        if b.measured is not None and b.predicted is not None and b.band is not None
    ]
    return QuarantineReport(
        depth=depth,
        assessed=len(assessed),
        quarantined=sum(1 for b in assessed if b.quarantined),
        ceiling=ceiling,
        band=next((b.band for b in bounds if b.band is not None), None),
    )
