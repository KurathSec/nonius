# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Because nonius is a measurement instrument, every release entry states **two versions**,
not one: package and composition spec. A composition spec MAJOR means some **recorded
value** changed — the drift gate's definition, and the only one that can be checked
mechanically. Usually that is a decision the composer makes, and then numbers published
under the old spec are not comparable to numbers under the new one. It can also be a
recorded citation label, which moves when a ruling is superseded without any measured
quantity changing. The stanza for each MAJOR says which kind it was; 2.0.0 is the second
kind.

## [Unreleased]

- package 0.1.0.dev0 · spec 2.0.0

First working shape. The composer, the composability audit, the independence-product
bound with its quarantine rule, the bridge table, the resolution readout, a
benchmark-agnostic manifest, a default slotted-prompt realizer, a read-only reference
adapter, and exporters for lm-evaluation-harness and Inspect AI.

Composition spec 0.1.0 fixes three decisions that the surrounding literature leaves
implicit, and the middle one is the reason this release exists at all:

- **Depth counts components, not links** (DEPTH-ALL-0003). The two readings differ by one
  item and the difference shows up in published arithmetic.
- **A link is admissible only if it is live** (LINK-ALL-0007). Type compatibility is
  necessary and nowhere near sufficient. On the reference corpus 32.2% of ordered item
  pairs are type-compatible and 7.0% carry a live link. A dead link costs dependence
  rather than difficulty: both components must still be answered, so the composite sits
  exactly on its product bound and the validity gate never flags it — it is simply a
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
rule — the project's headline argument — was wrong, because a dead-link composite does not
beat its product bound (LINK-ALL-0007); and the gold-agreement rule called its two
computations independent when they are only independent for a realizer that reaches the
gold independently, which the default one does not (EMIT-ALL-0006). Each is superseded with
a corrected successor rather than edited. See `src/nonius/spec/rulings/index.toml`.
