"""The versioned rulings registry (ARCHITECTURE.md section 4).

A ruling is one decision the composer makes, written down, given an immutable ID, and
cited from the code that implements it. The point is not documentation: it is that a
number published under ruling ``LINK-ALL-0007`` means the same thing forever, because
changing what an existing ID means silently rewrites the history of every number ever
published under it. Rulings are superseded by new IDs, never edited into new meanings.

Spec semver is independent of the package version:
  patch = editorial; minor = new rulings, no existing decision changes;
  major = any change that alters a decision for any existing corpus case.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources

from nonius.errors import SpecError

# Enumerated, not globbed: a ruling file that is present but unlisted would load in some
# environments and not others, which is exactly the drift the registry exists to prevent.
_RULING_FILES = (
    "core.toml",
    "depth.toml",
    "link.toml",
    "emit.toml",
    "bound.toml",
    "audit.toml",
)


@dataclass(frozen=True, slots=True)
class Ruling:
    """One immutable decision."""

    id: str
    topic: str
    title: str
    statement: str
    status: str = "active"  # active | draft | superseded
    since_spec: str = "0.1.0"
    #: Calibration-corpus case ids that exercise this ruling. May be empty: a ruling
    #: about a refusal has no value to hand-compute, and is covered instead by a named
    #: test listed in TEST_COVERED (tests/test_spec_coverage.py). What the gate does
    #: require is that every cited case names the ruling back -- a self-attested example
    #: is vacuous -- and that every active ruling is covered one way or the other.
    examples: tuple[str, ...] = ()
    superseded_by: str = ""
    #: Free-text record of why the decision went this way. Carries the evidence.
    rationale: str = ""


@dataclass(frozen=True, slots=True)
class Spec:
    version: str
    rulings: dict[str, Ruling] = field(default_factory=dict)


def _load() -> Spec:
    pkg = resources.files("nonius.spec.rulings")

    index = tomllib.loads((pkg / "index.toml").read_text(encoding="utf-8"))
    version = str(index["spec"]["version"])

    rulings: dict[str, Ruling] = {}
    for fname in _RULING_FILES:
        data = tomllib.loads((pkg / fname).read_text(encoding="utf-8"))
        for raw in data.get("ruling", []):
            rid = str(raw["id"])
            if rid in rulings:
                raise SpecError(f"duplicate ruling id {rid!r} (second occurrence in {fname})")
            rulings[rid] = Ruling(
                id=rid,
                topic=str(raw["topic"]),
                title=str(raw["title"]),
                statement=str(raw["statement"]),
                status=str(raw.get("status", "active")),
                since_spec=str(raw.get("since_spec", "0.1.0")),
                examples=tuple(str(x) for x in raw.get("examples", ())),
                superseded_by=str(raw.get("superseded_by", "")),
                rationale=str(raw.get("rationale", "")),
            )
    return Spec(version=version, rulings=rulings)


@lru_cache(maxsize=1)
def _spec() -> Spec:
    return _load()


def spec_version() -> str:
    """The rulings specification version (not the package version)."""
    return _spec().version


def all_rulings() -> tuple[Ruling, ...]:
    """Every ruling, ordered by id."""
    return tuple(_spec().rulings[k] for k in sorted(_spec().rulings))


def get(ruling_id: str) -> Ruling:
    try:
        return _spec().rulings[ruling_id]
    except KeyError:
        raise SpecError(f"no such ruling: {ruling_id!r}") from None


def require(ruling_id: str) -> str:
    """Assert the ruling exists and is active, and return its id (call at import time).

    This is what stops a citation from rotting into a lie: a comment can drift, an
    import-time assertion cannot. It refuses a *superseded* id as well as a phantom one,
    because binding code to a ruling the spec has already retracted is the subtler and
    more likely mistake -- it is what happens when a decision moves and the citation does
    not follow it.
    """
    ruling = _spec().rulings.get(ruling_id)
    if ruling is None:
        raise SpecError(
            f"code cites phantom ruling {ruling_id!r}; add it to the spec or fix the citation"
        )
    if ruling.status == "superseded":
        raise SpecError(
            f"code cites superseded ruling {ruling_id!r}; it was replaced by "
            f"{ruling.superseded_by!r}. Cite the successor."
        )
    return ruling_id
