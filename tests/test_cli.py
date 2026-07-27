"""The CLI contract: exit codes, stream discipline, and the verbs.

Driven through ``main()`` rather than a subprocess where possible, so a failure points at
the code rather than at a shell.
"""

from __future__ import annotations

import json

import pytest
from conftest import CORPUS

from nonius.cli import main

ITEMS = str(CORPUS / "items.jsonl")
ORACLE = "oracle:answer"


def test_help_and_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "audit" in capsys.readouterr().out
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip()


def test_unknown_verb_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["frobnicate"]) == 1
    assert "unknown verb" in capsys.readouterr().err


def test_missing_required_argument_exits_one() -> None:
    """argparse's own exit code is 2; here 2 means 'ran, found problems'."""
    with pytest.raises(SystemExit) as exc:
        main(["audit", "--oracle", ORACLE])
    assert exc.value.code == 1


def test_audit_json_goes_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["audit", "--items", ITEMS, "--oracle", ORACLE, "--json"]) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["verdict"] == "composable_to_depth_3"
    assert report["items"] == 10
    assert captured.err == ""


def test_audit_human_output_names_the_rulings(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["audit", "--items", ITEMS, "--oracle", ORACLE]) == 0
    out = capsys.readouterr().out
    assert "LINK-ALL-0001" in out and "LINK-ALL-0007" in out
    assert "verdict:" in out


def test_compose_emits_jsonl(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "compose",
                "--items",
                ITEMS,
                "--oracle",
                ORACLE,
                "--depths",
                "2,3",
                "--limit",
                "5",
            ]
        )
        == 0
    )
    lines = [x for x in capsys.readouterr().out.splitlines() if x.strip()]
    assert lines
    for line in lines:
        rec = json.loads(line)
        assert set(rec) >= {"id", "depth", "components", "links", "gold", "spec"}
        assert rec["depth"] == len(rec["components"])
        assert len(rec["links"]) == rec["depth"] - 1


def test_compose_refuses_when_nothing_is_live(
    tmp_path: object, capsys: pytest.CaptureFixture[str]
) -> None:
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    manifest = tmp_path / "dead.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "id": "only",
                "slots": [{"name": "subject", "tag": "int"}],
                "results": [{"name": "verdict", "tag": "str", "codomain": ["high", "low"]}],
                "payload": {
                    "op": "threshold",
                    "subject": 1,
                    "cut": -99999,
                    "hi": "high",
                    "lo": "low",
                    "prompt": "x {subject}",
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    assert main(["compose", "--items", str(manifest), "--oracle", ORACLE]) == 2
    assert "refusing to compose" in capsys.readouterr().err


def test_spec_verbs(capsys: pytest.CaptureFixture[str]) -> None:
    from nonius.spec.registry import spec_version

    assert main(["spec", "version"]) == 0
    # Compared against the registry rather than a literal: a hardcoded version here would
    # have to be edited on every spec bump, which is exactly how a test goes stale.
    assert capsys.readouterr().out.strip() == spec_version()

    assert main(["spec", "list"]) == 0
    listing = capsys.readouterr().out
    assert "LINK-ALL-0007" in listing
    # A retired ruling stays visible and is marked, because it is the record of a decision
    # somebody may hold a number from.
    assert "LINK-ALL-0002  A link is admissible" in listing
    assert "[superseded]" in listing

    assert main(["spec", "show", "LINK-ALL-0007"]) == 0
    shown = capsys.readouterr().out
    assert "Rationale:" in shown
    assert "Corpus cases:" in shown

    # Showing a superseded ruling must name its successor rather than pretend it is live.
    assert main(["spec", "show", "LINK-ALL-0002"]) == 0
    retired = capsys.readouterr().out
    assert "Superseded by: LINK-ALL-0007" in retired


def test_spec_show_rejects_a_phantom_ruling(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["spec", "show", "LINK-ALL-9999"]) == 1
    assert "no such ruling" in capsys.readouterr().err


def test_env_and_cite(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["env"]) == 0
    env = capsys.readouterr().out
    assert "probe_int" in env and "spec" in env

    assert main(["cite", "--format", "bibtex"]) == 0
    assert "@software" in capsys.readouterr().out


def test_bad_oracle_spec_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["audit", "--items", ITEMS, "--oracle", "nosuchmodule:nope"]) == 1
    assert "cannot import" in capsys.readouterr().err
