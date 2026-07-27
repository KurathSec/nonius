"""The nonius CLI (stdlib argparse, zero extra dependencies).

Diagnostics go to stderr, data to stdout, so the CLI is pipeline-safe.

Exit codes:
    0  success
    1  usage error, or an internal failure
    2  completed, but with error-severity diagnostics

The tool-gap record for this instrument writes the invocation as
``compose --items items.jsonl --oracle ./oracle.py --depths 1,2,3,5,8``. That shape is
kept as a verb rather than as the script name, because ``compose`` is too generic a name
to claim on PATH: ``nonius compose --items ...``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

if TYPE_CHECKING:  # imports are deferred at runtime so --help stays fast
    from nonius.archive import Archive
    from nonius.model import Item
    from nonius.oracle import Oracle, Realizer


class _Parser(argparse.ArgumentParser):
    """argparse exits 2 on a usage error; here 2 means 'ran, found problems'."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        raise SystemExit(1)


def _depths(raw: str) -> tuple[int, ...]:
    try:
        out = tuple(int(x) for x in raw.split(",") if x.strip())
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a comma-separated depth list: {raw!r}") from None
    if not out or any(d < 1 for d in out):
        raise argparse.ArgumentTypeError("depths must be positive integers")
    return out


def _load_inputs(
    args: argparse.Namespace,
) -> tuple[tuple[Item, ...], Oracle, Archive | None]:
    from nonius import manifest
    from nonius.archive import load as load_archive
    from nonius.oracle import load_callable

    items = manifest.load(args.items)
    oracle: Oracle = load_callable(args.oracle)  # type: ignore[assignment]
    archive = load_archive(args.archive) if getattr(args, "archive", None) else None
    return items, oracle, archive


def _cmd_audit(argv: Sequence[str]) -> int:
    p = _Parser(prog="nonius audit", description="Can this benchmark be composed, and how far?")
    p.add_argument("--items", required=True, help="item manifest (JSONL)")
    p.add_argument("--oracle", required=True, help="module:attr or path.py:attr")
    p.add_argument("--archive", help="per-item verdict archive (JSONL/.gz/CSV), optional")
    p.add_argument("--depths", type=_depths, default=(1, 2, 3, 5, 8))
    p.add_argument("--probe-cap", type=int, default=64)
    p.add_argument("--path-cap", type=int, default=10_000)
    p.add_argument("--sample", type=int, default=20_000)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = p.parse_args(list(argv))

    from nonius.audit import audit

    items, oracle, archive = _load_inputs(args)
    report = audit(
        items,
        oracle,
        archive=archive,
        depths=args.depths,
        probe_cap=args.probe_cap,
        path_cap=args.path_cap,
        sample=args.sample,
        seed=args.seed,
    )
    print(report.to_json() if args.json else report.render())

    errors = [d for d in report.diagnostics if d.severity == "error"]
    for d in errors:
        print(f"error: {d.code}: {d.message}", file=sys.stderr)
    return 2 if errors else 0


def _cmd_compose(argv: Sequence[str]) -> int:
    p = _Parser(prog="nonius compose", description="Emit depth-graded composite items.")
    p.add_argument("--items", required=True, help="item manifest (JSONL)")
    p.add_argument("--oracle", required=True, help="module:attr or path.py:attr")
    p.add_argument(
        "--realizer",
        help="module:attr for a benchmark-native realizer; "
        "omitted uses the default slotted-prompt realizer",
    )
    p.add_argument("--archive", help="per-item verdict archive, for strata")
    p.add_argument("--depths", type=_depths, default=(2, 3))
    p.add_argument("--limit", type=int, default=500, help="max composites per depth")
    p.add_argument("--probe-cap", type=int, default=64)
    p.add_argument("--path-cap", type=int, default=10_000)
    p.add_argument("--out", help="write JSONL here instead of stdout")
    p.add_argument(
        "--export",
        choices=("nonius", "lm-eval", "inspect"),
        default="nonius",
        help="output shape: nonius records, an lm-evaluation-harness dataset, "
        "or an Inspect AI dataset",
    )
    p.add_argument(
        "--language",
        default="text",
        help="which rendering to export (adapter-defined; the default realizer emits 'text')",
    )
    args = p.parse_args(list(argv))

    from nonius.audit import constructible, singletons
    from nonius.canonical import canonical_json
    from nonius.compose import analyze, composite_record, realize
    from nonius.manifest import index
    from nonius.model import Diagnostic
    from nonius.oracle import load_callable
    from nonius.realize import make_prompt_realizer

    items, oracle, archive = _load_inputs(args)
    idx = index(items)
    realizer: Realizer = (
        load_callable(args.realizer)  # type: ignore[assignment]
        if args.realizer
        else make_prompt_realizer(oracle)
    )

    analysis = analyze(items, oracle, probe_cap=args.probe_cap)
    if not analysis.live:
        print(
            "refusing to compose: no live link exists in this item set. "
            "Run `nonius audit` for the reasons.",
            file=sys.stderr,
        )
        return 2

    records: list[dict[str, object]] = []
    problems = 0
    # Deduplicated and insertion-ordered, so stderr is deterministic under any hash seed.
    # These are the realizer's own disclosures -- notably that its gold-agreement check is
    # vacuous -- and dropping them on the floor would make the tool quieter than honest.
    disclosures: dict[tuple[str, str], Diagnostic] = {}
    for depth in args.depths:
        available_chains = (
            singletons(items) if depth == 1 else constructible(analysis, depth, cap=args.path_cap)
        )
        pool = available_chains[: args.limit]
        for chain in pool:
            strata = (
                tuple(archive.stratum(c) for c in chain.components)
                if archive is not None
                else ()
            )
            try:
                composite, diags = realize(chain, idx, oracle, realizer, strata=strata)
            except Exception as exc:  # noqa: BLE001 - refusal is the point; report it
                problems += 1
                print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
                continue
            for d in diags:
                disclosures.setdefault((d.code, d.message), d)
            records.append(composite_record(composite))

    for d in disclosures.values():
        print(f"{d.severity}: {d.code}: {d.message}", file=sys.stderr)

    if args.export == "nonius":
        payload = "".join(canonical_json(r) + "\n" for r in records)
    else:
        from nonius.adapters.harness import EXPORTERS

        payload = EXPORTERS[args.export](records, language=args.language)
        # An exporter drops any composite lacking the requested rendering. Silently
        # emitting a short dataset that still looks plausible is the worse failure, so
        # the shortfall is reported and a total wipeout is an error.
        exported = len([x for x in payload.splitlines() if x.strip()])
        if exported < len(records):
            available: set[str] = set()
            for r in records:
                rendering = r.get("rendering", {})
                if isinstance(rendering, dict):
                    available.update(str(k) for k in rendering)
            print(
                f"error: {len(records) - exported} of {len(records)} composites have no "
                f"{args.language!r} rendering and were dropped; this realizer emits "
                f"{sorted(available) or ['(nothing)']}. Pass --language to pick one.",
                file=sys.stderr,
            )
            problems += 1
    lines = payload.splitlines()
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
        print(f"wrote {len(lines)} composites to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(payload)
    return 2 if problems else 0


def _cmd_run(argv: Sequence[str]) -> int:
    """Plan a paid run. Spends nothing: there is no code path here that can."""
    p = _Parser(
        prog="nonius run",
        description="Plan a run of composites against systems. Prints the plan and exits.",
    )
    p.add_argument("--composites", required=True, help="composite JSONL from `nonius compose`")
    p.add_argument("--prereg", required=True, help="pre-registration TOML")
    args = p.parse_args(list(argv))

    from nonius.errors import ManifestError
    from nonius.run import load_preregistration, plan

    prereg = load_preregistration(args.prereg)
    records = []
    for n, line in enumerate(
        Path(args.composites).read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ManifestError(f"{args.composites} line {n}: {exc}") from exc
    print(plan(prereg, records))
    print(
        "\nThis verb cannot spend. Executing a run means calling nonius.run.execute() "
        "from your own code, with your own model client, authorised=True, and a "
        "pre-registration whose status you have deliberately set to 'authorised'.",
        file=sys.stderr,
    )
    return 0


def _cmd_spec(argv: Sequence[str]) -> int:
    p = _Parser(prog="nonius spec", description="The versioned composition rulings.")
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser("version")
    sub.add_parser("list")
    show = sub.add_parser("show")
    show.add_argument("id")
    args = p.parse_args(list(argv))

    from nonius.spec.registry import all_rulings, get, spec_version

    if args.action == "version":
        print(spec_version())
    elif args.action == "list":
        for r in all_rulings():
            flag = "" if r.status == "active" else f" [{r.status}]"
            print(f"{r.id}  {r.title}{flag}")
    else:
        r = get(args.id)
        print(f"{r.id}  ({r.status}, since spec {r.since_spec})")
        print(f"\n{r.title}\n")
        print(r.statement.strip())
        if r.rationale.strip():
            print("\nRationale:\n")
            print(r.rationale.strip())
        if r.examples:
            print("\nCorpus cases: " + ", ".join(r.examples))
        if r.superseded_by:
            print(f"\nSuperseded by: {r.superseded_by}")
    return 0


def _cmd_env(argv: Sequence[str]) -> int:
    """The calibration plate: what a bug report or a paper should quote."""
    p = _Parser(prog="nonius env")
    p.parse_args(list(argv))

    import platform

    from nonius._version import __version__
    from nonius.compose import PROBE_INT
    from nonius.spec.registry import all_rulings, spec_version

    print(f"nonius        {__version__}")
    print(f"spec          {spec_version()}  ({len(all_rulings())} rulings)")
    print(f"probe_int     {','.join(str(x) for x in PROBE_INT)}")
    print(f"python        {platform.python_version()} ({platform.python_implementation()})")
    print(f"platform      {platform.system()} {platform.machine()}")
    return 0


def _cmd_cite(argv: Sequence[str]) -> int:
    p = _Parser(prog="nonius cite")
    p.add_argument("--format", choices=("text", "bibtex"), default="text")
    args = p.parse_args(list(argv))

    from nonius._version import __version__
    from nonius.spec.registry import spec_version

    if args.format == "bibtex":
        print(
            "@software{nonius,\n"
            "  title  = {nonius: a benchmark composer and composability audit},\n"
            "  author = {Kurath},\n"
            f"  version = {{{__version__}}},\n"
            f"  note   = {{composition spec {spec_version()}}},\n"
            "  url    = {https://github.com/KurathSec/nonius}\n"
            "}"
        )
    else:
        print(
            f"nonius {__version__} (composition spec {spec_version()}). "
            "https://github.com/KurathSec/nonius"
        )
    return 0


_VERBS = {
    "audit": _cmd_audit,
    "compose": _cmd_compose,
    "run": _cmd_run,
    "spec": _cmd_spec,
    "env": _cmd_env,
    "cite": _cmd_cite,
}


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__.strip().splitlines()[0])
        print("\nusage: nonius {audit,compose,run,spec,env,cite} ...\n")
        print("  audit    can this benchmark be composed, and how far (free, no model calls)")
        print("  compose  emit depth-graded composite items")
        print("  run      plan a paid run against systems (prints the plan; spends nothing)")
        print("  spec     the versioned composition rulings")
        print("  env      version and configuration, for bug reports and papers")
        print("  cite     how to cite this tool")
        return 0

    if args[0] in ("-V", "--version"):
        from nonius._version import __version__

        print(__version__)
        return 0

    verb = args[0]
    if verb not in _VERBS:
        print(
            f"nonius: error: unknown verb {verb!r}; expected one of "
            f"{', '.join(sorted(_VERBS))}",
            file=sys.stderr,
        )
        return 1

    from nonius.errors import NoniusError

    try:
        return _VERBS[verb](args[1:])
    except NoniusError as exc:
        print(f"nonius {verb}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"nonius {verb}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
