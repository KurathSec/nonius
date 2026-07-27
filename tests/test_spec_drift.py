"""Gate 1 of 3: composition drift.

A full snapshot of every decision the composer makes on the calibration corpus, stamped
with the rulings version that produced it. A changed value is red until the snapshot is
deliberately regenerated at a new spec MAJOR, and ``tools/update_snapshot.py`` refuses to
do that without one.

The gate has four teeth, and each one closes a way it could quietly disarm itself.
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import ROOT
from tools_snapshot import compute

from nonius.spec.registry import spec_version

SNAPSHOT = ROOT / "snapshots" / "corpus_values.json"


def _snapshot() -> dict[str, object]:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_snapshot_exists() -> None:
    assert SNAPSHOT.is_file(), (
        f"{SNAPSHOT} is missing; generate it with tools/update_snapshot.py"
    )


def test_snapshot_stamp_matches_live_spec() -> None:
    """The gate may never silently disarm itself.

    A spec bump -- major or minor -- is red until the snapshot is deliberately
    regenerated at the new version.
    """
    assert _snapshot()["spec_version"] == spec_version(), (
        f"snapshot was taken at spec {_snapshot()['spec_version']} but the live spec is "
        f"{spec_version()}; regenerate with tools/update_snapshot.py"
    )


def test_no_unsnapshotted_value() -> None:
    live = compute()["values"]
    stored = _snapshot()["values"]
    assert isinstance(stored, dict)
    missing = sorted(set(live) - set(stored))
    assert not missing, f"values with no snapshot entry: {missing[:10]}"


def test_key_sets_are_equal() -> None:
    """Equality, not containment: a mangled snapshot that lost keys would narrow the gate."""
    live = compute()["values"]
    stored = _snapshot()["values"]
    assert isinstance(stored, dict)
    assert sorted(live) == sorted(stored), (
        f"snapshot key set differs: "
        f"only live {sorted(set(live) - set(stored))[:5]}, "
        f"only stored {sorted(set(stored) - set(live))[:5]}"
    )


def test_no_value_changed() -> None:
    live = compute()["values"]
    stored = _snapshot()["values"]
    assert isinstance(stored, dict)
    version = spec_version()
    for key in sorted(live):
        expected, actual = stored[key], live[key]
        assert json.dumps(expected, sort_keys=True) == json.dumps(actual, sort_keys=True), (
            f"COMPOSITION DRIFT: {key} changed {expected!r} -> {actual!r} under spec "
            f"{version}.\nA changed decision requires a spec MAJOR bump "
            f"(tools/update_snapshot.py --confirm-spec-bump)"
        )


def test_snapshot_is_canonical_bytes() -> None:
    """The file is the artifact; a reformat is a diff nobody can review."""
    raw = SNAPSHOT.read_text(encoding="utf-8")
    assert raw == json.dumps(json.loads(raw), indent=2, sort_keys=True) + "\n"
    assert "\r" not in raw
    assert Path(SNAPSHOT).read_bytes().endswith(b"}\n")
