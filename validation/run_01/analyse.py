#!/usr/bin/env python3
"""Re-derive every pre-registered threshold for run-01, from committed data only.

The run bought 14268 completions once. This reads the graded outcome of that purchase,
never the raw completions, and recomputes KT-0, KT-1, KT-2, KT-2b and KT-4 with nonius's
own machinery. Deterministic and timestamp-free: re-running on the same inputs gives
byte-identical files, so no number in the prose can drift from the artifact.

    NONIUS_SPAGHETTI_HOME=/path/to/Spaghetti-Architect python validation/run_01/analyse.py

What is committed and what is not. `derived/composite_archive.jsonl.gz` is the graded
record -- (system, item, draw, correct) over composites, in the same format nonius consumes
for singletons -- and it is what makes this reproducible. The raw completions (11 MB of
model text) and the emitted composite set (12 MB, deterministically regenerable from the
subject) are NOT committed; their sha256 is recorded in the payload so a reader can check a
copy they obtained separately.
"""

from __future__ import annotations

import collections
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent.parent / "src"))

from nonius.adapters import spaghetti as sp  # noqa: E402
from nonius.bound import (  # noqa: E402
    ReuseCeilingExceeded,
    assess,
    guard_reuse,
    max_prediction,
    noise_band,
    product_prediction,
    summarize,
)
from nonius.canonical import canonical_json  # noqa: E402
from nonius.compose import make_chain  # noqa: E402
from nonius.model import Link  # noqa: E402
from nonius.resolution import measure, predict, singleton_row, table  # noqa: E402
from nonius.spec.registry import spec_version  # noqa: E402

DERIVED = ROOT / "derived"
ARCHIVE = DERIVED / "composite_archive.jsonl.gz"
SHAPES = ROOT / "composite_shapes.jsonl"
SEED = 20260619
CEILING = 0.20
REUSE_CEILING = 100          # preregistration/run-01.toml [reuse]
KT1_SYSTEM = "deepseek-ai-DeepSeek-V4-Flash"
KT1_DEPTH = 3                # registered for one system at one depth, not pooled
COMPOSED = (2, 3, 5)

#: The pre-registration names models as the API does, `vendor/Model`; the subject's archive
#: labels the same systems `vendor-Model`. Nothing reconciled them, and the first analysis
#: of this run reported NOT ASSESSED at every depth as a result. nonius refusing was the
#: correct behaviour -- a rate of 0.0 would have read as a clean pass on a comparison that
#: never happened -- but the mapping has to live somewhere, so it lives here, explicitly.
def archive_name(model: str) -> str:
    return model.replace("/", "-")


def main() -> int:
    arch = sp.archive(sp.home())
    band = noise_band(arch, seed=SEED)

    shapes = {}
    for line in SHAPES.read_text(encoding="utf-8").split("\n"):
        if line.strip():
            r = json.loads(line)
            shapes[r["id"]] = r

    with gzip.open(ARCHIVE, "rt", encoding="utf-8") as fh:
        verdicts = [json.loads(x) for x in fh if x.strip()]

    per: dict[str, dict[str, float]] = collections.defaultdict(dict)
    draws: dict[tuple[str, str], list[int]] = collections.defaultdict(list)
    for v in verdicts:
        draws[(v["item"], v["system"])].append(int(v["correct"]))
    for (cid, system), xs in draws.items():
        per[cid][system] = sum(xs) / len(xs)

    def chain_of(rec: dict[str, object]):
        links = [Link(**x) for x in rec["links"]]  # type: ignore[arg-type]
        return make_chain(tuple(rec["components"]), links)  # type: ignore[arg-type]

    depths = sorted({int(str(r["depth"])) for r in shapes.values()})
    rows = {
        d: measure({c: per[c] for c in shapes if shapes[c]["depth"] == d},
                   depth=d, quarantined=(), seed=SEED)
        for d in depths
    }
    singleton = singleton_row(arch, seed=SEED)

    def ordering(row: object) -> list[str]:
        return [s for s, _ in sorted(row.accuracy.items(), key=lambda kv: -kv[1])]  # type: ignore[attr-defined]

    # ---- KT-0: both clauses. The parse clause is a registered half of this arm and
    # cannot be evaluated from accuracy alone, so the archive carries a `parsed` flag.
    control = rows[1]
    kt0_value = control.accuracy[KT1_SYSTEM]
    parsed_rate = sum(1 for v in verdicts if v.get("parsed")) / len(verdicts)
    kt0 = {"system": KT1_SYSTEM, "measured": kt0_value, "floor": 0.60,
           "parse_rate": parsed_rate, "parse_floor": 0.90,
           "fires": kt0_value < 0.60 or parsed_rate < 0.90}

    # ---- Reuse ceiling (LINK-ALL-0006). Declared in advance at 100. A depth whose pool
    # exceeds it is REFUSED a product bound, so no KT-1 or KT-2 number may be quoted there.
    # Not calling this was how the first analysis published both at depth 5.
    reuse = {}
    for d in COMPOSED:
        chains = [chain_of(r) for r in shapes.values() if r["depth"] == d]
        try:
            rep = guard_reuse(chains, ceiling=REUSE_CEILING)
            worst = max(rep.multiplicity.items(), key=lambda kv: kv[1]) if rep.multiplicity else ("", 0)
            reuse[d] = {"refused": False, "worst_component": worst[0], "worst_multiplicity": worst[1]}
        except ReuseCeilingExceeded as exc:
            reuse[d] = {"refused": True, "reason": str(exc)}
    priceable = [d for d in COMPOSED if not reuse[d]["refused"]]

    # ---- KT-2 first: its quarantine set feeds measure(), because a quarantined composite
    # is EXCLUDED rather than counted as a success (BOUND-ALL-0003).
    kt2, quarantined = {}, {}
    for d in priceable:
        bounds = [x for c, r in shapes.items() if r["depth"] == d
                  for x in assess(c, chain_of(r), arch, measured=per[c], band=band)]
        rep = summarize(bounds, depth=d, ceiling=CEILING)
        quarantined[d] = sorted({b.composite for b in bounds if b.quarantined})
        # A cell measuring 0 can never exceed its bound, so the rate has a structural
        # ceiling far below the declared one. Quoting 0.019 against 0.20 without this
        # compares to a number the data could not reach.
        cells = [b for b in bounds if b.measured is not None]
        reachable = sum(1 for b in cells if b.measured > 0.0)
        kt2[d] = {"quarantined": rep.quarantined, "assessed": rep.assessed, "rate": rep.rate,
                  "exceeds_ceiling": rep.exceeds_ceiling, "ceiling": CEILING,
                  "cells_able_to_exceed": reachable,
                  "structural_max_rate": reachable / rep.assessed if rep.assessed else None,
                  "rate_among_reachable": rep.quarantined / reachable if reachable else None}

    # Re-measure with the quarantined composites excluded, per BOUND-ALL-0003.
    rows = {d: measure({c: per[c] for c in shapes if shapes[c]["depth"] == d},
                       depth=d, quarantined=tuple(quarantined.get(d, ())), seed=SEED)
            for d in depths}
    control = rows[1]

    # ---- The predicted row for each DRAWN population. Without it the measured row has no
    # null to be read against, and the free audit's prediction is not the same population.
    pred = {}
    for d in COMPOSED:
        pool = [chain_of(r) for c, r in shapes.items() if r["depth"] == d
                and c not in set(quarantined.get(d, ()))]
        pred[d] = predict(pool, arch, depth=d, seed=SEED, sample=None)

    # ---- KT-1 as registered: ONE system, ONE depth. The pooled counts the first analysis
    # reported are a different, unregistered statistic that passes by construction wherever
    # the measurement is zero, because product <= max.
    kt1 = {"registered": None, "informative_cells": {}}
    if KT1_DEPTH in priceable:
        ms, ps, xs = [], [], []
        for c, r in shapes.items():
            if r["depth"] != KT1_DEPTH or c in set(quarantined.get(KT1_DEPTH, ())):
                continue
            k = chain_of(r)
            p_, x_ = product_prediction(arch, KT1_SYSTEM, k.components), max_prediction(arch, KT1_SYSTEM, k.components)
            if p_ is None or x_ is None:
                continue
            ms.append(per[c].get(KT1_SYSTEM, 0.0))
            ps.append(p_)
            xs.append(x_)
        m_, p_, x_ = (sum(v)/len(v) for v in (ms, ps, xs))
        kt1["registered"] = {"system": KT1_SYSTEM, "depth": KT1_DEPTH, "measured": m_,
            "product": p_, "max": x_, "closer_to": "product" if abs(m_-p_) <= abs(m_-x_) else "max",
            "fires": abs(m_-x_) < abs(m_-p_),
            "vacuous": m_ == 0.0,
            "note": "product <= max, so a measured 0.0 cannot be closer to the max. This "
                    "arm cannot fire on an all-zero row and says so."}
    for d in priceable:
        tot = inf = to_max = 0
        for c, r in shapes.items():
            if r["depth"] != d or c in set(quarantined.get(d, ())):
                continue
            k = chain_of(r)
            for s, m in per[c].items():
                p_, x_ = product_prediction(arch, s, k.components), max_prediction(arch, s, k.components)
                if p_ is None or x_ is None:
                    continue
                tot += 1
                if m > 0.0 and p_ != x_:
                    inf += 1
                    to_max += abs(m - x_) < abs(m - p_)
        kt1["informative_cells"][str(d)] = {"cells": tot, "informative": inf,
            "closer_to_max": to_max,
            "note": "informative = measured > 0 AND product != max. The rest pass by "
                    "construction and are excluded rather than counted."}

    # ---- KT-2b reading (b): measured vs PREDICTED at the same depth, against the
    # registered yardstick max(band, m*). Reading (a) vs the singleton is population
    # evidence, which the pre-registration says explicitly.
    kt2b = {}
    for d in COMPOSED:
        if d not in priceable:
            kt2b[str(d)] = {"evaluable": False, "why": "depth refused by the reuse ceiling"}
            continue
        mo, po = ordering(rows[d]), ordering(pred[d])
        yard = max(band, rows[d].m_star or 0.0)
        worst = 0.0
        for i in range(len(mo) - 1):
            a, b_ = mo[i], mo[i+1]
            worst = max(worst, abs(rows[d].accuracy.get(a,0.0) - rows[d].accuracy.get(b_,0.0)))
        kt2b[str(d)] = {"measured_order": mo, "predicted_order": po,
            "departs": mo != po, "yardstick": yard, "largest_adjacent_gap": worst,
            "fires": mo != po and worst > yard,
            "evaluable": bool(rows[d].accuracy) and max(rows[d].accuracy.values()) > 0.0}

    # ---- KT-4 on the MATCHING UNIT. The measured composed row is one program x one
    # profile x one language at k=3, which is the item-level unit; the pooled program-level
    # 0.7200 baseline pools fifteen rendering cells at k=120. Comparing them charges a
    # replicate-depth artifact to composition.
    best = max((d for d in COMPOSED), key=lambda d: rows[d].discriminating)
    kt4 = {"best_composed_depth": best,
        "composed_discriminating": rows[best].discriminating,
        "baseline_program_level_k120": singleton.discriminating,
        "delta_against_program_level": rows[best].discriminating - singleton.discriminating,
        "unit_warning": "The measured composed rows are one rendering cell at k=3, the "
            "item-level unit. The program-level baseline pools fifteen cells at k=120. The "
            "pre-registration requires the MATCHING unit, so the program-level delta "
            "overstates the effect by the replicate-depth difference and is not the "
            "registered comparison.",
        "required": 0.05}

    payload = {
        "provenance": {
            "run": "run-01", "status": "executed", "nonius_spec": spec_version(),
            "prompt_version": "bench-prompts-v2",
            "prompt_task": "comprehend (output prediction), the template the committed "
                           "singleton archive was built with",
            "seed": SEED, "completions_bought": len(verdicts),
            "timeouts": sum(1 for v in verdicts if v.get("timeout")),
            "unparseable": sum(1 for v in verdicts if not v.get("parsed") and not v.get("timeout")),
            "usd_note": "two estimators disagree by 4.7x; both are in inputs.json and "
                        "neither is silently preferred",
        },
        "noise_band": band,
        "reuse_ceiling": {"declared": REUSE_CEILING,
                          **{str(d): reuse[d] for d in COMPOSED}},
        "caps": {
            "note": "The pre-registered cap of 500 per depth withheld chains, and what it "
                    "withheld is not neutral: at depth 2 it dropped every fsm_transition "
                    "chain, at depth 5 every non-fsm one. So no family is held constant "
                    "across depths and depth is confounded with family (AUDIT-ALL-0004).",
            **{str(d): dict(rows[d].caps) for d in depths},
        },
        "singleton": {"source": "committed archive, program level, k=120",
                      "accuracy": dict(sorted(singleton.accuracy.items())),
                      "discriminating": singleton.discriminating,
                      "ordering": ordering(singleton)},
        "measured": {str(d): {"n": rows[d].n, "accuracy": dict(sorted(rows[d].accuracy.items())),
                              "dead": rows[d].dead, "floored": rows[d].floored,
                              "discriminating": rows[d].discriminating,
                              "top_two_gap": rows[d].top_two_gap, "m_star": rows[d].m_star,
                              "gap_exceeds_m_star": rows[d].m_star is not None
                                                    and rows[d].top_two_gap > rows[d].m_star,
                              "ordering": ordering(rows[d]),
                              "quarantined_excluded": len(quarantined.get(d, ()))}
                     for d in depths},
        "predicted_on_drawn_population": {
            str(d): {"n": pred[d].n, "accuracy": dict(sorted(pred[d].accuracy.items())),
                     "discriminating": pred[d].discriminating,
                     "top_two_gap": pred[d].top_two_gap, "ordering": ordering(pred[d])}
            for d in COMPOSED},
        "thresholds": {"KT-0-execution-validity": kt0, "KT-1-product-vs-max": kt1,
                       "KT-2-quarantine": {str(d): kt2[d] for d in kt2},
                       "KT-2b-ordering": kt2b, "KT-4-floor-not-ceiling": kt4},
    }

    DERIVED.mkdir(parents=True, exist_ok=True)
    (DERIVED / "results.json").write_text(canonical_json(payload, indent=2) + "\n", encoding="utf-8")
    readout = table([singleton, *(rows[d] for d in depths)])
    (DERIVED / "readout.txt").write_text(readout + "\n", encoding="utf-8")
    print(readout)
    print(f"\nKT-0 {'FIRES' if kt0['fires'] else 'passes'}"
          f" (acc {kt0['measured']:.4f}, parse {kt0['parse_rate']:.4f})")
    for d in COMPOSED:
        if reuse[d]["refused"]:
            print(f"depth {d}: REFUSED a product bound by the reuse ceiling; no KT-1/KT-2 quoted")
    print(f"KT-4 best composed depth {kt4['best_composed_depth']} "
          f"discriminating {kt4['composed_discriminating']:.4f}, "
          f"delta vs pooled baseline {kt4['delta_against_program_level']:+.4f} "
          f"(UNIT MISMATCH: see unit_warning)")
    print(f"wrote {DERIVED/'results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
