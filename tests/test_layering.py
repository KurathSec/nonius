"""Gate 3 of 3: the isolation seam, enforced rather than agreed (ARCHITECTURE.md §2).

nonius's whole contribution is that the composition operator is factored *out* of the
benchmark it was demonstrated on. If the core quietly imported that benchmark, the
factoring would be a claim in a README rather than a property of the code.

So: exactly one module may *import* Spaghetti Architect's source tree, and it is the
adapter. Naming the project in prose is fine and several core modules do; what is enforced
here is the import graph, plus the adapter's read-only promise. This is also the
anti-salami boundary in machine-checkable form -- see NOTICE.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from conftest import ROOT

SRC = ROOT.parent / "src" / "nonius"
ADAPTER = SRC / "adapters" / "spaghetti.py"

#: Top-level package names that belong to Spaghetti Architect's source tree.
FOREIGN = {"src", "bench", "eval"}

CORE = sorted(p for p in SRC.rglob("*.py") if p != ADAPTER)


@pytest.mark.parametrize("path", CORE, ids=lambda p: str(p.relative_to(SRC)))
def test_core_never_imports_the_benchmark(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "").split(".")[0]]
        else:
            continue
        offending = sorted(set(names) & FOREIGN)
        assert not offending, (
            f"{path.relative_to(SRC)}:{node.lineno} imports {offending}; only "
            f"adapters/spaghetti.py may, and the core must run without that project present"
        )


def test_core_imports_without_the_benchmark_present() -> None:
    """Importing nonius must not require the adapter's dependency to exist."""
    import nonius

    assert nonius.spec_version()
    assert nonius.__version__


def test_adapter_opens_nothing_for_writing() -> None:
    """The adapter reads a third-party checkout and must never modify it.

    Checked structurally: no ``open(..., "w")``, no ``Path.write_*``, no ``shutil`` or
    ``os`` mutation call anywhere in the module.
    """
    source = ADAPTER.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(ADAPTER))

    banned_attrs = {
        "write_text",
        "write_bytes",
        "mkdir",
        "unlink",
        "rmdir",
        "rename",
        "replace",
        "touch",
        "chmod",
        "remove",
        "rmtree",
        "copy",
        "copytree",
        "move",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                assert func.attr not in banned_attrs, (
                    f"adapters/spaghetti.py:{node.lineno} calls {func.attr}(); the adapter "
                    f"is read-only"
                )
            if isinstance(func, ast.Name) and func.id == "open":
                mode = "r"
                for kw in node.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        mode = str(kw.value.value)
                if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                    mode = str(node.args[1].value)
                assert "w" not in mode and "a" not in mode and "+" not in mode, (
                    f"adapters/spaghetti.py:{node.lineno} opens a file for writing"
                )


def test_adapter_is_the_only_exempted_module() -> None:
    """The ruff exemption list and this test must agree on which module is the seam."""
    pyproject = (ROOT.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert '"src/nonius/adapters/spaghetti.py" = ["TID253"]' in pyproject
