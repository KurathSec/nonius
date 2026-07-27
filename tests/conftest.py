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
