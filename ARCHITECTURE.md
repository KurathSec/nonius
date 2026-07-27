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
module may *import* a specific benchmark — `adapters/spaghetti.py`. Naming one in prose is
fine and several core modules do; what is enforced is the import graph. Two paths are
exempted from ruff's `banned-module-level-imports`: the adapter, and the layering test
that checks the rest.

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

Rulings are never edited into new meanings once released. A ruling is superseded by a new
id, with the old one keeping `status = "superseded"` and naming its successor. `require()`
refuses a superseded id, so a decision that moves takes its citations with it or the import
fails.

A ruling that **no released version has ever carried** may still be amended in place, and
the amendment is recorded in the changelog stanza of the cycle that makes it — not the one
that authored it. What immutability protects is a meaning someone could already have
published a number under; until a version ships, there is no such meaning. Once superseded,
a ruling's text is frozen outright and `tests/test_spec_coverage.py` pins a digest of it,
because a retired ruling is the record of a decision rather than a draft.

## 5. Errors

One base class, `NoniusError`; nothing else escapes the public facade. There is no logger.
Diagnostics are a typed, data-carrying output with a closed code set, printed to stderr by
the CLI and carried in the audit report as data.

## 6. Composition, in three refusable stages

### 6.1 Analysis — the stage that does the work

Enumerate every type-compatible substitution (LINK-ALL-0001), then decide which are
**live**: a link is admissible only if the downstream's answer varies as the substituted
slot ranges over the upstream result's codomain (LINK-ALL-0007).

This is the load-bearing idea. Type compatibility is necessary and nowhere near
sufficient. Measured on the reference corpus, 32.2% of ordered item pairs are
type-compatible and **7.0%** carry a live link.

What a dead link costs is *dependence*, not difficulty. Every component's results are in
the composite's gold, so both must still be answered and accuracy still tracks the product
— a dead-link composite is not easier and does not beat its bound. It simply is not a
chain: it is a conjunction of items printed together, so depth counts how many items were
stapled into one prompt rather than how far an answer was carried. A composer that checks
types alone emits a set that is four-fifths conjunctions and calls them chains.

### 6.2 Construction

Chains are DAGs, not only paths. **Fan-in** — several upstream components feeding distinct
slots of one downstream component — raises component count without lengthening the longest
path (DEPTH-ALL-0002). On a corpus whose link graph is shallow it is the only way to reach
higher depths without authoring items. Depth means component count and does not determine
the link count (DEPTH-ALL-0003); path depth is reported separately and the two are never
conflated.

Assigning distinct upstreams to a sink's slots is a bipartite matching, so the greedy seed
is repaired by augmenting paths: a first-fit that let an early slot take the only upstream
a later slot could have used would abandon fan-ins that exist.

**What construction enumerates.** Paths and single-sink fan-ins, and nothing else.
A mixed shape — a fan-in whose sink then feeds a further component — is a legal composite
that `make_chain` accepts and the audit does not find. So the reported component count is a
floor with its search space declared (AUDIT-ALL-0005), not a maximum.

### 6.3 Realization, and the two by-construction checks

- **Literal suppression** (EMIT-ALL-0001). No linked slot may survive as a literal binding.
  Checked exactly, against the bindings the realizer declares, rather than by grepping text.
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
than the noise band means a shortcut exists — the composite is *easier* than composition
allows, as it would be if the upstream answer were readable in the downstream's text — and
the item is quarantined as invalid rather than counted as a success. Note what this does
not catch: a dead link makes a conjunction rather than a chain, and a conjunction sits
exactly on the bound, so liveness has to be enforced at construction (LINK-ALL-0007) and
cannot be recovered from the measurement. It also has an obvious failure of nerve — if items that
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

No model calls, no composites emitted, nothing spent. Link graph, live edges, the deepest
component count reached over the enumerated shapes, per-family reachability, and — with an
archive — the predicted resolution on the **constructible** population. Verdict:
`not_composable` / `composable_to_depth_k` / `composable`, always with reasons.

That component count is a **floor, not a maximum** (AUDIT-ALL-0005). It is the deepest
reached over paths and single-sink fan-ins; a mixed shape can exceed it. The report labels
it `deepest reached` and states the search space beside it.

Predictions are computed on composites the link graph can actually build (AUDIT-ALL-0002).
A uniform prediction describes items the composer cannot emit; on the reference corpus the
two differ by 0.0008 on the discriminating fraction at depth 3 (0.7164 against 0.7172)
while differing 4.6-fold on the between-system gap (0.0294 against 0.1362) — so a uniform
prediction can look right on one axis while being badly wrong on the one being bought.

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

1. **Composition drift** — a full value snapshot of every link verdict, composite gold,
   rendering hash and diagnostic on the calibration corpus, stamped with the spec version.
   `tools/update_snapshot.py` is the only way to move it and refuses without a real spec
   MAJOR bump; a deleted case counts as a change, so "delete, regenerate, re-add" is
   closed off.
2. **Ruling coverage** — every active ruling is exercised by a calibration case or by a
   named test, every example cites back, and every ruling-id-shaped string in `src/`
   resolves, including in comments.
3. **Layering** — the core never imports the subject benchmark, and the adapter never
   writes.
