# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Because nonius is a measurement instrument, every release entry states **two versions**,
not one: package and composition spec. A composition spec MAJOR means some decision the
composer makes changed, which means numbers published under the old spec are not
comparable to numbers published under the new one.

## [Unreleased]

- package 0.1.0.dev0 · spec 1.0.0

First working shape. The composer, the composability audit, the independence-product
bound with its quarantine rule, the bridge table, the resolution readout, a
benchmark-agnostic manifest, a default slotted-prompt realizer, a read-only reference
adapter, and exporters for lm-evaluation-harness and Inspect AI.

Composition spec 0.1.0 fixes three decisions that the surrounding literature leaves
implicit, and the middle one is the reason this release exists at all:

- **Depth counts components, not links** (DEPTH-ALL-0001). The two readings differ by one
  item and the difference shows up in published arithmetic.
- **A link is admissible only if it is live** (LINK-ALL-0002). Type compatibility is
  necessary and nowhere near sufficient. On the reference corpus 32.2% of ordered item
  pairs are type-compatible and 7.0% carry a live link, so a composer checking types alone
  emits a mostly degenerate item set — which its own validity gate then quarantines.
- **A substituted slot must not survive as a literal** (EMIT-ALL-0001). Printing the
  upstream answer into the downstream's presentation makes the chain fake, and is what the
  obvious reading of "substitute into the input literals" produces.

The reference audit in `validation/spaghetti_audit/` reports a real benchmark that the
operator largely declines to compose, and says why. No paid run has been executed;
`preregistration/run-01.toml` is designed and unexecuted.

Composition spec 1.0.0 corrects three decisions before any number was published under
0.1.0, and the correction is itself worth recording: an adversarial review of the whole
project found that the audit's headline component count was called a maximum when it is a
floor over two enumerated shapes, that a stated reuse ceiling was never implemented, and
that hashing the spec version into a composite id made every id move on an editorial
patch. All three are fixed rather than reworded — see the spec changelog in
`src/nonius/spec/rulings/index.toml`.
