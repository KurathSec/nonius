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

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent.parent / "src"))

from nonius.adapters import evalplus as ep  # noqa: E402
from nonius.archive import load as load_archive  # noqa: E402
from nonius.audit import audit  # noqa: E402
from nonius.canonical import canonical_json  # noqa: E402
from nonius.compose import analyze, make_chain, realize  # noqa: E402
from nonius.manifest import index  # noqa: E402
from nonius.model import Link  # noqa: E402
from nonius.spec.registry import spec_version  # noqa: E402
from nonius.stats import mean  # noqa: E402

DERIVED = ROOT / "derived"


ARCHIVE = DERIVED / "singleton_archive.jsonl.gz"
DEPTHS = (1, 2, 3, 5)
SEED = 20260619


def memoized(fn: object) -> object:
    """``ep.oracle`` with a process-local memo, and the reason it is sound to add one.

    Every oracle call is a subprocess, and this script asks for the same ones twice: once
    for the link analysis reported under `links`, and again inside `audit()`, which runs
    its own `analyze()`. Without a memo the second pass re-executes tens of thousands of
    subprocesses to recompute values it already has, and the script takes longer than a
    timeout will wait, which is exactly how the first three attempts died.

    Caching is transparent HERE and would not be in general. `oracle(item, bindings)` is a
    pure function of its arguments only because the adapter excludes the one HumanEval task
    whose canonical solution is nondeterministic (`ep.NONDETERMINISTIC`). Refusals are
    cached alongside values on the same reasoning: a contract rejection is a property of
    the binding, so re-running it cannot produce a gold.
    """
    cache: dict[tuple[str, tuple[tuple[str, object], ...]], tuple[object, Exception | None]] = {}

    def wrapped(item: object, bindings: dict[str, object]) -> object:
        key = (item.id, tuple(sorted(bindings.items())))  # type: ignore[attr-defined]
        if key not in cache:
            try:
                cache[key] = (ep.oracle(item, bindings), None)  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001 - a refusal is cached like a value
                cache[key] = (None, exc)
        value, exc = cache[key]
        if exc is not None:
            raise exc
        return value

    return wrapped


def _difficulty(arch: object) -> dict[str, object]:
    """Strata and the noise band, with the caveat that makes them readable.

    `Archive.stratum` calls an item `dead` when EVERY system is perfect, so the strata are
    a function of WHICH systems the panel holds, not only how many. This panel includes
    gpt-j at pass@1 0.0415, which makes `dead` unreachable: the archive holds zero dead
    items against 18 of 100 on the first subject. That difference is the panel, not the
    benchmark, and any comparison of the two subjects' strata has to carry this sentence.
    """
    if arch is None:
        return {"available": False}
    from collections import Counter

    from nonius.bound import noise_band, unanimous_fraction
    strata = Counter(arch.stratum(i) for i in arch.items)  # type: ignore[attr-defined]
    return {
        "available": True,
        "systems": list(arch.systems),  # type: ignore[attr-defined]
        "items": len(arch.items),  # type: ignore[attr-defined]
        "k": arch.k(),  # type: ignore[attr-defined]
        "strata": dict(sorted(strata.items())),
        "noise_band": noise_band(arch, seed=SEED),  # type: ignore[arg-type]
        "unanimous_cell_fraction": unanimous_fraction(arch),  # type: ignore[arg-type]
        "panel_caveat": "Strata depend on which systems are in the panel. This one holds "
                        "gpt-j at pass@1 0.0415, so `dead` (every system perfect) is "
                        "unreachable and the dead count is 0 against 18/100 on the first "
                        "subject. That gap is the panel rather than the benchmark.",
        "systems_omitted": 17,
        "systems_omitted_note": "23 systems were released; 6 were graded. A subset is a "
                                "bound and is reported beside what it withheld "
                                "(AUDIT-ALL-0004).",
    }


def _pct(x: object) -> str:
    return f"{float(x):.1%}" if isinstance(x, (int, float)) else "n/a"


def report_markdown() -> int:
    """Render `derived/audit.json` as the page the docs transclude.

    Separate from the audit and driven by the artifact, so regenerating the prose costs
    nothing and cannot introduce a number the artifact does not contain. Every figure below
    is read out of the JSON; none is typed in.
    """
    d = json.loads((DERIVED / "audit.json").read_text(encoding="utf-8"))
    m, lk, em, diff = d["manifest"], d["links"], d["emission"], d["difficulty"]
    out: list[str] = []
    w = out.append

    w("## The second audit: HumanEval+")
    w("")
    w(f"nonius pointed at a benchmark its author did not build. EvalPlus supplies the "
      f"items, the contracts, the canonical solutions and the oracle; this project claims "
      f"none of them. Spec `{d['provenance']['nonius_spec']}`, access "
      f"{d['provenance']['access']}.")
    w("")
    w(f"The adapter admits **{m['items']} of HumanEval's 164 items**. The rest are absent "
      f"because their signature is not plain positional or their result is not a scalar "
      f"nonius can pipe, plus two named exclusions: "
      f"`{', '.join(m['excluded']['nondeterministic'])}` is nondeterministic and "
      f"`{', '.join(m['excluded']['property_oracle'])}` has a property oracle rather than a "
      f"value one. HumanEval ships no topic label, so no family stratum is declared: any "
      f"would be adapter-invented.")
    w("")
    w("### The funnel")
    w("")
    w("Four numbers, and the gaps between them are the finding:")
    w("")
    w("| stage | count | share of previous |")
    w("| --- | ---: | ---: |")
    w(f"| type-compatible candidates | {lk['candidate_links']} | |")
    w(f"| decidable (has a probe set) | {lk['decided_links']} | "
      f"{lk['decided_links'] / lk['candidate_links']:.1%} |")
    w(f"| live (answer varies over the codomain) | {lk['live_links']} | "
      f"{_pct(lk['live_share_of_decided'])} |")
    w(f"| emittable (downstream contract accepts it) | {em['emittable_composites']} | "
      f"{_pct(em['emittable_share_of_live'])} |")
    w("")
    w(f"{lk['unprobeable_links']} candidates were never *decided*: their upstream result "
      f"has no probe set, so calling them dead would report an absent probe set as a fact "
      f"about the benchmark. They are excluded from the denominator rather than counted "
      f"against it.")
    w("")
    w(f"The last row is the one this subject taught the project. Liveness asks whether the "
      f"downstream answer varies over the upstream codomain. Emission additionally needs "
      f"the downstream **contract** to accept the piped value, and EvalPlus's contracts are "
      f"the only domain declaration these items carry. "
      f"{em['refused_at_realization']} live links are refused at realization "
      f"({', '.join(f'{n} {k}' for k, n in sorted(em['refusal_kinds'].items()))}), so "
      f"liveness is necessary and not sufficient here in exactly the way type "
      f"compatibility is necessary and not sufficient for liveness.")
    w("")

    if diff.get("available"):
        w("### Difficulty, and why the strata are not comparable across subjects")
        w("")
        w(f"The archive holds {diff['items']} items across {len(diff['systems'])} systems at "
          f"k = {diff['k']}: `{', '.join(diff['systems'])}`.")
        w("")
        w("| stratum | items |")
        w("| --- | ---: |")
        for k, v in diff["strata"].items():
            w(f"| {k} | {v} |")
        w("")
        w(f"**{diff['panel_caveat']}**")
        w("")
        w(f"The noise band is {diff['noise_band']:.4f} with "
          f"{diff['unanimous_cell_fraction']:.1%} of cells unanimous, so the same bias "
          f"`docs/honesty.md` records for the first subject applies here and is larger.")
        w("")
        w(f"{diff['systems_omitted_note']}")
        w("")

    if d.get("readouts"):
        w("### Resolution readout")
        w("")
        w("Predicted rows, from the archive and the independence product bound. Nothing "
          "here is measured: no inference was bought for this subject. Two cautions come "
          "before the table, and both of them limit what it can be read to say.")
        w("")
        w("**The depth-1 row is not a baseline for the rows below it.** `singleton_row` "
          "averages over every item in the archive, while the composed rows are built only "
          "from the items the adapter admits. Those populations differ here, and not "
          "randomly: the admitted items are easier for every one of the six systems.")
        w("")
        arch = load_archive(ARCHIVE)
        admitted = {i.id for i in ep.items()}
        complete = [i for i in arch.items if all(arch.rate(s, i) is not None for s in arch.systems)]
        w("| system | depth-1 row (all archive items) | restricted to the composable items "
          "| difference |")
        w("| --- | ---: | ---: | ---: |")
        for s in arch.systems:
            allr = mean([arch.rate(s, i) for i in complete])  # type: ignore[arg-type]
            sub = mean([arch.rate(s, i) for i in complete if i in admitted])  # type: ignore[arg-type]
            w(f"| {s} | {allr:.4f} | {sub:.4f} | {sub - allr:+.4f} |")
        w("")
        w(f"So the depth 1 to depth 2 fall is measured across a change of population as "
          f"well as a change of depth. The same report says {len(admitted)} chains at "
          f"depth 1 and {d['readouts'][0]['n']} items in the depth-1 row, which is the "
          f"inconsistency in one line. Read the composed rows against the middle column, "
          f"never the left one. This is a defect in the audit rather than in the subject, "
          f"and it applies to the first subject's readout too.")
        w("")
        w("**The predicted rows cannot test what a measured run would test.** Under the "
          "product bound a composite's accuracy is a product of its components', so the "
          "ordering over systems is preserved by construction and decay with depth is "
          "arithmetic rather than evidence. `m*` falls with depth for the same mechanical "
          "reason: predictions crowd toward zero, so their spread shrinks. That the gap "
          "exceeds `m*` at every depth is therefore not a finding about composition. It is "
          "the same shape of vacuity `docs/honesty.md` records for the gold-agreement "
          "check and for KT-1.")
        w("")
        systems = sorted({s for r in d["readouts"] for s in r["accuracy"]})
        w("| depth | n | source | " + " | ".join(systems)
          + " | dead | floored | discriminating | gap | m\\* | gap > m\\* |")
        w("| ---: | ---: | --- | " + " | ".join("---:" for _ in systems)
          + " | ---: | ---: | ---: | ---: | ---: | --- |")
        for r in d["readouts"]:
            acc = " | ".join(f"{r['accuracy'].get(s, 0.0):.4f}" for s in systems)
            ms = f"{r['m_star']:.4f}" if r["m_star"] is not None else "n/a"
            w(f"| {r['depth']} | {r['n']} | {r['source']} | {acc} | {r['dead']:.4f} | "
              f"{r['floored']:.4f} | {r['discriminating']:.4f} | {r['top_two_gap']:.4f} | "
              f"{ms} | {'yes' if r['gap_exceeds_m_star'] else 'no'} |")
        w("")
        w(f"Verdict: **`{d['verdict']}`**.")
        w("")
        if d.get("concentration_at_depth"):
            w("Concentration, which is the disclosure that makes the rows readable:")
            w("")
            for depth, c in d["concentration_at_depth"].items():
                w(f"* depth {depth}: the largest family contributes {c['chains']} of "
                  f"{c['pool']} chains in the pool")
            w("")

    w("### Caps")
    w("")
    for k, v in sorted(d["caps"].items()):
        w(f"* `{k}`: {v}")
    w("")

    text = "\n".join(out) + "\n"
    (DERIVED / "audit_report.md").write_text(text, encoding="utf-8")
    print(f"wrote {DERIVED / 'audit_report.md'} ({len(out)} lines)")
    return 0


def main() -> int:
    if "--report" in sys.argv[1:]:
        return report_markdown()
    items = ep.items()
    oracle = memoized(ep.oracle)
    analysis = analyze(items, oracle)  # type: ignore[arg-type]
    arch = load_archive(ARCHIVE) if ARCHIVE.exists() else None

    candidates = len(analysis.candidates)
    live = len(analysis.live)
    liveness_reasons = Counter(v.reason for v in analysis.verdicts if not v.live)

    # The distinction the headline turns on. A link refused because its upstream result has
    # no probe set was never DECIDED; a link refused because the downstream answer is
    # constant over the codomain was decided and found dead. Reporting them as one number
    # would let an absent probe set read as evidence about the benchmark's structure.
    unprobeable = sum(
        n for r, n in liveness_reasons.items() if "no probe set" in r or "empty codomain" in r
    )
    decided = candidates - unprobeable
    dead = decided - live

    # A live link is not an emittable composite on this subject. Liveness asks whether the
    # downstream answer varies over the upstream codomain; emission additionally requires
    # the downstream CONTRACT to accept the piped value, and EvalPlus's contracts are the
    # only domain declaration these items have. Reporting liveness alone would overstate
    # what can actually be built, so the audit measures both and says so.
    print(f"  analysis done: {candidates} candidates, {live} live; realizing", flush=True)
    idx = index(items)
    realizer = ep.make_realizer()
    emittable = refused = 0
    # Distinct from `liveness_reasons`. These two counters were once one name, and the
    # rebinding silently published the realization kinds under `links.refusal_reasons`.
    refusal_kinds: Counter[str] = Counter()
    for cand in analysis.live:
        chain = make_chain((cand.upstream_item, cand.downstream_item),
                           [Link(0, cand.result, 1, cand.slot, cand.tag)])
        try:
            realize(chain, idx, oracle, realizer)  # type: ignore[arg-type]
            emittable += 1
        except Exception as exc:  # noqa: BLE001 - the refusal is the measurement
            refused += 1
            refusal_kinds[type(exc).__name__] += 1

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
            "refusal_reasons": dict(sorted(liveness_reasons.items())),
        },
        "emission": {
            "note": "A live link still needs the downstream contract to accept the piped "
                    "value. Liveness is necessary and not sufficient here, exactly as type "
                    "compatibility is necessary and not sufficient for liveness.",
            "live_links": live,
            "emittable_composites": emittable,
            "refused_at_realization": refused,
            "emittable_share_of_live": emittable / live if live else None,
            "refusal_kinds": dict(sorted(refusal_kinds.items())),
        },
        "difficulty": _difficulty(arch),
        "caps": dict(analysis.caps),
    }
    if arch is not None:
        print("  archive loaded; running the depth-graded audit", flush=True)
        report = audit(items, oracle, archive=arch, depths=DEPTHS, seed=SEED)  # type: ignore[arg-type]
        payload["readouts"] = [
            {"depth": r.depth, "n": r.n, "source": r.source,
             "accuracy": dict(sorted(r.accuracy.items())),
             "dead": r.dead, "floored": r.floored, "discriminating": r.discriminating,
             "top_two_gap": r.top_two_gap, "m_star": r.m_star,
             "gap_exceeds_m_star": r.m_star is not None and r.top_two_gap > r.m_star}
            for r in report.readouts
        ]
        payload["verdict"] = report.verdict
        payload["concentration_at_depth"] = {
            str(k): {"family": f, "chains": c, "pool": pl}
            for k, (f, c, pl) in sorted(report.concentration_at_depth.items())
        }
        (DERIVED / "readout.txt").write_text(report.render() + "\n", encoding="utf-8")

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
