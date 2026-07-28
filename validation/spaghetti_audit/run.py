#!/usr/bin/env python3
"""The reference audit: nonius pointed at a real benchmark.

Produces every artifact under ``derived/``. Deterministic -- sorted keys, no timestamps --
so re-running it on the same inputs produces byte-identical files and the docs cannot
drift from the numbers.

The subject is Spaghetti Architect: a separate project, read strictly read-only, used here
as an instrument and claimed as nothing. See ../../NOTICE for the boundary.

    NONIUS_SPAGHETTI_HOME=/path/to/Spaghetti-Architect python validation/spaghetti_audit/run.py

A missing checkout is a hard error and never a silent skip: this report is part of the
scholarly artifact, and a report that quietly measured nothing is worse than no report.
"""

from __future__ import annotations

import copy
import dataclasses
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent.parent / "src"))

from nonius.adapters import spaghetti as sp  # noqa: E402
from nonius.audit import audit, constructible  # noqa: E402
from nonius.bound import noise_band  # noqa: E402
from nonius.bridge import build as build_bridge  # noqa: E402
from nonius.canonical import canonical_json  # noqa: E402
from nonius.compose import analyze, composite_record, realize  # noqa: E402
from nonius.manifest import index  # noqa: E402
from nonius.resolution import ci95_for, predict  # noqa: E402
from nonius.spec.registry import spec_version  # noqa: E402

DERIVED = ROOT / "derived"
DEPTHS = (1, 2, 3, 5, 8, 13)
SEED = 20260619


def _provenance(home: Path) -> dict[str, object]:
    try:
        commit = subprocess.run(
            ["git", "-C", str(home), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    return {
        "subject": "Spaghetti Architect",
        "subject_commit": commit,
        "subject_role": "instrument and input; claimed as neither",
        "nonius_spec": spec_version(),
        "seed": SEED,
        "access": "read-only",
    }


def _item_level_stats(home: Path) -> dict[str, object]:
    """The archive's discrimination, at the unit the benchmark actually scores.

    The audit composes *programs*, so its archive pools the fifteen rendering cells and
    reports 100 programs. The benchmark itself scores 1500 items -- program x profile x
    language. Both are true and they are not the same number, so both are recorded here
    and each is labelled with its unit.
    """
    per_cell: dict[tuple[str, str, str], dict[str, float]] = {}
    for profile in sp.PROFILES:
        for language in sp.LANGUAGES:
            arch = sp.archive(home, profile=profile, language=language)
            for item in arch.items:
                per_cell[(item, profile, language)] = arch.per_item(item)

    systems = sorted({s for row in per_cell.values() for s in row})
    complete = [row for row in per_cell.values() if len(row) == len(systems)]
    n = len(complete)
    dead = sum(1 for row in complete if all(row[s] == 1.0 for s in systems))
    floored = sum(1 for row in complete if all(row[s] == 0.0 for s in systems))
    disc = sum(1 for row in complete if len({round(row[s], 12) for s in systems}) > 1)
    means = {s: sum(row[s] for row in complete) / n for s in systems}
    ranked = sorted(means.values(), reverse=True)
    # The same resolution floor the composed rows carry, so the singleton gap is read
    # against a floor rather than quoted bare.
    m_star = max(ci95_for([row[s] for row in complete], seed=SEED) for s in systems)

    return {
        "unit": "item = program x profile x language",
        "n": n,
        "systems": systems,
        "mean_accuracy": means,
        "top_two_gap": ranked[0] - ranked[1],
        "m_star": m_star,
        "dead_all_systems_perfect": dead,
        "dead_fraction": dead / n,
        "floored_all_systems_fail": floored,
        "floored_fraction": floored / n,
        "discriminating": disc,
        "discriminating_fraction": disc / n,
    }


def _uniform_contrast(items: object, analysis: object, arch: object) -> list[dict[str, object]]:
    """The same prediction over the constructible and the uniform population.

    AUDIT-ALL-0002 exists because these differ. Recording both is what makes the ruling
    checkable rather than assertable.
    """
    import random

    from nonius.model import Chain

    rng = random.Random(SEED)
    ids = [i.id for i in items]  # type: ignore[attr-defined]
    rows: list[dict[str, object]] = []
    for depth in (2, 3, 5):
        pool = constructible(analysis, depth, cap=20_000)  # type: ignore[arg-type]
        if not pool:
            continue
        c = predict(pool, arch, depth=depth, seed=SEED, sample=20_000)  # type: ignore[arg-type]
        # predict() stamps population="constructible" unconditionally, and this arm is
        # deliberately the opposite. Relabel it rather than letting the readout assert
        # something false about where its rows came from.
        u = dataclasses.replace(
            predict(
                [Chain(tuple(rng.sample(ids, depth)), ()) for _ in range(5000)],
                arch,  # type: ignore[arg-type]
                depth=depth,
                seed=SEED,
                sample=20_000,
            ),
            caps={"population": "uniform", "note": "sampled uniformly over all items"},
        )
        for label, row in (("constructible", c), ("uniform", u)):
            rows.append(
                {
                    "depth": depth,
                    "population": label,
                    "n": row.n,
                    "discriminating": row.discriminating,
                    "top_two_gap": row.top_two_gap,
                    "floored": row.floored,
                }
            )
    return rows


def _validate_toolchains(home: Path, analysis: object, idx: object) -> dict[str, object]:
    """Compile and run emitted composites in all five target languages.

    This is where EMIT-ALL-0006 earns its keep: the merged program's own oracle gave the
    gold, and here an actual compiler and runtime are asked whether that gold is what the
    program produces.
    """
    # Through the adapter, never by importing the subject here: the seam is the point, and
    # tests/test_layering.py only guards src/, so a direct import in this file would be an
    # unchecked second entrance.
    sa = sp._sa(str(home))
    validate = sa["validate"]

    realizer = sp.make_realizer(home, profile="max")

    tc_depths, tc_cap, tc_per_depth = (2, 3, 5), 40, 2
    outcomes: dict[str, int] = {}
    checked: list[dict[str, object]] = []
    for depth in tc_depths:
        for chain in constructible(analysis, depth, cap=tc_cap)[:tc_per_depth]:  # type: ignore[arg-type]
            composite, _ = realize(chain, idx, sp.oracle, realizer)  # type: ignore[arg-type]
            programs = [
                sa["parse"](copy.deepcopy(idx[c].payload["ir"]))  # type: ignore[index]
                for c in chain.components
            ]
            merged, _s = sp._merge(sa, programs, list(chain.links))
            per_lang = {}
            for lang, source in sorted(composite.realization.rendering.items()):
                result = validate(lang, source, merged)
                per_lang[lang] = result.status
                outcomes[result.status] = outcomes.get(result.status, 0) + 1
            checked.append(
                {
                    "composite": composite.id,
                    "depth": chain.depth,
                    "components": list(chain.components),
                    "languages": per_lang,
                }
            )
    return {
        "note": (
            "PASS means the rendered composite compiled, ran, and produced exactly the "
            "gold that the merged program's oracle predicted. SKIP means the toolchain is "
            "absent on this machine, which is honest locally and would be a no-op in CI."
        ),
        # A sample, and a small one. Stating the selection is what stops the outcome tally
        # from reading as coverage of the whole emitted set (AUDIT-ALL-0004).
        "selection": {
            "depths": list(tc_depths),
            "composites_per_depth": tc_per_depth,
            "composites_checked": len(checked),
            "languages_per_composite": len(sp.LANGUAGES),
            "note": "a spot check, not a sweep: the emitted set is far larger",
        },
        "outcomes": outcomes,
        "composites": checked,
    }


def main() -> int:
    home = sp.home()
    DERIVED.mkdir(parents=True, exist_ok=True)

    items = sp.items(home)
    idx = index(items)
    analysis = analyze(items, sp.oracle)
    arch = sp.archive(home)

    report = audit(items, sp.oracle, archive=arch, depths=DEPTHS, seed=SEED, sample=20_000)

    payload: dict[str, object] = {
        "provenance": _provenance(home),
        "audit": report.to_dict(),
        "archive": {
            "unit": "item = program (fifteen rendering cells pooled as replicates)",
            "systems": list(arch.systems),
            "items": len(arch.items),
            "k": arch.k(),
            "mean_accuracy": {
                s: sum(r for i in arch.items if (r := arch.rate(s, i)) is not None)
                / len(arch.items)
                for s in arch.systems
            },
            # The band every quarantine verdict is read against, emitted rather than
            # hand-copied: it was the last number in the repository that no generator
            # produced, and it was wrong by a digit.
            "noise_band": noise_band(arch, seed=SEED),
            "strata": {
                name: sum(1 for i in arch.items if arch.stratum(i) == name)
                for name in ("dead", "floored", "discriminating", "uniform-partial")
            },
        },
        "item_level": _item_level_stats(home),
        "population_contrast": _uniform_contrast(items, analysis, arch),
        "toolchain_validation": _validate_toolchains(home, analysis, idx),
    }

    # Everything is rendered before anything is written. These four files are committed
    # artifacts that get read together, and a run that died between the first and the last
    # used to leave them from two different runs -- which is exactly how the m* crash
    # shipped a report contradicting the audit.json beside it.
    artifacts: dict[str, str] = {
        "audit.json": canonical_json(payload, indent=2) + "\n",
    }

    # A small, committed sample of real composites, so a reader can see what the operator
    # actually emits rather than only what it counts.
    realizer = sp.make_realizer(home, profile="max", languages=("python",))
    sample: list[str] = []
    for depth in (2, 3, 5, 8, 13):
        for chain in constructible(analysis, depth, cap=10)[:2]:
            composite, _ = realize(
                chain,
                idx,
                sp.oracle,
                realizer,
                strata=tuple(arch.stratum(c) for c in chain.components),
            )
            sample.append(canonical_json(composite_record(composite)))
    artifacts["composites_sample.jsonl"] = "\n".join(sample) + "\n"

    bridge_rows = []
    for depth in (2, 3, 5):
        pool = constructible(analysis, depth, cap=20_000)
        if pool:
            bridge_rows += [
                {
                    "system": r.system,
                    "depth": r.depth,
                    "singleton": r.singleton,
                    "predicted_composite": r.predicted_composite,
                    "chains_used": r.chains_used,
                    "chains_available": r.chains_available,
                }
                for r in build_bridge(pool, arch, depth=depth)
            ]
    artifacts["bridge.json"] = (
        canonical_json({"note": BRIDGE_NOTE, "rows": bridge_rows}, indent=2) + "\n"
    )

    # _markdown() renders the report, and is the step that used to raise. It runs before
    # the first write, so a failure here leaves derived/ exactly as it was.
    artifacts["audit_report.md"] = _markdown(payload, report)

    for name, content in sorted(artifacts.items()):
        (DERIVED / name).write_text(content, encoding="utf-8")
    print(f"wrote {len(artifacts)} artifacts to {DERIVED}")
    print(report.render())
    return 0


BRIDGE_NOTE = (
    "An arithmetic re-expression under an independence assumption, not a proof of "
    "measurement equivalence. Measured columns are absent because no composite has been "
    "run against any system: the paid run is designed and pre-registered, not executed. "
    "Note also that the two columns are computed on different populations: `singleton` is "
    "the mean over every archive item, while `predicted_composite` is the mean over the "
    "components of the supplied chains, which is a small and skewed subset of them. They "
    "are comparable as currencies, not as samples."
)


def _markdown(payload: dict[str, object], report: object) -> str:
    audit_d = payload["audit"]
    assert isinstance(audit_d, dict)
    item = payload["item_level"]
    assert isinstance(item, dict)
    prov = payload["provenance"]
    assert isinstance(prov, dict)

    lines = [
        "# Reference audit: Spaghetti Architect",
        "",
        "Generated by `validation/spaghetti_audit/run.py`. Do not hand-edit: fix the code "
        "or the spec, re-run, and let the derived artifact carry the number.",
        "",
        f"- subject commit: `{prov['subject_commit']}`",
        f"- nonius composition spec: `{prov['nonius_spec']}`",
        f"- seed: `{prov['seed']}`",
        "- access: read-only. Nothing in the subject repository is modified.",
        "",
        "## Verdict",
        "",
        f"**{audit_d['verdict']}**",
        "",
        "```",
        report.render(),  # type: ignore[attr-defined]
        "```",
        "",
        "## The two units, and why both appear",
        "",
        "The composer works on programs, so the audit's archive pools the fifteen "
        "rendering cells (three messiness profiles x five languages) and reports "
        f"{len(audit_d.get('reach', []))} families over {audit_d['items']} programs. "
        "The benchmark itself "
        f"scores {item['n']} items, one per program x profile x language. Both numbers are "
        "true; they are not the same quantity, and neither is a rounding of the other.",
        "",
        f"At the item level: {item['dead_all_systems_perfect']} of {item['n']} "
        f"({item['dead_fraction']:.1%}) are answered perfectly by all four systems, "
        f"{item['floored_all_systems_fail']} ({item['floored_fraction']:.1%}) are failed by "
        f"all four, and {item['discriminating']} ({item['discriminating_fraction']:.1%}) "
        f"discriminate. The gap between the top two systems is "
        f"{item['top_two_gap']:.4f}, against a resolution floor m* of "
        f"{item['m_star']:.4f}.",
        "",
        "## Constructible against uniform",
        "",
        "Same archive, same unit; only the population differs (AUDIT-ALL-0002).",
        "",
        "| depth | population | n | discriminating | top-two gap | floored |",
        "|---|---|---|---|---|---|",
    ]
    contrast = payload["population_contrast"]
    assert isinstance(contrast, list)
    for row in contrast:
        lines.append(
            f"| {row['depth']} | {row['population']} | {row['n']} | "
            f"{row['discriminating']:.4f} | {row['top_two_gap']:.4f} | {row['floored']:.4f} |"
        )

    tv = payload["toolchain_validation"]
    assert isinstance(tv, dict)
    sel = tv["selection"]
    assert isinstance(sel, dict)
    lines += [
        "",
        "## Do the emitted composites actually run?",
        "",
        str(tv["note"]),
        "",
        f"Outcomes across five toolchains: `{tv['outcomes']}` -- "
        f"{sel['composites_checked']} composites x {sel['languages_per_composite']} "
        f"languages, sampled {sel['composites_per_depth']} per depth from "
        f"{sel['depths']}. A spot check, not a sweep.",
        "",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
