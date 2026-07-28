"""The README's audit transcript must be what the tool actually prints.

Round 7 added a column to ``AuditReport.render()`` and left the README showing the old
three-column table -- presented, as it still is, as verbatim console output. The block is
otherwise an exact copy of the reference render, so nothing but a check like this one
distinguishes "deliberately elided" from "stale paste". The omitted column was the
disclosure that 98% of the depth-5 pool is one family, which is precisely the thing the
table would otherwise be read as evidence against.

Offline and file-only: it compares two committed files and regenerates nothing.
"""

from __future__ import annotations

from conftest import ROOT

REPORT = ROOT.parent / "validation" / "spaghetti_audit" / "derived" / "audit_report.md"
README = ROOT.parent / "README.md"


def _fenced(text: str, opener: str) -> list[str]:
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == opener)
    end = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == "```")
    return lines[start + 1 : end]


def test_the_readme_audit_transcript_is_the_real_render() -> None:
    # The README fence opens with the `$ ...` invocation, which is not render output.
    transcript = _fenced(README.read_text(encoding="utf-8"), "```console")
    assert transcript and transcript[0].startswith("$ nonius audit"), (
        "the README's first console fence is expected to be the audit transcript"
    )
    body = [line.rstrip() for line in transcript[1:]]

    render = [line.rstrip() for line in _fenced(REPORT.read_text(encoding="utf-8"), "```")]

    # The README shows a prefix of the render (it stops before the readout table).
    assert body == render[: len(body)], (
        "README.md's audit transcript is not what the tool prints. Do not retype it -- "
        "re-paste it from the fenced block in "
        "validation/spaghetti_audit/derived/audit_report.md, which the harness writes.\n"
        f"first difference at transcript line {next((i for i, (a, b) in enumerate(zip(body, render, strict=False)) if a != b), len(body))}"
    )
