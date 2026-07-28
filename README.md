# nonius

**Compose the benchmark you already have — and find out for free whether you can.**

A saturated benchmark still returns a well-formed number. It is kept precisely because
every historical comparison was computed against it, so switching instruments costs
comparability and staying costs signal. Today the practitioner has two moves and both are
bad: keep reporting a number that no longer separates systems, or adopt a harder benchmark
and lose every previous result.

nonius adds a third. Point it at your own committed items plus the program that already
computes their gold answers, and it emits depth-graded composites in which one item's
executed answer becomes the next item's input. The composite's gold is a deterministic
function of the component golds, computed by the same oracle. No examiner is invoked, no
item is authored, and no model is called.

It also tells you when the answer is no.

```console
$ nonius audit --items items.jsonl --oracle ./oracle.py:answer --depths 1,2,3,5,8,13
verdict: composable_to_depth_13

  items                 100
  candidate links     16470   type-compatible (LINK-ALL-0001)
  live links           5880    35.7%   admissible (LINK-ALL-0007)
  live pairs            690     7.0% of 9900 ordered pairs carry a live link
  deepest reached        13   over paths and fan-ins; a floor, not a maximum (AUDIT-ALL-0005)

  family                    items  can start  can continue  isolated
  agg_stats                    20         20             0         0
  allowlist                    24          0            19         5
  config_resolver              24          0             0        24
  discovery_pipeline            6          0             0         6
  fsm_transition                6          6             6         0
  status_router                 6          0             0         6
  threshold_select             14          0            14         0

   depth     paths   fan-ins   largest single-family share
       1       100         0   n/a
       2       690        39   36/729 fsm_transition
       3       120        14   120/134 fsm_transition
       5       720        12   720/732 fsm_transition
       8         0         4   0/4 (no single-family chain)
      13         0         1   0/1 (no single-family chain)

  cannot compose in either direction: config_resolver, discovery_pipeline, status_router
  can only terminate a chain, never start one: allowlist, threshold_select

  bounds: probe cap 64 per link, path cap 10000 per depth, sample 20000 per readout, diagnostic cap 25 per code
  WITHHELD: 10565 diagnostics beyond the per-code cap (full counts in --json under caps.diagnostic_counts)
```

Read the reachability table before the verdict. Three families cannot be composed in any
direction, and two more can only ever sit at the end of a chain. `deepest reached 13` is a
floor over the two shapes the audit enumerates — paths and single-sink fan-ins — and a
mixed shape can exceed it (AUDIT-ALL-0005); the table is what that number is made of.

That readout costs nothing and takes seconds. Getting it *before* you emit a corpus and
buy inference against it is the point.

## Install

**nonius is unreleased.** There is no PyPI distribution and no published tag, so install
from a checkout:

```console
git clone <your checkout of this repository> nonius
cd nonius
pip install -e .
```

`pip install nonius` is what the first release will look like; it does not work today, and
saying otherwise would be the first false claim in a tool built to refuse them.

Zero runtime dependencies, Python 3.11+.

## What it needs from your benchmark

Three things, and the second is the hard one:

1. **An item manifest** (JSONL) declaring typed, named input slots and typed, named
   results — things a benchmark with an execution oracle already possesses but never
   exposes.
2. **A callable oracle**, `oracle(item, bindings) -> results`. This is the instrument's
   hard precondition and its main limit on reach: a benchmark whose gold is a stored
   constant with no program behind it cannot be composed, because there is nothing to
   re-run under a changed binding. That excludes most multiple-choice suites and every
   human-labelled set.
3. **Optionally, a per-item verdict archive** `(system, item, draw, verdict)`, used for
   difficulty stratification and the product-bound prediction — never for the gold.

A **realizer** turns components plus links into one presentable composite. `nonius` ships
a default one for any manifest whose items carry a slotted prompt template; an adapter can
supply a better one.

## Why an audit, and not just a composer

Because on real corpora the operator usually declines, and the reason is not the one you
would guess.

Type compatibility is not the binding constraint. A link only *binds* if the downstream
answer actually varies as the substituted slot ranges over the upstream result's codomain.
If it does not, the composite is still harder than either item alone — both components
must be answered — but it is a **conjunction, not a chain**. Nothing was carried from one
item to the next, so depth counts how many items were printed together rather than how far
an answer travelled, and the measurement is no longer about composition.

That failure is invisible after the fact. A conjunction sits exactly on the independence
product bound, so the validity gate never flags it; liveness has to be enforced when the
item is built.

Measured on the reference corpus (100 committed programs, run through the benchmark's own
execution oracle): **3190 of 9900 ordered item pairs (32.2%) are type-compatible, but only
690 (7.0%) carry a live link.** See [validation](docs/validation.md) for the full audit and what it
implies.

## What nonius does not claim

Carried here deliberately, because the surrounding literature is large and old:

- **Composition is not novel.** It is hardness amplification and direct-product testing in
  complexity theory (Yao 1982 onward), serial diagnostic testing under conditional
  independence in biostatistics (Vacek 1985), task decomposition with a dependence level in
  human reliability analysis (THERP, NUREG/CR-1278, 1983), and cascading errors in NLP
  (Finkel, Manning and Ng 2006). In this decade: REval, DynaCode, NESTFUL, EvoEval, CHASE,
  GSM-Infinite, GSM-Symbolic, MathGAP and DyVal. The claimed contribution is an installable
  operator with a liveness rule, a validity gate and a resolution readout. Nothing more.
- **It is not the first thing to manufacture difficulty without an examiner.** CHASE
  published that framework in 2025.
- **It does not claim the composed instrument measures the same construct as the
  singleton.** That is the question composition poses, not one nonius settles. If composite
  accuracy tracks the maximum of the component accuracies rather than their product, or if
  the system ordering inverts, the answer is no.
- **It does not claim to preserve comparability.** The bridge table re-expresses old scores
  under a stated independence assumption. That is an arithmetic re-expression, not a proof
  of measurement equivalence, and it inherits every failure of the assumption it rests on.
- **It does not claim to be cheaper than current practice.** The evidence base behind this
  work cannot price anything. The defensible claim is narrower: composition requires no
  examiner.
- **It claims no generality beyond benchmarks with a callable execution oracle.**

## Documentation

- [Quickstart](docs/quickstart.md)
- [The rulings](docs/spec/rulings.md) — every composition decision, with an immutable id
- [Honesty](docs/honesty.md) — what is measured, what is assumed, what is refused
- [Validation](docs/validation.md) — the reference audit and its finding
- [Architecture](ARCHITECTURE.md)

## Licence

MIT. See [NOTICE](NOTICE) for provenance of the pieces that came from elsewhere.
