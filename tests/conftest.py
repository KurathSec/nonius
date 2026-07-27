"""Calibration-corpus loader, importable by tools/ as well as by the tests.

The corpus is one shared item set plus one case file per scenario. Cases are data, not
code: each states the rulings it exercises, how its expected values were computed, and the
arithmetic itself in ``notes``. A case whose numbers cannot be checked by hand is not a
calibration case.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "corpus"
CASES = CORPUS / "cases"

# The corpus oracle lives beside the fixtures so a reader finds it in one place.
if str(CORPUS) not in sys.path:
    sys.path.insert(0, str(CORPUS))


def corpus_items() -> Any:
    from nonius import manifest

    return manifest.load(CORPUS / "items.jsonl")


def corpus_oracle() -> Any:
    from oracle import answer  # type: ignore[import-not-found]

    return answer


def cases() -> list[dict[str, Any]]:
    """Every case file, ordered by id."""
    out: list[dict[str, Any]] = []
    for path in sorted(CASES.glob("*.toml")):
        # Read bytes and decode explicitly: a helpful reader that rewrote line endings
        # would change what a byte-comparing expectation is comparing.
        data = tomllib.loads(path.read_bytes().decode("utf-8"))
        case = dict(data["case"])
        case["expect"] = data.get("expect", {})
        case["path"] = str(path)
        if case["id"] != path.stem:
            raise AssertionError(f"{path}: case id {case['id']!r} does not match filename")
        out.append(case)
    return out


def case_ids() -> set[str]:
    return {c["id"] for c in cases()}


def chain_for(case: dict[str, Any], items: Any) -> Any:
    """Build a case's chain, taking each link's tag from the manifest.

    The case files write links as 4-tuples with no tag, because the tag is not a free
    choice -- it is the slot's declared type. Hard-coding it (say, to "") would make every
    composite id in the drift snapshot the id of a chain the composer never emits.
    """
    from nonius.compose import make_chain
    from nonius.manifest import index
    from nonius.model import Link

    exp = case["expect"]
    idx = index(items)
    components = tuple(exp["components"])
    links = [
        Link(u, r, d, s, idx[components[d]].slot(s).tag) for u, r, d, s in exp["links"]
    ]
    return make_chain(components, links)
