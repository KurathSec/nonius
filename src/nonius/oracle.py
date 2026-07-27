"""The practitioner-supplied callables (ARCHITECTURE.md section 3).

nonius needs two things from a benchmark, and this module states exactly what they are.

An **oracle** maps an item's slot bindings to its results. It is the benchmark's own
gold-producing program, unchanged -- the same thing it already runs to grade a singleton.
This is the instrument's hard precondition: a benchmark whose gold is a stored constant
with no callable behind it cannot be composed, because there is nothing to re-run under
a changed binding. That excludes most multiple-choice suites and every human-labelled set.

A **realizer** turns components plus links into one presentable composite. The dossier's
input specification named three things an item must declare and omitted this one, but a
composer cannot work without it: expressing 'this slot's value is that item's answer'
*without printing the value* is precisely the operation that makes a chain bind, and only
the benchmark knows how to say that in its own presentation. Two tiers ship:
``nonius.realize.prompt_realizer`` works for any manifest whose items carry a slotted
prompt template, and an adapter may supply a native realizer that does better -- the
Spaghetti Architect adapter merges the component programs into one program, so the link
becomes an ordinary variable reference.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from nonius.errors import OracleError
from nonius.model import Item, Link, Realization, Scalar


@runtime_checkable
class Oracle(Protocol):
    """Maps an item's slot bindings to its result variables.

    Must be deterministic and side-effect free: the same bindings must give the same
    results, in this process and the next. nonius calls it many times per link during
    liveness probing and relies on that.
    """

    def __call__(
        self, item: Item, bindings: Mapping[str, Scalar]
    ) -> Mapping[str, Scalar]: ...


@runtime_checkable
class Realizer(Protocol):
    """Turns components plus links into one presentable composite."""

    def __call__(
        self, components: Sequence[Item], links: Sequence[Link]
    ) -> Realization: ...


def load_callable(spec: str) -> object:
    """Load ``module:attr`` or ``/path/to/file.py:attr``.

    A file path is loaded under a private module name so that importing a practitioner's
    oracle cannot shadow an installed package.
    """
    if ":" not in spec:
        raise OracleError(
            f"expected 'module:attr' or 'path.py:attr', got {spec!r}"
        )
    target, _, attr = spec.rpartition(":")
    if not target or not attr:
        raise OracleError(f"malformed callable spec: {spec!r}")

    if target.endswith(".py") or "/" in target or target.startswith("."):
        path = Path(target).expanduser().resolve()
        if not path.is_file():
            raise OracleError(f"no such file: {path}")
        mod_name = f"_nonius_user_{abs(hash(str(path)))}"
        module_spec = importlib.util.spec_from_file_location(mod_name, path)
        if module_spec is None or module_spec.loader is None:
            raise OracleError(f"cannot import {path}")
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[mod_name] = module
        module_spec.loader.exec_module(module)
    else:
        try:
            module = importlib.import_module(target)
        except ImportError as exc:
            raise OracleError(f"cannot import {target!r}: {exc}") from exc

    try:
        obj = getattr(module, attr)
    except AttributeError:
        raise OracleError(f"{target!r} has no attribute {attr!r}") from None
    if not callable(obj):
        raise OracleError(f"{spec!r} is not callable")
    return obj


def evaluate(oracle: Oracle, item: Item, bindings: Mapping[str, Scalar]) -> dict[str, Scalar]:
    """Call the oracle and check its answer is shaped like the item's declaration.

    A mismatch here is a manifest bug, and catching it at the first call is much cheaper
    than discovering it as a gold disagreement thousands of composites later.
    """
    try:
        raw = oracle(item, bindings)
    except Exception as exc:  # noqa: BLE001 - any user callable, reported not swallowed
        raise OracleError(f"oracle raised on item {item.id!r}: {exc!r}") from exc

    declared = {r.name for r in item.results}
    got = set(raw)
    if got != declared:
        raise OracleError(
            f"oracle for item {item.id!r} returned keys {sorted(got)}, "
            f"but the manifest declares {sorted(declared)}"
        )
    return dict(raw)
