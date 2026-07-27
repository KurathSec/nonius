## What and why

<!-- What was wrong, and what evidence shows it is fixed. -->

## Gate checklist

- [ ] **No calibration value changed**, or this PR bumps the spec MAJOR in
      `src/nonius/spec/rulings/index.toml` and regenerates the snapshot with
      `tools/update_snapshot.py --confirm-spec-bump`.
- [ ] Every new composition decision is a **TOML ruling with a new immutable id**, cited
      from the code with `require()`, and exercised by a calibration case or a named test.
- [ ] No number was hand-edited into prose. Numbers come from
      `validation/spaghetti_audit/derived/`.
- [ ] `docs/spec/rulings.md` regenerated with `tools/render_rulings.py`.
- [ ] Nothing outside this repository was modified. If the adapter was touched:
      `git -C <subject repo> status --porcelain` is unchanged.
