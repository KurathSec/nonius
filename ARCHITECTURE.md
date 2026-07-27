# Architecture

Why nonius is built this way. Module docstrings cite the numbered sections below, and
`tests/test_spec_coverage.py` checks that every ruling id they mention resolves.

When this document and the code disagree, **the code is right and this is a bug.**

---

## 1. What the instrument is for

A saturated benchmark is kept because every historical comparison was computed against it.
Switching costs comparability; staying costs signal. nonius composes the items you already
have into harder ones whose gold is a deterministic function of the component golds, so
the instrument gets harder without becoming a different instrument.

That is the easy half. The hard half is that **most benchmarks cannot be composed**, and
the reason is not the one anybody expects. So the audit — the free pre-flight that says no
and explains why — is a first-class output rather than a diagnostic.

## 2. Layering, enforced rather than agreed

```
   manifest ──┐
   oracle   ──┼──▶  compose  ──▶  audit / bound / bridge / resolution
   archive  ──┘         │
                        └──▶  realize (default)  |  adapters/*.py (native)
```

The core is benchmark-agnostic and **must run with no benchmark installed**. Exactly one
module may name a specific benchmark — `adapters/spaghetti.py` — and it is the only one
ruff's `banned-module-level-imports` exempts.

This is not tidiness. The entire contribution is that the operator is factored *out* of
the benchmark it was demonstrated on; if the core imported that benchmark, the factoring
would be a claim in a README rather than a property of the code. `tests/test_layering.py`
checks it by walking the AST of every core module, and separately checks that the adapter
contains no call that could write to the project it reads.

## 3. The data model, and the one hard precondition

An item is: an id, typed named input **slots**, typed named **results**, an optional
stratum label, and an opaque payload the core never inspects.

Two callables come from the practitioner:

- **oracle** `(item, bindings) -> results`. Bindings are *overrides*: a slot named in
  `bindings` replaces the item's own value, everything else keeps it. This is the hard
  precondition and the instrument's main limit on reach. A benchmark whose gold is a
  stored constant with no program behind it cannot be composed, because there is nothing
  to re-run under a changed binding. That excludes most multiple-choice suites and every
  human-labelled set.
- **realizer** `(components, links) -> Realization`. The recorded specification for this
  instrument named three things an item must declare and omitted this one, but a composer
  cannot work without it: saying "this slot's value is that item's answer" *without
  printing the value* is exactly the operation that makes a chain bind, and only the
  benchmark knows how to say that in its own presentation.

## 4. Versioned rulings

A ruling is one decision, written down, given an immutable id, and cited from the code
that implements it. `require()` raises at import on a phantom id, so a citation cannot rot
into a lie. Spec semver is independent of the package version; a decision that changes an
existing value is a spec MAJOR.

Rulings are never edited into new meanings. A ruling is superseded by a new id, with the
old one keeping `status = "superseded"` and naming its successor.

## 5. Errors

One base class, `NoniusError`; nothing else escapes the public facade. There is no logger.
Diagnostics are a typed, data-carrying output with a closed code set, printed to stderr by
the CLI and carried in the audit report as data.

## 6. Composition, in three refusable stages

### 6.1 Analysis — the stage that does the work

Enumerate every type-compatible substitution (LINK-ALL-0001), then decide which are
**live**: a link is admissible only if the downstream's answer varies as the substituted
slot ranges over the upstream result's codomain (LINK-ALL-0002).

This is the load-bearing idea. Type compatibility is necessary and nowhere near
sufficient. Measured on the reference corpus, 32.2% of ordered item pairs are
type-compatible and **7.0%** carry a live link. A dead link is not a harmless one: the
downstream answer does not depend on the upstream answer, so a system can skip the
upstream component and still be scored correct — and that composite will then exceed its
own independence product bound and be quarantined. A composer that checks types alone
manufactures quarantine faster than it manufactures difficulty.

### 6.2 Construction

Chains are DAGs, not only paths. **Fan-in** — several upstream components feeding distinct
slots of one downstream component — raises component count without lengthening the longest
path (DEPTH-ALL-0002). On a corpus whose link graph is shallow it is the only way to reach
higher depths without authoring items. Depth means component count; path depth is reported
separately and the two are never conflated.

### 6.3 Realization, and the two by-construction checks

- **Literal suppression** (EMIT-ALL-0001). No linked slot may survive as a literal binding.
  The obvious reading of "substitute the answer into the input literals of the next item"
  produces exactly this bug, and it is fatal rather than cosmetic: the answer is printed,
  the system reads it, and the whole emitted set beats its own bound.
- **Gold agreement** (EMIT-ALL-0002). The realization's gold must equal the gold from
  evaluating components one at a time in topological order.

The second check has force only when the realizer reaches the gold by an independent
route. The default prompt realizer chains the component oracles, which is the same
computation the check uses as its reference — so for that realizer the check is vacuous,
and nonius *says so* with an info diagnostic rather than letting a tautology read as
evidence. The Spaghetti Architect adapter merges the components into one program and takes
the gold from that program's own oracle, and there the check is real.

## 7. The archive

`(system, item, draw, verdict)`. Optional. It buys difficulty strata, the product
prediction, and the replicate noise band. **It never decides correctness** — that comes
from the composed gold and nothing else.

## 8. The bound, and its way of being self-serving

Under independence, composite accuracy is the product of component accuracies. That is the
null a measurement is read against, never the gold.

The rule has one direction with teeth: measured accuracy exceeding the product by more
than the noise band means the chain did not bind, and the item is quarantined as invalid
rather than counted as a success. It also has an obvious failure of nerve — if items that
beat the bound are discarded and items that match it are called confirmation, the gate can
only ever confirm itself. So the quarantine ceiling is a **required parameter with no
default**, declared before measurement and printed next to the observed rate.

## 9. Resolution

Per depth: each system's accuracy, the dead/floored/discriminating fractions, the top-two
gap, and `m*` — the widest 95% bootstrap interval on any system's mean, below which a
difference is inside the instrument's own noise and must not be reported as a difference.

Predicted and measured rows are labelled and never mixed. A predicted row cannot detect a
shortcut, because a shortcut is by definition a departure from the model it uses.

## 10. The bridge

A historical singleton score read on the composed scale (`p ** d`) and a composed score
read on the old one (`c ** (1/d)`), with the residual between predicted and measured shown
next to them. An arithmetic re-expression under a stated assumption, not a proof of
measurement equivalence. The residual column exists so a failure of the assumption is
visible rather than buried.

## 11. The audit

No model calls, no composites emitted, nothing spent. Link graph, live edges, maximum
constructible component count, per-family reachability, and — with an archive — the
predicted resolution on the **constructible** population. Verdict:
`not_composable` / `composable_to_depth_k` / `composable`, always with reasons.

Predictions are computed on composites the link graph can actually build (AUDIT-ALL-0002).
A uniform prediction describes items the composer cannot emit; on the reference corpus the
two agree to three decimal places on the discriminating fraction at depth 3 while
differing 4.6-fold on the between-system gap.

Every bound the audit applies to its own search — probe cap, path cap, sample size,
diagnostic cap — is reported alongside what it withheld. A silently truncated search reads
as "covered everything" when it did not.

## 12. Adapters

`adapters/spaghetti.py` is the reference adapter and the isolation seam.
`adapters/harness.py` exports composites as lm-evaluation-harness and Inspect AI datasets,
so composites run inside the harness the practitioner already uses — a composite that only
ran inside nonius would be a new instrument by another route.

The merged composite program is constructed as a frozen dataclass rather than through the
subject project's `parse()`, because that parser requires every operand to be an *input*
and a composite's whole point is that one operand is another operation's result. Nothing
is patched: nonius restates the invariants `parse()` would have checked that still apply,
and then verifies the result by compiling and running it.

## 13. Spending

`run.py` is the only module that can cost money, and it refuses by default: it needs a
pre-registration that declares a quarantine ceiling, an explicit `authorised=True`, and a
pre-registration whose status was deliberately set to `authorised`. The `nonius run` verb
has no code path that can spend at all — it prints the plan.

nonius ships no model client. The caller supplies `complete(prompt) -> str`.

## 14. Determinism

Sorted keys, floats quantized to 12 significant digits, no timestamps, no hash-order
dependence. Tested across processes under two `PYTHONHASHSEED` values. The claim is
per-platform; cross-OS byte-identity is not claimed.

## 15. The three gates

1. **Composition drift** — a full value snapshot of every link verdict and composite gold
   on the calibration corpus, stamped with the spec version. `tools/update_snapshot.py` is
   the only way to move it and refuses without a real spec MAJOR bump; a deleted case
   counts as a change, so "delete, regenerate, re-add" is closed off.
2. **Ruling coverage** — every active ruling is exercised by a calibration case or by a
   named test, every example cites back, and every ruling-id-shaped string in `src/`
   resolves, including in comments.
3. **Layering** — the core never imports the subject benchmark, and the adapter never
   writes.
