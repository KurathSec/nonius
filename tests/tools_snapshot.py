"""Shared value computation for the composition-drift gate and its update tool.

Kept out of the test module so ``tools/update_snapshot.py`` computes the *same* values the
gate compares, rather than a second implementation that can drift from it.
"""

from __future__ import annotations

from typing import Any

from conftest import cases, corpus_items, corpus_oracle

from nonius.compose import analyze, composite_id, make_chain, realize
from nonius.manifest import index
from nonius.model import Link
from nonius.realize import make_prompt_realizer
from nonius.spec.registry import spec_version


def compute() -> dict[str, Any]:
    """Every decision the composer makes on the calibration corpus, as a flat mapping.

    Keys are ``<case-or-scope>::<what>``. Every link verdict, every composite gold and id.
    A numeric or verdict change anywhere in the composer moves a value here.
    """
    items = corpus_items()
    oracle = corpus_oracle()
    idx = index(items)
    values: dict[str, Any] = {}

    analysis = analyze(items, oracle)
    for v in analysis.verdicts:
        c = v.candidate
        key = f"link::{c.upstream_item}.{c.result}->{c.downstream_item}.{c.slot}"
        values[key] = {
            "live": v.live,
            "distinct_outcomes": v.distinct_outcomes,
            "probed": v.probed,
            "tag": c.tag,
        }

    values["analysis::counts"] = {
        "candidates": len(analysis.candidates),
        "live": len(analysis.live),
        "live_pairs": len(analysis.live_pairs()),
    }

    realizer = make_prompt_realizer(oracle)
    for case in cases():
        exp = case.get("expect", {})
        if "links" not in exp or "components" not in exp:
            continue
        chain = make_chain(
            tuple(exp["components"]), [Link(u, r, d, s, "") for u, r, d, s in exp["links"]]
        )
        composite, _ = realize(chain, idx, oracle, realizer)
        values[f"{case['id']}::id"] = composite.id
        values[f"{case['id']}::gold"] = composite.realization.gold_map()
        values[f"{case['id']}::depth"] = chain.depth
        values[f"{case['id']}::path_depth"] = chain.path_depth
        values[f"{case['id']}::suppressed"] = list(composite.realization.suppressed)
        assert composite.id == composite_id(chain)

    return {
        "spec_version": spec_version(),
        "values": values,
    }
