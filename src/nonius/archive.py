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
from dataclasses import dataclass, field
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
    #: Memo for :meth:`_cells`, excluded from equality, hashing and repr because it is
    #: derived: two archives with the same verdicts are the same archive whether or not
    #: either has been indexed.
    _cells_memo: dict[tuple[str, str], list[int]] | None = field(
        default=None, init=False, compare=False, repr=False
    )

    def _cells(self) -> dict[tuple[str, str], list[int]]:
        """``(system, item) -> the draws``, built once and reused.

        Every accessor below used to scan ``verdicts`` in full. That is invisible on a
        small archive and quadratic on a real one: ``product_prediction`` asks for one rate
        per system per component, so a depth-5 audit over ten thousand chains made 300000
        scans of a 195400-row archive, which is 5.9e10 comparisons and does not finish.
        ``k()`` was worse still, scanning once per (system, item) pair.

        The memo is written through ``object.__setattr__`` because the dataclass is frozen.
        That is sound here and would not be in general: the value is a pure function of
        ``verdicts``, which cannot change, so no caller can observe a difference beyond the
        time it took. Nothing derived from it depends on insertion order.
        """
        cached = self._cells_memo
        if cached is None:
            cached = {}
            for v in self.verdicts:
                cached.setdefault((v.system, v.item), []).append(v.correct)
            object.__setattr__(self, "_cells_memo", cached)
        return cached

    @property
    def systems(self) -> tuple[str, ...]:
        return tuple(sorted({s for s, _ in self._cells()}))

    @property
    def items(self) -> tuple[str, ...]:
        return tuple(sorted({i for _, i in self._cells()}))

    def k(self) -> int:
        """The replicate count, or 0 when systems disagree about it.

        A ragged archive is reported rather than averaged over: the noise band depends on
        k, and quietly using a mean k would put a made-up number under the quarantine rule.
        """
        cells = self._cells()
        counts = {
            len(cells.get((s, i), ())) for s in self.systems for i in self.items
        }
        counts.discard(0)
        return counts.pop() if len(counts) == 1 else 0

    def rate(self, system: str, item: str) -> float | None:
        """Pass rate of ``system`` on ``item``; ``None`` when the pair is absent."""
        draws = self._cells().get((system, item))
        return mean([float(x) for x in draws]) if draws else None

    def rates(self) -> dict[tuple[str, str], float]:
        return {
            key: mean([float(x) for x in vals])
            for key, vals in sorted(self._cells().items())
        }

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
        ``unknown``       the item is missing for at least one system.

        This is a description of the *systems that produced the archive*, not a property
        of the item, and it is circular with any claim about which stratum recovers the
        most resolution. See docs/honesty.md.
        """
        per = self.per_item(item)
        # "every system" must mean every system in the archive, not every system that
        # happened to attempt this item: otherwise an item one system never saw can be
        # labelled `dead` on the strength of the others. An empty archive has no systems,
        # so `0 < 0` would fall through and label everything `uniform-partial`.
        if not per or len(per) < len(self.systems):
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
    seen: set[tuple[str, str, int]] = set()
    for n, rec in enumerate(records):
        try:
            raw = rec["correct"]
            # A verdict is 1 or 0, never a score. Coercing anything int()-able would let a
            # harness that emits partial credit load silently, with every value below 1.0
            # floored to a failure -- corrupting strata, product predictions and the band
            # with no diagnostic anywhere.
            if raw not in (0, 1, True, False, "0", "1"):
                raise ValueError(
                    f"'correct' must be 0 or 1, got {raw!r}; a verdict is a verdict, "
                    f"not a score"
                )
            verdict = Verdict(
                system=str(rec["system"]),
                item=str(rec["item"]),
                draw=int(rec["draw"]),  # type: ignore[call-overload]
                correct=1 if int(raw) else 0,
            )
            key = (verdict.system, verdict.item, verdict.draw)
            if key in seen:
                # `draw` is the replicate index and `k()` is the row count per cell, so a
                # double-loaded archive would silently inflate k and re-weight every rate.
                raise ValueError(
                    f"duplicate (system, item, draw) {key}; each replicate appears once"
                )
            seen.add(key)
            out.append(verdict)
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
    """Read a ``(system, item, draw, correct)`` archive from JSONL(.gz), CSV or TSV.

    The plain four-column form is the fallback every harness can produce. Native readers
    for richer layouts belong in adapters, not here.
    """
    archive = _load(path)
    if not archive.verdicts:
        # An empty archive is indistinguishable downstream from "no archive supplied", and
        # every statistic derived from it is vacuously clean. A header-only CSV, an empty
        # file, or a CSV whose header row is missing (DictReader eats the first data row
        # as the header) all land here, and silence would report them as a result.
        raise ManifestError(
            f"{path}: no verdicts read. An archive with no rows cannot support strata, a "
            f"product prediction or a noise band. Check the file is non-empty and that a "
            f"CSV/TSV carries a `system,item,draw,correct` header row."
        )
    return archive


def _load(path: str | Path) -> Archive:
    p = Path(path)
    if p.suffix in {".csv", ".tsv"}:
        # utf-8-sig, a no-op without a BOM: with one, the first header cell becomes
        # "﻿system" and every row fails with an opaque missing-key error that names
        # the wrong problem.
        with p.open(encoding="utf-8-sig", newline="") as fh:
            delimiter = "\t" if p.suffix == ".tsv" else ","
            return from_records(list(csv.DictReader(fh, delimiter=delimiter)))
    return from_records(_jsonl(p))


def _jsonl(p: Path) -> Iterator[Mapping[str, object]]:
    """Parse a JSONL archive, naming the line that failed.

    The decode has to happen inside a generator that from_records consumes, so the guard
    belongs here: from_records' own try block starts inside its loop body, which means a
    JSONDecodeError raised by the generator's ``next()`` escaped it entirely and reached
    the CLI as a traceback.
    """
    for n, line in enumerate(_open(p), start=1):
        if not line.strip() or line.startswith("#"):
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ManifestError(f"{p} line {n}: {exc}") from exc
        if not isinstance(record, dict):
            raise ManifestError(
                f"{p} line {n}: each line must be an object, got {type(record).__name__}"
            )
        yield record


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
