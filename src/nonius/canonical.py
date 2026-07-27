"""Deterministic serialization (CORE-ALL-0002).

Every artifact nonius writes -- composite records, audit reports, drift snapshots -- is
byte-identical for the same inputs on the same platform. That is a tested contract
(tests/test_determinism.py), not a sentence: no timestamps, no hash-order dependence,
no locale-sensitive formatting. Cross-OS byte-identity is explicitly not claimed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def qfloat(x: float) -> float:
    """Quantize to 12 significant digits (CORE-ALL-0002).

    Applied at every serialization boundary so that an arithmetic reassociation in a
    later Python release cannot move a published digit.
    """
    return float(f"{x:.12g}")


def _quantize(obj: Any) -> Any:
    if isinstance(obj, float):
        return qfloat(obj)
    if isinstance(obj, dict):
        return {k: _quantize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_quantize(v) for v in obj]
    return obj


def canonical_json(obj: Any, *, indent: int | None = None) -> str:
    """Sorted keys, quantized floats, no trailing whitespace, LF only."""
    return json.dumps(
        _quantize(obj),
        sort_keys=True,
        indent=indent,
        separators=(",", ":") if indent is None else (",", ": "),
        ensure_ascii=False,
    )


def content_hash(obj: Any) -> str:
    """A stable 16-hex-digit content hash over any JSON-representable value.

    Truncated sha256. Used for composite identity (EMIT-ALL-0005), where the hash must
    change if and only if the composite's meaning changes.
    """
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()[:16]
