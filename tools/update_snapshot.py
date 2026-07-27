#!/usr/bin/env python3
"""Regenerate the composition-drift snapshot -- and refuse when that would be dishonest.

This is the only supported way to move ``tests/snapshots/corpus_values.json``. It refuses:

* a missing snapshot file, unless ``--create-baseline`` says so -- deleting it is the same
  laundering route as emptying it, and cheaper;
* any changed existing value without ``--confirm-spec-bump``;
* ``--confirm-spec-bump`` when the spec MAJOR did not actually move -- the flag confirms
  a bump, it does not replace one;
* a deleted case, which is treated as a change, so "delete a case, regenerate, re-add it
  later with different values" is closed off.

Adding new values needs no flag: a new case cannot rewrite the history of an old one.

    python tools/update_snapshot.py [--confirm-spec-bump] [--create-baseline] [--check]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))

from tools_snapshot import compute  # noqa: E402

from nonius.spec.registry import spec_version  # noqa: E402

SNAPSHOT = ROOT / "tests" / "snapshots" / "corpus_values.json"


def _major(version: str) -> int:
    return int(version.split(".")[0])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--confirm-spec-bump",
        action="store_true",
        help="acknowledge that existing decisions changed and the spec MAJOR moved",
    )
    ap.add_argument(
        "--create-baseline",
        action="store_true",
        help="bootstrap a snapshot when none exists; not a way past --confirm-spec-bump",
    )
    ap.add_argument(
        "--check", action="store_true", help="report what would change and write nothing"
    )
    args = ap.parse_args(argv)

    fresh = compute()

    if not SNAPSHOT.is_file():
        # A missing baseline is not an empty one, and it is the cheaper laundering route:
        # with nothing to compare against, every changed value looks like an addition and
        # sails past the bump requirement. Refuse before the --check branch, because a
        # working tree with no snapshot is broken rather than merely unreported.
        if not args.create_baseline:
            print(
                f"refusing: {SNAPSHOT} does not exist. Regenerating from nothing would "
                f"launder any changed decision past the spec MAJOR requirement. Restore it "
                f"from version control; pass --create-baseline only when genuinely "
                f"bootstrapping a new corpus.",
                file=sys.stderr,
            )
            return 1
        if args.check:
            print(f"{SNAPSHOT} does not exist; it would be created")
            return 0
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(fresh, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"created {SNAPSHOT} at spec {fresh['spec_version']}")
        return 0

    old = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    old_values = old["values"]
    new_values = fresh["values"]

    # A snapshot that has been emptied (or nearly so) is the cheap version of the
    # delete-and-regenerate laundering route: with no old values to compare against,
    # every real value looks like an addition and sails through without a bump. Refuse
    # to treat a collapsed baseline as a baseline at all. Note the condition must fire on
    # an EMPTY dict too -- `if old_values and ...` would skip exactly the worst case.
    if new_values and len(old_values) * 2 < len(new_values):
        print(
            f"refusing: the existing snapshot holds {len(old_values)} values against "
            f"{len(new_values)} live ones. A baseline that small cannot detect drift; it "
            f"looks like it was emptied. Restore it from version control.",
            file=sys.stderr,
        )
        return 1

    changed = sorted(
        k
        for k in old_values
        if k in new_values
        and json.dumps(old_values[k], sort_keys=True)
        != json.dumps(new_values[k], sort_keys=True)
    )
    # A removed value is a change: without this, deleting a case and re-adding it later
    # would launder a numeric change past the gate.
    removed = sorted(set(old_values) - set(new_values))
    added = sorted(set(new_values) - set(old_values))

    for key in changed:
        print(f"CHANGED {key}: {old_values[key]!r} -> {new_values[key]!r}")
    for key in removed:
        print(f"REMOVED {key}: {old_values[key]!r}")
    for key in added:
        print(f"added   {key}")

    if changed or removed:
        if not args.confirm_spec_bump:
            print(
                f"\nrefusing: {len(changed)} changed and {len(removed)} removed value(s) "
                f"need a spec MAJOR bump. Bump "
                f"src/nonius/spec/rulings/index.toml, then re-run with "
                f"--confirm-spec-bump.",
                file=sys.stderr,
            )
            return 1
        if _major(spec_version()) <= _major(str(old["spec_version"])):
            print(
                f"refusing: --confirm-spec-bump given, but the spec MAJOR did not move "
                f"({old['spec_version']} -> {spec_version()}). The flag confirms a bump, "
                f"it does not replace one.",
                file=sys.stderr,
            )
            return 1

    if args.check:
        print(
            f"\n{len(changed)} changed, {len(removed)} removed, {len(added)} added "
            f"(nothing written)"
        )
        return 0

    SNAPSHOT.write_text(json.dumps(fresh, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nwrote {SNAPSHOT} at spec {fresh['spec_version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
