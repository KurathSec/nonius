# Operating instructions for Claude Code

What the tool is and how to use it: `README.md`. Why it is built this way: `ARCHITECTURE.md`.
What changed and when: `CHANGELOG.md`. **This file does not repeat any of them.**

Treat `ARCHITECTURE.md` as authoritative when it disagrees with anything else, **except
code. When code and prose disagree, the code is right and the prose is a bug.**

## Commands

```
.venv/bin/pytest                       # the whole suite, all offline
.venv/bin/ruff check src tests tools
.venv/bin/mypy                         # --strict over src/nonius, a hard gate
.venv/bin/python tools/update_snapshot.py --check
NONIUS_SPAGHETTI_HOME=/path/to/Spaghetti-Architect \
  .venv/bin/python validation/spaghetti_audit/run.py
```

## The three mechanical gates (never work around them)

1. `tests/test_spec_drift.py`: composition drift. A changed decision is red until
   `tools/update_snapshot.py --confirm-spec-bump` is run *after* a real spec MAJOR bump in
   `src/nonius/spec/rulings/index.toml`. The tool refuses a bump that did not happen.
2. `tests/test_spec_coverage.py`: every active ruling is exercised, every example cites
   back, every ruling id in `src/` resolves. `UNCOVERED` is shrink-only and is empty.
3. `tests/test_layering.py`: the core never imports the subject benchmark, and the
   adapter never opens a file for writing.

**Rulings are never edited into new meanings.** Supersede with a new id.

## Spaghetti Architect is read-only, always

`/home/kureist/Spaghetti-Architect` is a separate project. nonius reads it and never
writes to it. No file, no cache, no temp artifact inside its tree. Check with
`git -C <that repo> status --porcelain` before and after any work that touches the adapter.
The claim boundary in both directions is in `NOTICE`; do not blur it.

## Honesty invariants (encoded in types and tests, keep them that way)

- The audit **refuses** and explains. `not_composable` is a correct and useful answer
  rather than a failure to be worked around by loosening a ruling.
- Any bound applied to a search is reported next to what it withheld. Never truncate
  silently.
- The gold-agreement check is vacuous for a realizer that computes gold by chaining; that
  is stated in a diagnostic. Do not remove the diagnostic to make the output look cleaner.
- The quarantine ceiling is a required parameter. A default would let the gate confirm
  itself.
- Predicted and measured rows are labelled and never mixed.
- Outputs contain no timestamps. A `Date`-like call or a hash-order dependence breaks
  `tests/test_determinism.py`.

## Calibration corpus

`tests/corpus/` is a fixture, **not** a benchmark, and nothing derived from it is a finding
about any model. Expected values are hand-computed with the arithmetic shown in `notes`;
integers assert exactly. A case whose numbers cannot be checked on paper does not belong.

## Numbers in prose

Every number in `README.md`, `ARCHITECTURE.md` and `docs/` traces to exactly one of three
places, and none of them is a person's memory:

- `validation/spaghetti_audit/derived/`: the reference audit's artifacts;
- the calibration corpus and its snapshot, for anything about `tests/corpus/`;
- a command you can re-run, quoted verbatim (`nonius env`, `nonius audit ...`).

**Never hand-edit a number into the prose.** Fix the code or the spec, re-run the harness,
and let the artifact carry it. A figure with no such provenance does not belong in a
sentence. That includes the type-compatible-pair count, which comes from re-running the
analysis rather than from a stored file.

## `paper/` is LOCAL ONLY

Gitignored, zero tracked files, and excluded from the sdist as a second fence. Do not
`git add` anything under it and do not quote it into a tracked file.
