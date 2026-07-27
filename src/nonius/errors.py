"""The error taxonomy (ARCHITECTURE.md section 5).

One base class, and nothing outside this module's exports escapes the public facade.
Every subclass names the ruling it enforces, so a traceback points at the spec rather
than at an implementation detail.
"""

from __future__ import annotations


class NoniusError(Exception):
    """Base for every error nonius raises deliberately."""


class SpecError(NoniusError):
    """The rulings registry is inconsistent, or code cites a ruling that does not exist."""


class ManifestError(NoniusError):
    """An item manifest is malformed or violates a declared invariant (CORE-ALL-0003)."""


class OracleError(NoniusError):
    """The practitioner-supplied oracle failed, or returned something unusable."""


class LinkError(NoniusError):
    """A proposed link is not admissible (LINK-ALL-0001 .. LINK-ALL-0005)."""


class CompositionError(NoniusError):
    """A composite could not be built, or failed a by-construction check at emit time."""


class GoldDisagreementError(CompositionError):
    """The merged program's gold disagrees with the chained component oracles (EMIT-ALL-0002).

    This is the load-bearing check. Two independent computations of the same answer
    disagreeing means the composite is not a deterministic function of its component
    golds, which is the one property the whole instrument rests on.
    """


class LiteralLeakError(CompositionError):
    """A substituted slot survived as a literal in the rendering (EMIT-ALL-0001).

    A composite whose upstream answer is printed in the downstream's source is not a
    chain: the model can read the value instead of computing it. Such an item would
    beat its own product bound and be quarantined, so it is refused at emit time.
    """
