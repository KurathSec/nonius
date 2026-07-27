# Contributing

## Setup

```
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest && .venv/bin/ruff check src tests tools && .venv/bin/mypy
```

Zero runtime dependencies, and that is a constraint rather than a coincidence. Standard
library only in `src/nonius/`. If a change needs a third-party package, it needs a
discussion first.

## The three gates

They are described in `ARCHITECTURE.md` §15 and enforced in CI. Do not work around them.

## Adding a ruling

A ruling is one decision, with an immutable id, cited from the code that implements it.

1. Add a `[[ruling]]` stanza to the right file in `src/nonius/spec/rulings/`. Ids are
   `{TOPIC}-ALL-{NNNN}` and are never reused.
2. Cite it from the implementing code with `require("...")` at module import, so a typo
   fails at import rather than in review.
3. Add a calibration case that exercises it, or — if the ruling is a refusal with no value
   to compute — a named test, and add it to `TEST_COVERED` in
   `tests/test_spec_coverage.py`.
4. Bump the spec MINOR in `src/nonius/spec/rulings/index.toml` and add a changelog stanza.

## Superseding a ruling

**A ruling id is immutable forever**: changing what an existing id *means* silently
rewrites the history of every number ever published under it. Once a ruling is superseded
its text is frozen outright, and `tests/test_spec_coverage.py` pins a digest of it.

The one exception, stated in `ARCHITECTURE.md` §4: a ruling authored in the *current
unreleased* spec cycle may still be amended in place, with the amendment recorded in that
cycle's changelog stanza. What immutability protects is a meaning someone could already
have published a number under.

On the old stanza, add exactly two fields and change nothing else:

```toml
status = "superseded"
superseded_by = "LINK-ALL-0007"
```

The spec level is **not** decided by the supersession. It is decided by the drift gate: if
any existing corpus value moved, it is a MAJOR; if none did, it is a MINOR.

## Adding a calibration case

`tests/corpus/cases/<id>.toml`, with the shared item set in `tests/corpus/items.jsonl`.

- Expected values are **hand-computed, with the arithmetic shown in `notes`**. A case whose
  numbers cannot be checked on paper is a snapshot, not calibration, and the test suite
  rejects it.
- Integers assert exactly. Floats carry a declared tolerance.
- The case names the rulings it exercises, and those rulings must cite it back.

Then run `tools/update_snapshot.py`. Adding new values needs no flag; a new case cannot
rewrite the history of an old one.

## Adding an adapter

An adapter supplies `items()`, an `oracle`, optionally a native `realizer`, and optionally
an `archive`. It lives in `src/nonius/adapters/` and is the **only** place a specific
benchmark may be *imported*. Naming one in prose is fine; what is enforced is the import
graph.

If it reads someone else's repository, it reads it read-only, and `tests/test_layering.py`
will check that structurally: no `open(..., "w")`, no `write_text`, no `mkdir`, no
`shutil` mutation.

## House style

- `from __future__ import annotations` everywhere; frozen, slotted dataclasses; tuples not
  lists in result types.
- Module docstrings are design rationale and cite `ARCHITECTURE.md` sections and ruling
  ids. Function docstrings are one line, usually carrying the ruling.
- Comments explain **why not** as much as why. The most useful comment names the failure it
  prevents.
- No logger. Diagnostics are a typed output with a closed code set.
- No timestamps, no hash-order dependence, no unseeded randomness.

## Commits

Lowercase `area: imperative summary`, with a body that states what was wrong and what
evidence shows it is fixed.
