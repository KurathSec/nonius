"""The item manifest: JSONL in, ``Item`` out (CORE-ALL-0003).

One record per item, declaring the three things a benchmark with an execution oracle
already possesses but never exposes -- typed named input slots, typed named results, and
enough payload for its own oracle and realizer to do their work.

    {"id": "item-1",
     "family": "arithmetic",
     "slots":   [{"name": "n", "tag": "int", "consumer": "threshold"}],
     "results": [{"name": "verdict", "tag": "str", "codomain": ["low", "high"]}],
     "payload": {"...": "adapter-private"}}

``codomain`` may be omitted, which declares the result unbounded and sends liveness
probing to the versioned probe set (LINK-ALL-0003).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

from nonius.errors import ManifestError
from nonius.model import Item, ResultVar, Scalar, Slot, TypeTag

_TAGS: frozenset[str] = frozenset({"bool", "int", "float", "str", "null"})


def _tag(raw: Any, where: str) -> TypeTag:
    if raw == "bool":
        return "bool"
    if raw == "int":
        return "int"
    if raw == "float":
        return "float"
    if raw == "str":
        return "str"
    if raw == "null":
        return "null"
    raise ManifestError(f"{where}: tag must be one of {sorted(_TAGS)}, got {raw!r}")


def _scalar(raw: Any, where: str) -> Scalar:
    if raw is None or isinstance(raw, (str, int, float, bool)):
        return raw
    raise ManifestError(f"{where}: expected a scalar, got {type(raw).__name__}")


def _built(build: Any, where: str) -> Any:
    """Construct a model object, reporting its validation failure as a manifest error."""
    try:
        return build()
    except ValueError as exc:
        raise ManifestError(f"{where}: {exc}") from exc


def _slot(raw: Any, where: str) -> Slot:
    if not isinstance(raw, dict):
        raise ManifestError(f"{where}: slot must be an object")
    if "name" not in raw or "tag" not in raw:
        raise ManifestError(f"{where}: slot needs 'name' and 'tag'")
    accepts = raw.get("accepts")
    built: Slot = _built(
        lambda: Slot(
            name=str(raw["name"]),
            tag=_tag(raw["tag"], f"{where}.tag"),
            accepts=(
                tuple(_scalar(v, f"{where}.accepts") for v in accepts)
                if isinstance(accepts, list)
                else None
            ),
            consumer=str(raw.get("consumer", "")),
        ),
        where,
    )
    return built


def _result(raw: Any, where: str) -> ResultVar:
    if not isinstance(raw, dict):
        raise ManifestError(f"{where}: result must be an object")
    if "name" not in raw or "tag" not in raw:
        raise ManifestError(f"{where}: result needs 'name' and 'tag'")
    codomain = raw.get("codomain")
    built: ResultVar = _built(
        lambda: ResultVar(
            name=str(raw["name"]),
            tag=_tag(raw["tag"], f"{where}.tag"),
            codomain=(
                tuple(_scalar(v, f"{where}.codomain") for v in codomain)
                if isinstance(codomain, list)
                else None
            ),
        ),
        where,
    )
    return built


def item_from_dict(raw: Any, where: str = "item") -> Item:
    if not isinstance(raw, dict):
        raise ManifestError(f"{where}: record must be an object")
    if "id" not in raw:
        raise ManifestError(f"{where}: record needs an 'id'")
    item_id = str(raw["id"])

    slots = tuple(
        _slot(s, f"{item_id}.slots[{i}]") for i, s in enumerate(raw.get("slots", []))
    )
    results = tuple(
        _result(r, f"{item_id}.results[{i}]") for i, r in enumerate(raw.get("results", []))
    )

    names = [s.name for s in slots]
    if len(set(names)) != len(names):
        raise ManifestError(f"{item_id}: duplicate slot name")
    names = [r.name for r in results]
    if len(set(names)) != len(names):
        raise ManifestError(f"{item_id}: duplicate result name")

    payload = raw.get("payload", {})
    if not isinstance(payload, dict):
        raise ManifestError(f"{item_id}: payload must be an object")

    return Item(
        id=item_id,
        slots=slots,
        results=results,
        family=str(raw.get("family", "")),
        payload=payload,
    )


def item_to_dict(item: Item) -> dict[str, Any]:
    out: dict[str, Any] = {"id": item.id}
    if item.family:
        out["family"] = item.family
    if item.slots:
        out["slots"] = [
            {
                k: v
                for k, v in (
                    ("name", s.name),
                    ("tag", s.tag),
                    ("accepts", list(s.accepts) if s.accepts is not None else None),
                    ("consumer", s.consumer or None),
                )
                if v is not None
            }
            for s in item.slots
        ]
    if item.results:
        out["results"] = [
            {
                k: v
                for k, v in (
                    ("name", r.name),
                    ("tag", r.tag),
                    ("codomain", list(r.codomain) if r.codomain is not None else None),
                )
                if v is not None
            }
            for r in item.results
        ]
    if item.payload:
        out["payload"] = dict(item.payload)
    return out


def loads(text: str) -> tuple[Item, ...]:
    """Parse a JSONL manifest. Blank lines and ``#`` comment lines are skipped."""
    items: list[Item] = []
    seen: set[str] = set()
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            raw = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ManifestError(f"line {lineno}: {exc}") from exc
        item = item_from_dict(raw, where=f"line {lineno}")
        if item.id in seen:
            raise ManifestError(f"line {lineno}: duplicate item id {item.id!r}")
        seen.add(item.id)
        items.append(item)
    return tuple(items)


def load(path: str | Path) -> tuple[Item, ...]:
    return loads(Path(path).read_text(encoding="utf-8"))


def dumps(items: Iterable[Item]) -> str:
    """Serialize back to JSONL. Round-trips: ``loads(dumps(x)) == x``."""
    return "".join(
        json.dumps(item_to_dict(i), sort_keys=True, ensure_ascii=False) + "\n" for i in items
    )


def index(items: Sequence[Item]) -> dict[str, Item]:
    return {i.id: i for i in items}


def iter_items(path: str | Path) -> Iterator[Item]:
    yield from load(path)
