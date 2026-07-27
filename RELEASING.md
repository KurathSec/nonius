# Releasing

## Per release

1. **Check the stamps the committed artifacts carry**, not whether their inputs changed.
   - `.venv/bin/python tools/update_snapshot.py --check` reports nothing changed.
   - `validation/spaghetti_audit/derived/audit.json` carries the current
     `provenance.nonius_spec`. If it does not, re-run the harness and commit the result.
   Keying this step off the *inputs* is the mistake that is easy to make twice.
2. `.venv/bin/pytest && .venv/bin/ruff check src tests tools && .venv/bin/mypy` — all green.
3. Move the `## [Unreleased]` section of `CHANGELOG.md` to `## [X.Y.Z]`, stating both
   versions (package and composition spec), and open a fresh `## [Unreleased]`.
4. Set `__version__` in `src/nonius/_version.py` to `X.Y.Z` with no `dev` suffix.
5. Commit, tag `vX.Y.Z`, push the tag. The release workflow does the rest.

The tag job refuses unless: the tag is an ancestor of `main`; the tag equals
`v{__version__}`; the version contains no `dev`; the changelog yields a non-empty section
for it; the sdist ships none of the excluded paths; and the built wheel imports and runs
`nonius env` in a clean venv — the artifact, not `-e .`.

## What deliberately does not happen here

- The composition spec version is **not** bumped by a release. It moves when a decision
  moves, which is a separate, reviewable act with its own gate.
- `CITATION.cff` is never version-bumped; the archival service supplies version and date.
- The reference audit is not re-run automatically. It reads a third-party checkout at a
  recorded commit, and silently re-running it against a different commit would change a
  published number without anyone deciding to.

## On a partial failure

Use "Re-run failed jobs", never "Re-run all jobs": publishing is idempotent per artifact,
and re-running everything can republish an artifact that already succeeded.
