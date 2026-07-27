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

#: Modules whose ``open`` takes the path first and the mode second, unlike ``Path.open``.
_OPEN_MODULES = {"gzip", "io", "bz2", "lzma", "codecs", "os", "tarfile", "zipfile", "shutil"}

CORE = sorted(p for p in SRC.rglob("*.py") if p != ADAPTER)


@pytest.mark.parametrize("path", CORE, ids=lambda p: str(p.relative_to(SRC)))
def test_core_never_imports_the_benchmark(path: Path) -> None:
    """No import statement names the subject's tree.

    Statements only; :func:`test_core_takes_no_dynamic_route_to_the_benchmark` covers the
    ways a module can depend on it without one.
    """
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


#: Ways to reach a module without an import statement. The core has no business with any
#: of them, and an import-statement-only gate is blind to every one.
DYNAMIC_IMPORT = {"import_module", "__import__", "exec_module", "spec_from_file_location"}

#: Names that mean "shell out" whoever owns them.
SHELL_DISTINCTIVE = {"popen", "Popen", "check_output", "check_call", "execv", "execvp"}
#: Names that mean it only when the receiver says so. ``system``, ``run`` and ``call`` are
#: ordinary method names elsewhere -- ``platform.system()`` is not a subprocess.
SHELL_RECEIVERS = {"subprocess", "os"}
SHELL_SCOPED = {"system", "run", "call", "spawnl", "spawnv", "fork"}


def _shell_aliases(tree: ast.Module) -> tuple[set[str], set[str]]:
    """Local names bound to a shell module, and to a shell function directly.

    ``import subprocess as sp`` and ``from os import system as go`` both defeat a check
    that matches source names, and both are one line of work for anyone trying.
    """
    modules: set[str] = set(SHELL_RECEIVERS)
    functions: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in SHELL_RECEIVERS:
                    modules.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in SHELL_RECEIVERS:
                for alias in node.names:
                    if alias.name in SHELL_DISTINCTIVE | SHELL_SCOPED:
                        functions.add(alias.asname or alias.name)
    return modules, functions


def _shells_out(node: ast.Call, modules: set[str], functions: set[str]) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute):
        receiver = func.value
        if isinstance(receiver, ast.Name) and receiver.id in modules:
            return func.attr in SHELL_DISTINCTIVE | SHELL_SCOPED
        return func.attr in SHELL_DISTINCTIVE
    name = getattr(func, "id", "")
    # A bare ``system(...)`` in this codebase came from ``os``; a bare ``run(...)`` did not.
    return name in SHELL_DISTINCTIVE | {"system"} or name in functions


@pytest.mark.parametrize("path", CORE, ids=lambda p: str(p.relative_to(SRC)))
def test_core_takes_no_dynamic_route_to_the_benchmark(path: Path) -> None:
    """An import statement is not the only way to depend on something.

    ``importlib.import_module("src.nodes.validator")``, a string appended to ``sys.path``,
    or a subprocess would all satisfy the statement-level gate while making the core
    depend on the subject exactly as much. The core module that legitimately loads a
    practitioner's oracle by path is exempt by name, because that is its whole job.
    """
    rel = path.relative_to(SRC).as_posix()
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    shell_modules, shell_functions = _shell_aliases(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        if name in DYNAMIC_IMPORT and rel != "oracle.py":
            raise AssertionError(
                f"{rel}:{node.lineno} calls {name}(); the core loads nothing dynamically. "
                f"Only oracle.py may, to load the practitioner's own callable."
            )
        if _shells_out(node, shell_modules, shell_functions):
            raise AssertionError(f"{rel}:{node.lineno} shells out; the core does not")

    # A literal naming the subject's tree is a dependency however it is used. Derived from
    # FOREIGN rather than hand-listed, so the two cannot drift apart -- an earlier version
    # covered "src." and "bench." but only "src/" and "bench/", and never "eval" at all.
    tokens = [
        f"{quote}{pkg}{sep}"
        for pkg in sorted(FOREIGN)
        for quote in ('"', "'")
        for sep in (".", "/")
    ]
    for n, line in enumerate(source.splitlines(), start=1):
        for token in tokens:
            assert token not in line, (
                f"{rel}:{n} names the subject's tree in a string literal ({token!r}); the "
                f"core must run without that project present"
            )

    # sys.path is a route in itself, whatever is appended to it.
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "path":
            if isinstance(node.value, ast.Name) and node.value.id == "sys":
                raise AssertionError(
                    f"{rel}:{node.lineno} touches sys.path; the core does not extend the "
                    f"import path, and doing so is how a dependency arrives without an "
                    f"import statement"
                )


def test_core_imports_without_the_benchmark_present() -> None:
    """Importing nonius must not require the adapter's dependency to exist."""
    import nonius

    assert nonius.spec_version()
    assert nonius.__version__


def test_adapter_opens_nothing_for_writing() -> None:
    """The adapter reads a third-party checkout and must never modify it.

    Checked structurally, against a named set of mutating calls rather than an exhaustive
    one: every ``open`` with a write mode (including a mode this gate cannot read), every
    call whose name is in ``banned_attrs``, and every shell-out, with import aliases
    resolved. A stdlib mutation whose name is not in that set would pass, which is why the
    set is listed in full above rather than described.
    """
    source = ADAPTER.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(ADAPTER))
    shell_modules, shell_functions = _shell_aliases(tree)

    banned_attrs = {
        "write",
        "writelines",
        "write_text",
        "write_bytes",
        "mkdir",
        "makedirs",
        "unlink",
        "rmdir",
        "rename",
        "replace",
        "touch",
        "chmod",
        "remove",
        "rmtree",
        "copy",
        "copy2",
        "copyfile",
        "copyfileobj",
        "copymode",
        "copystat",
        "copytree",
        "move",
        "truncate",
        "symlink",
        "link",
        "hardlink_to",
        "symlink_to",
        "mkfifo",
        "mknod",
        "utime",
        "chown",
        "lchmod",
        "rename_to",
        "renames",
        "removedirs",
        "unpack_archive",
        "make_archive",
        "extract",
        "extractall",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # `open` reaches here as a bare name (builtin) and as an attribute
        # (``Path.open``, ``gzip.open``, ``io.open``). Both take a mode, and both were
        # invisible to an earlier version of this test that checked only the builtin.
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name == "open":
            # Where the mode sits depends on the receiver, and getting this wrong is how
            # the check either misses a write or trips over a legitimate read:
            #   open(path, mode)        builtin      -> index 1
            #   gzip.open(path, mode)   module-style -> index 1
            #   path.open(mode)         Path object  -> index 0
            receiver = func.value if isinstance(func, ast.Attribute) else None
            module_style = isinstance(receiver, ast.Name) and receiver.id in _OPEN_MODULES
            index = 0 if (isinstance(func, ast.Attribute) and not module_style) else 1

            supplied: ast.expr | None = None
            for kw in node.keywords:
                if kw.arg == "mode":
                    supplied = kw.value
            if len(node.args) > index:
                supplied = node.args[index]
            if supplied is None:
                continue  # no mode given: read, which is the default everywhere
            # Fail closed on a mode this gate cannot read. A mode held in a variable is
            # exactly how an earlier version of this check was defeated.
            assert isinstance(supplied, ast.Constant), (
                f"adapters/spaghetti.py:{node.lineno} opens a file with a mode this gate "
                f"cannot read; write it as a literal so the read-only claim stays checkable"
            )
            mode = str(supplied.value)
            assert not ({"w", "a", "x", "+"} & set(mode)), (
                f"adapters/spaghetti.py:{node.lineno} opens a file with mode {mode!r}"
            )
        elif name in banned_attrs:
            # Matched on the callee's NAME, whether it arrives as an attribute
            # (``shutil.copy``, ``p.write_text``) or as a bare name imported earlier
            # (``from os import remove``). An attribute-only check missed the second.
            raise AssertionError(
                f"adapters/spaghetti.py:{node.lineno} calls {name}(); the adapter "
                f"is read-only"
            )
        elif _shells_out(node, shell_modules, shell_functions):
            raise AssertionError(
                f"adapters/spaghetti.py:{node.lineno} shells out; a subprocess can write "
                f"anything and this gate cannot see inside one"
            )


def test_adapter_is_the_only_exempted_module() -> None:
    """The ruff exemption list and this test must agree on which module is the seam."""
    pyproject = (ROOT.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert '"src/nonius/adapters/spaghetti.py" = ["TID253"]' in pyproject
