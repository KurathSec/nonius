#!/usr/bin/env python3
"""The second reference audit: nonius pointed at HumanEval+.

The subject nonius's author did not build. EvalPlus supplies the items, the contracts, the
canonical solutions and the oracle; this project claims none of them. See ../../NOTICE.

Deterministic and timestamp-free, like the first audit, so re-running on the same inputs
gives byte-identical files and no number in the prose can drift from the artifact.

    NONIUS_EVALPLUS_DATA=/path/to/HumanEvalPlus.jsonl.gz python validation/evalplus_audit/run.py

The dataset is NOT vendored. A missing file is a hard error rather than a silent skip.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent.parent / "src"))

from nonius.adapters import evalplus as ep  # noqa: E402
from nonius.canonical import canonical_json  # noqa: E402
from nonius.compose import analyze, make_chain, realize  # noqa: E402
from nonius.manifest import index  # noqa: E402
from nonius.model import Link  # noqa: E402
from nonius.spec.registry import spec_version  # noqa: E402

DERIVED = ROOT / "derived"


def main() -> int:
    items = ep.items()
    analysis = analyze(items, ep.oracle)

    candidates = len(analysis.candidates)
    live = len(analysis.live)
    reasons = Counter(v.reason for v in analysis.verdicts if not v.live)

    # The distinction the headline turns on. A link refused because its upstream result has
    # no probe set was never DECIDED; a link refused because the downstream answer is
    # constant over the codomain was decided and found dead. Reporting them as one number
    # would let an absent probe set read as evidence about the benchmark's structure.
    unprobeable = sum(n for r, n in reasons.items() if "no probe set" in r or "empty codomain" in r)
    decided = candidates - unprobeable
    dead = decided - live

    # A live link is not an emittable composite on this subject. Liveness asks whether the
    # downstream answer varies over the upstream codomain; emission additionally requires
    # the downstream CONTRACT to accept the piped value, and EvalPlus's contracts are the
    # only domain declaration these items have. Reporting liveness alone would overstate
    # what can actually be built, so the audit measures both and says so.
    idx = index(items)
    realizer = ep.make_realizer()
    emittable = refused = 0
    reasons: Counter[str] = Counter()
    for cand in analysis.live:
        chain = make_chain((cand.upstream_item, cand.downstream_item),
                           [Link(0, cand.result, 1, cand.slot, cand.tag)])
        try:
            realize(chain, idx, ep.oracle, realizer)
            emittable += 1
        except Exception as exc:  # noqa: BLE001 - the refusal is the measurement
            refused += 1
            reasons[type(exc).__name__] += 1

    payload = {
        "provenance": {
            "subject": "EvalPlus HumanEval+",
            "subject_role": "instrument and input; claimed as neither",
            "subject_data": Path(ep.data_path()).name,
            "subject_upstream": "https://github.com/evalplus/evalplus",
            "nonius_spec": spec_version(),
            "access": "read-only; dataset not vendored",
        },
        "manifest": {
            "items": len(items),
            "excluded": {
                "nondeterministic": sorted(ep.NONDETERMINISTIC),
                "property_oracle": sorted(ep.PROPERTY_ORACLE),
                "note": "further items are absent because their signature is not plain "
                        "positional, or their result is not a scalar nonius can pipe",
            },
            "families_declared": sorted({i.family for i in items}),
            "family_note": "HumanEval ships no topic label. Any stratum here would be "
                           "adapter-invented, so none is declared.",
            "result_tags": dict(sorted(Counter(i.results[0].tag for i in items).items())),
            "slot_tags": dict(sorted(Counter(s.tag for i in items for s in i.slots).items())),
        },
        "links": {
            "candidate_links": candidates,
            "unprobeable_links": unprobeable,
            "decided_links": decided,
            "live_links": live,
            "dead_links": dead,
            "live_share_of_decided": live / decided if decided else None,
            "dead_share_of_decided": dead / decided if decided else None,
            "live_pairs": len(analysis.live_pairs()),
            "ordered_pairs": len(items) * (len(items) - 1),
            "refusal_reasons": dict(sorted(reasons.items())),
        },
        "emission": {
            "note": "A live link still needs the downstream contract to accept the piped "
                    "value. Liveness is necessary and not sufficient here, exactly as type "
                    "compatibility is necessary and not sufficient for liveness.",
            "live_links": live,
            "emittable_composites": emittable,
            "refused_at_realization": refused,
            "emittable_share_of_live": emittable / live if live else None,
            "refusal_kinds": dict(sorted(reasons.items())),
        },
        "caps": dict(analysis.caps),
    }

    DERIVED.mkdir(parents=True, exist_ok=True)
    (DERIVED / "audit.json").write_text(canonical_json(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {DERIVED / 'audit.json'}")
    print(f"  items {len(items)} | candidates {candidates} | unprobeable {unprobeable} "
          f"| decided {decided} | live {live} | dead {dead}")
    print(f"  emittable {emittable} of {live} live ({emittable/live:.1%}); "
          f"{refused} refused at realization")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
