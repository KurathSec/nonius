"""nonius -- compose a benchmark's own items, and audit whether that is even possible.

A saturated benchmark is kept because every historical comparison was computed against
it, so switching costs comparability and staying costs signal. nonius takes the items you
already have plus the callable oracle they already carry, and emits depth-graded
composites whose gold is a deterministic function of the component golds -- no examiner,
no new items, no model calls.

It also refuses. Most benchmarks cannot be composed, and the free audit says so before
anything is spent: ``nonius audit`` reports which items can start a chain, which can
continue one, how deep the link graph actually goes, and what resolution composition
would buy on the population it can really build.
"""

from __future__ import annotations

from nonius._version import __version__
from nonius.bound import ReuseCeilingExceeded, ReuseReport, guard_reuse
from nonius.compose import (
    LinkAnalysis,
    LinkVerdict,
    analyze,
    chained_gold,
    composite_id,
    enumerate_fanins,
    enumerate_paths,
    make_chain,
    realize,
    reuse_multiplicity,
    singleton,
)
from nonius.errors import (
    CompositionError,
    GoldDisagreementError,
    LinkError,
    LiteralLeakError,
    ManifestError,
    NoniusError,
    OracleError,
    SpecError,
)
from nonius.model import (
    Candidate,
    Chain,
    Composite,
    Diagnostic,
    Item,
    Link,
    Realization,
    ResultVar,
    Scalar,
    Slot,
    tag_of,
)
from nonius.oracle import Oracle, Realizer
from nonius.realize import make_prompt_realizer
from nonius.spec.registry import all_rulings, get, spec_version

__all__ = [
    "Candidate",
    "Chain",
    "Composite",
    "CompositionError",
    "Diagnostic",
    "GoldDisagreementError",
    "Item",
    "Link",
    "LinkAnalysis",
    "LinkError",
    "LinkVerdict",
    "LiteralLeakError",
    "ManifestError",
    "NoniusError",
    "Oracle",
    "OracleError",
    "Realization",
    "Realizer",
    "ResultVar",
    "ReuseCeilingExceeded",
    "ReuseReport",
    "Scalar",
    "Slot",
    "SpecError",
    "__version__",
    "all_rulings",
    "analyze",
    "chained_gold",
    "composite_id",
    "enumerate_fanins",
    "enumerate_paths",
    "get",
    "guard_reuse",
    "make_chain",
    "make_prompt_realizer",
    "realize",
    "reuse_multiplicity",
    "singleton",
    "spec_version",
    "tag_of",
]
