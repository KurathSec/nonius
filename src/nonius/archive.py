"""The per-item verdict archive (ARCHITECTURE.md section 7).

``(system, item, draw, verdict)`` -- what each system answered, per replicate, on each
singleton item. Optional: nonius composes without it. Supplying one buys three things,
and none of them is the gold:

* difficulty strata, so composites can be built from items of a chosen difficulty;
* the independence product prediction each composite is read against (BOUND-ALL-0001);
* the replicate noise band that decides quarantine (BOUND-ALL-0002).

The archive never decides whether an answer is correct. Correctness comes from the
composed gold and nothing else.
"""

from __future__ import annotations

import csv
import gzip
import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from nonius.errors import ManifestError
from nonius.stats import mean, stdev


@dataclass(frozen=True, slots=True)
class Verdict:
    """One system's one draw on one item. ``correct`` is 1 or 0, never a score."""

    system: str
    item: str
    draw: int
    correct: int


@dataclass(frozen=True, slots=True)
class Archive:
    """Per-item, per-draw verdicts for one or more systems."""

    verdicts: tuple[Verdict, ...]

    @property
    def systems(self) -> tuple[str, ...]:
        return tuple(sorted({v.system for v in self.verdicts}))

    @property
    def items(self) -> tuple[str, ...]:
        return tuple(sorted({v.item for v in self.verdicts}))

    def k(self) -> int:
        """The replicate count, or 0 when systems disagree about it.

        A ragged archive is reported rather than averaged over: the noise band depends on
        k, and quietly using a mean k would put a made-up number under the quarantine rule.
        """
        counts = {
            len([v for v in self.verdicts if v.system == s and v.item == i])
            for s in self.systems
            for i in self.items
        }
        counts.discard(0)
        return counts.pop() if len(counts) == 1 else 0

    def rate(self, system: str, item: str) -> float | None:
        """Pass rate of ``system`` on ``item``; ``None`` when the pair is absent."""
        draws = [v.correct for v in self.verdicts if v.system == system and v.item == item]
        return mean([float(x) for x in draws]) if draws else None

    def rates(self) -> dict[tuple[str, str], float]:
        acc: dict[tuple[str, str], list[float]] = {}
        for v in self.verdicts:
            acc.setdefault((v.system, v.item), []).append(float(v.correct))
        return {key: mean(vals) for key, vals in sorted(acc.items())}

    def per_item(self, item: str) -> dict[str, float]:
        return {
            s: r for s, r in ((s, self.rate(s, item)) for s in self.systems) if r is not None
        }

    def stratum(self, item: str) -> str:
        """A coarse, reportable difficulty label from the systems' own verdicts.

        ``dead``          every system perfect -- the saturation the family is about;
        ``floored``       every system at zero;
        ``discriminating``systems disagree;
        ``uniform-partial`` systems agree on a rate that is neither 0 nor 1;
        ``unknown``       the item is not in the archive.

        This is a description of the *systems that produced the archive*, not a property
        of the item, and it is circular with any claim about which stratum recovers the
        most resolution. See docs/honesty.md.
        """
        per = self.per_item(item)
        if not per:
            return "unknown"
        vals = set(per.values())
        if vals == {1.0}:
            return "dead"
        if vals == {0.0}:
            return "floored"
        if len(vals) > 1:
            return "discriminating"
        return "uniform-partial"

    def replicate_spread(self) -> float:
        """Dispersion of per-draw verdicts within (system, item) cells.

        The raw material for the noise band (BOUND-ALL-0002): how much a rate moves for
        reasons that are not the item.
        """
        spreads: list[float] = []
        for s in self.systems:
            for i in self.items:
                draws = [float(v.correct) for v in self.verdicts if v.system == s and v.item == i]
                if len(draws) > 1:
                    spreads.append(stdev(draws))
        return mean(spreads)


def from_records(records: Iterable[Mapping[str, object]]) -> Archive:
    out: list[Verdict] = []
    for n, rec in enumerate(records):
        try:
            out.append(
                Verdict(
                    system=str(rec["system"]),
                    item=str(rec["item"]),
                    draw=int(rec["draw"]),  # type: ignore[call-overload]
                    correct=1 if int(rec["correct"]) else 0,  # type: ignore[call-overload]
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ManifestError(f"archive record {n}: {exc}") from exc
    return Archive(tuple(out))


def _open(path: Path) -> Iterator[str]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            yield from fh
    else:
        with path.open(encoding="utf-8") as fh:
            yield from fh


def load(path: str | Path) -> Archive:
    """Read a ``(system, item, draw, correct)`` archive from JSONL(.gz) or CSV.

    The plain four-column form is the fallback every harness can produce. Native readers
    for richer layouts belong in adapters, not here.
    """
    p = Path(path)
    if p.suffix in {".csv", ".tsv"}:
        with p.open(encoding="utf-8", newline="") as fh:
            return from_records(list(csv.DictReader(fh)))
    return from_records(
        json.loads(line) for line in _open(p) if line.strip() and not line.startswith("#")
    )


def dumps(archive: Archive) -> str:
    return "".join(
        json.dumps(
            {"system": v.system, "item": v.item, "draw": v.draw, "correct": v.correct},
            sort_keys=True,
        )
        + "\n"
        for v in archive.verdicts
    )


def singleton_rates(archive: Archive, items: Sequence[str]) -> dict[str, dict[str, float]]:
    """``{system: {item: rate}}`` restricted to ``items``, for the bridge table."""
    return {
        s: {i: r for i in items if (r := archive.rate(s, i)) is not None}
        for s in archive.systems
    }
