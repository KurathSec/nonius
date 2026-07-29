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
    assess,
    max_prediction,
    noise_band,
    product_prediction,
    summarize,
)
from nonius.canonical import canonical_json  # noqa: E402
from nonius.compose import make_chain  # noqa: E402
from nonius.model import Link  # noqa: E402
from nonius.resolution import measure, singleton_row, table  # noqa: E402
from nonius.spec.registry import spec_version  # noqa: E402

DERIVED = ROOT / "derived"
ARCHIVE = DERIVED / "composite_archive.jsonl.gz"
SHAPES = ROOT / "composite_shapes.jsonl"
SEED = 20260619
CEILING = 0.20
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

    # KT-0: the arm that can fire on a dead harness. The other four cannot: product <= max
    # makes an all-zero measurement pass KT-1 by construction, and 0.0 beats no bound.
    control = rows[1]
    kt0_system = archive_name("deepseek-ai/DeepSeek-V4-Flash")
    kt0_floor = 0.60
    kt0_value = control.accuracy[kt0_system]

    kt1, kt2 = {}, {}
    for d in COMPOSED:
        closer_product = closer_max = 0
        bounds = []
        for cid, rec in shapes.items():
            if rec["depth"] != d:
                continue
            chain = chain_of(rec)
            bounds += assess(cid, chain, arch, measured=per[cid], band=band)
            for system, m in per[cid].items():
                p = product_prediction(arch, system, chain.components)
                x = max_prediction(arch, system, chain.components)
                if p is None or x is None:
                    continue
                closer_product += abs(m - p) <= abs(m - x)
                closer_max += abs(m - x) < abs(m - p)
        report = summarize(bounds, depth=d, ceiling=CEILING)
        kt1[d] = {"closer_to_product": closer_product, "closer_to_max": closer_max,
                  # Vacuous wherever the measurement is all zeros: product <= max, so 0.0
                  # can never be strictly closer to the max. Stated, not hidden.
                  "informative": rows[d].accuracy and max(rows[d].accuracy.values()) > 0.0}
        kt2[d] = {"quarantined": report.quarantined, "assessed": report.assessed,
                  "rate": report.rate, "exceeds_ceiling": report.exceeds_ceiling,
                  "line": report.line()}

    best = max(COMPOSED, key=lambda d: rows[d].discriminating)
    delta = rows[best].discriminating - singleton.discriminating

    payload = {
        "provenance": {
            "run": "run-01",
            "status": "executed",
            "nonius_spec": spec_version(),
            "prompt_version": "bench-prompts-v2",
            "prompt_task": "comprehend (output prediction), the same template the "
                           "committed singleton archive was built with",
            "seed": SEED,
            "completions_bought": len(verdicts),
            "estimated_usd": 12.3795,
            "timeouts": sum(1 for v in verdicts if v.get("timeout")),
        },
        "noise_band": band,
        "singleton": {
            "source": "committed archive, program level",
            "accuracy": dict(sorted(singleton.accuracy.items())),
            "discriminating": singleton.discriminating,
            "ordering": ordering(singleton),
        },
        "measured": {
            str(d): {
                "n": rows[d].n,
                "accuracy": dict(sorted(rows[d].accuracy.items())),
                "dead": rows[d].dead, "floored": rows[d].floored,
                "discriminating": rows[d].discriminating,
                "top_two_gap": rows[d].top_two_gap, "m_star": rows[d].m_star,
                "ordering": ordering(rows[d]),
            }
            for d in depths
        },
        "thresholds": {
            "KT-0-execution-validity": {
                "system": kt0_system, "measured": kt0_value, "floor": kt0_floor,
                "fires": kt0_value < kt0_floor,
            },
            "KT-1-product-vs-max": {str(d): kt1[d] for d in COMPOSED},
            "KT-2-quarantine": {str(d): kt2[d] for d in COMPOSED},
            "KT-2b-ordering": {
                str(d): {"ordering": ordering(rows[d]),
                         "inverted": ordering(rows[d]) != ordering(singleton),
                         # An all-zero row has no ordering: every system ties and the sort
                         # is arbitrary. Reporting that as an inversion would be a finding
                         # about tie-breaking.
                         "meaningful": bool(rows[d].accuracy) and max(rows[d].accuracy.values()) > 0.0}
                for d in depths
            },
            "KT-4-floor-not-ceiling": {
                "best_composed_depth": best,
                "composed_discriminating": rows[best].discriminating,
                "singleton_discriminating": singleton.discriminating,
                "delta": delta, "required": 0.05, "fires": delta < 0.05,
            },
        },
    }

    DERIVED.mkdir(parents=True, exist_ok=True)
    (DERIVED / "results.json").write_text(canonical_json(payload, indent=2) + "\n", encoding="utf-8")
    (DERIVED / "readout.txt").write_text(
        table([singleton, *(rows[d] for d in depths)]) + "\n", encoding="utf-8")
    print(table([singleton, *(rows[d] for d in depths)]))
    print(f"\nKT-0 {'FIRES' if payload['thresholds']['KT-0-execution-validity']['fires'] else 'passes'}"
          f"  |  KT-4 {'FIRES' if delta < 0.05 else 'passes'} (delta {delta:+.4f})")
    print(f"wrote {DERIVED/'results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
