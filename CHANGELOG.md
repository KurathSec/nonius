# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Because nonius is a measurement instrument, every release entry states **two versions**
rather than one: package and composition spec. A composition spec MAJOR means some
**recorded value** changed, which is the drift gate's definition and the only one that can
be checked mechanically. Usually that is a decision the composer makes, and then numbers published
under the old spec are not comparable to numbers under the new one. It can also be a
recorded citation label, which moves when a ruling is superseded without any measured
quantity changing. The stanza for each MAJOR says which kind it was; 2.0.0 is the second
kind.

## [Unreleased]

Nothing yet.

## [0.2.0] - 2026-08-03

- package 0.2.0 · spec 2.0.0

No recorded value changed; the drift snapshot is untouched. A second reference subject,
and the defects it forced out of the core.

### Added

- **EvalPlus adapter** (`nonius.adapters.evalplus`) and a sandboxed out-of-process worker:
  HumanEval+ as a second reference subject, one this project's author did not build. The
  adapter admits 109 of 164 items (plain positional signatures, scalar results; two named
  exclusions) and its realizer reaches the gold by merged-source execution, so the
  gold-agreement check is not vacuous for it.
- **The second reference audit** (`validation/evalplus_audit/`): the funnel it measured
  (3764 type-compatible → 2564 decidable → 2279 live → 1835 emittable) names a stage the
  first subject could not expose — a live link whose piped value the downstream *contract*
  refuses. Liveness is necessary and not sufficient for emission, exactly as type
  compatibility is necessary and not sufficient for liveness.
- **A six-system verdict archive for the second subject** (196797 verdicts regraded from
  EvalPlus's 2023 sample release; no inference bought). `build_archive.py --emit` rebuilds
  the committed archive byte-for-byte from committed grades; `--check` tests consistency
  with EvalPlus's published pass@1 (ordering reproduced; every value below its greedy
  figure) and is documented as consistency, not verification.
- **Population-labelled readouts**: `DepthReadout.population` and
  `singleton_row(..., restrict_to=...)`. The depth-1 baseline used to average over every
  archive item while composed rows drew from the live-link subset; both rows are now
  emitted and labelled (`predicted/all`, `predicted/composable`). The correction reverses
  sign between the two reference subjects, which is why it is a row and not a caveat.
- **`search_paths`**: path enumeration with an explicit work budget and an exhaustiveness
  flag. `cap` bounds results, not work; proving "nothing at this depth" exhausts every
  shorter node-distinct path, which on the second subject's graph does not terminate. An
  abandoned search now reports `composable` (capped) rather than publishing a budget as a
  property of the benchmark.
- **Layering gate for bytecode**: the subject checkout must stay free of our `__pycache__`;
  every adapter import of the subject must sit inside the no-bytecode guard. Two `.pyc`
  files had leaked before the guard existed; the gate keeps the repair permanent.

### Fixed

- **`Archive` accessors indexed**: every accessor rescanned the full verdict tuple, which
  is invisible on small fixtures and quadratic on a real archive — the second subject's
  depth-graded audit ran five hours at full CPU without finishing. One pass now builds
  `(system, item) → draws`; values verified identical on all 984 cells. Gated by a
  traversal-count test, not a clock, because a timing threshold is exactly what missed it.
- `m_star` no longer crashes rendering when no interval exists; the cell prints `n/a`.
- Batch failures in the archive build are regraded one worker per draw, so a single
  misbehaving completion costs one verdict rather than 200; incomplete batches are named
  in `incomplete.json` and retried on resume.

### Docs

- `docs/honesty.md` carries the second subject: the emission stage, the panel-dependence
  of difficulty strata (zero dead items under a panel containing GPT-J), the vacuity of an
  all-predicted readout, and the depth-1 population defect with its reversing sign.
- The retraction wording now matches the artifact: the seven informative cells left the
  headline unsupported rather than contradicted.

## [0.1.0] - 2026-07-28

- package 0.1.0 · spec 2.0.0

First working shape. The composer, the composability audit, the independence-product
bound with its quarantine rule, the bridge table, the resolution readout, a
benchmark-agnostic manifest, a default slotted-prompt realizer, a read-only reference
adapter, and exporters for lm-evaluation-harness and Inspect AI.

Composition spec 0.1.0 fixes three decisions that the surrounding literature leaves
implicit, and the middle one is the reason this release exists at all:

- **Depth counts components rather than links** (DEPTH-ALL-0003). The two readings differ by one
  item and the difference shows up in published arithmetic.
- **A link is admissible only if it is live** (LINK-ALL-0007). Type compatibility is
  necessary and nowhere near sufficient. On the reference corpus 32.2% of ordered item
  pairs are type-compatible and 7.0% carry a live link. A dead link costs dependence
  rather than difficulty: both components must still be answered, so the composite sits
  exactly on its product bound and the validity gate never flags it. It is simply a
  conjunction of items rather than a chain.
- **A substituted slot must not survive as a literal** (EMIT-ALL-0001). Printing the
  upstream answer into the downstream's presentation makes the chain fake, and is what the
  obvious reading of "substitute into the input literals" produces.

The reference audit in `validation/spaghetti_audit/` reports a real benchmark that the
operator largely declines to compose, and says why. No paid run has been executed;
`preregistration/run-01.toml` is designed and unexecuted.

Composition spec 1.0.0, 1.1.0 and 2.0.0 correct five rulings, all before anything was
released, and the corrections are themselves worth recording. An adversarial review of the
whole project found that: the audit's headline component count was called a maximum when it
is a floor over two enumerated shapes (AUDIT-ALL-0005); depth was said to determine the link
count, true only of a path (DEPTH-ALL-0003); hashing the spec version into a composite id
moved every id on an editorial patch (EMIT-ALL-0005); the stated reason for the liveness
rule, the project's headline argument, was wrong, because a dead-link composite does not
beat its product bound (LINK-ALL-0007); and the gold-agreement rule called its two
computations independent when they are only independent for a realizer that reaches the
gold independently, which the default one does not (EMIT-ALL-0006). Each is superseded with
a corrected successor rather than edited. See `src/nonius/spec/rulings/index.toml`.
