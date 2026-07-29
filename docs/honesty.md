# Honesty

What nonius measures, what it assumes, and what it refuses. This page exists because a
composability tool is easy to oversell and the surrounding literature is forty years deep.

## What is claimed

One thing: **an installable composition operator with a liveness rule, a validity gate and
a resolution readout.** That is the whole contribution.

## What is not claimed

**Composition is not novel.** It is hardness amplification and direct-product testing in
complexity theory (Yao 1982 onward), serial diagnostic testing under conditional
independence in biostatistics (Vacek 1985), task decomposition with a dependence level in
human reliability analysis (THERP, NUREG/CR-1278, 1983), and cascading errors in NLP
(Finkel, Manning and Ng 2006). In this decade: REval, DynaCode, NESTFUL, EvoEval, CHASE,
GSM-Infinite, GSM-Symbolic, MathGAP, DyVal. Four separate fields have owned pieces of this
under four different words for between two and forty-four years. What did not exist was a
package you can point at your own items.

**Not the first thing to manufacture difficulty without an examiner.** CHASE published
that framework in 2025.

**No claim that the composed instrument measures the same construct as the singleton.**
That is the question composition poses. nonius does not settle it. If composite accuracy
tracks the maximum of the component accuracies rather than their product, or if the system
ordering inverts, the answer is no, and the honest report is a negative result about
composition rather than a harder benchmark.

**No claim to preserve comparability.** The bridge table is an arithmetic re-expression
under a stated independence assumption. It inherits every failure of that assumption, and
prints the residual so the failure is visible.

**No claim to be cheaper than current practice.** The evidence base behind this work
cannot price anything. The defensible claim is narrower and it is an availability
argument rather than a price one: composition requires no examiner, and above human capability no
examiner is available.

**No generality beyond benchmarks with a callable execution oracle.** A benchmark whose
gold is a stored constant cannot be composed at all, which excludes most multiple-choice
suites and every human-labelled set.

## Assumptions that are load-bearing

**Independence.** The product bound assumes component failures are independent. That
assumption is what the bound tests and what the bridge table rests on. Biostatistics and
human reliability analysis both concluded, decades ago, that the better move is to *model*
the dependence rather than discard the composite: latent-class machinery in one field, a
five-level dependence correction in the other. nonius quarantines instead. That is a
weaker answer and it is v1's answer.

**Component exchangeability.** `c ** (1/depth)` treats a chain's components as
interchangeable draws. They are not, and heavy reuse makes it worse, which is why reuse
multiplicity is reported and `nonius.bound.guard_reuse` refuses to price a set whose worst
component exceeds a declared ceiling, a parameter with no default, because how much reuse
is tolerable depends on how the bound will be read (LINK-ALL-0006).

**The probe set.** Liveness for an unbounded int codomain is decided against eleven
declared values. A different probe set would move some links between live and dead, which
is exactly why changing it is a spec MAJOR.

## Circularities, named

**Difficulty strata are not independent of the systems.** Strata come from the same
systems a run would measure. Composing along a difficulty axis those systems defined, and
then measuring those systems, is circular in the stratification, though not in the gold.
Any claim about which stratum recovers the most resolution needs a system that contributed
nothing to the stratification.

**A dead link is invisible to the bound.** Liveness is enforced when a composite is built
(LINK-ALL-0007) and cannot be recovered from the measurement: a dead-link composite is a
conjunction of items, both of which must still be answered, so it sits exactly on the
product bound. The quarantine gate catches composites that are *easier* than the bound
allows, rather than ones that are the right difficulty for the wrong reason.

**The bound is both prediction and gate.** A composite that beats the bound is quarantined;
a distribution that matches it is confirmation. That is a rule that can only confirm itself
unless the quarantine rate has a ceiling fixed in advance, which is why the ceiling is a
required parameter with no default (BOUND-ALL-0004).

**The gold-agreement check can be vacuous.** For a realizer that computes the gold by
chaining the component oracles, the check compares that computation against itself. nonius
emits an info diagnostic saying so. The check has force only for a realizer that reaches
the gold independently.

**Path enumeration builds one chain per node sequence.** It takes the first admissible
(result, slot) assignment and drops the rest, so the constructible population is far smaller
than the set of distinct composites over the same items. A fan-in can then add a second
chain over a sequence a path already covered, when its assignment differs: on the reference
asset that happens for 39 of the 690 depth-2 sequences, and in all 39 it is a different
upstream *result* piped into the same slot. The bound is reported as
`caps.paths_are_one_chain_per_node_sequence`, and it means the depth counts are a floor
twice over: over shapes, and over link assignments within a shape.

**In the pre-registered run the depth-5 product bound is refused rather than computed.** 720 of
the 732 constructible depth-5 chains live inside one family's six near-duplicate programs.
The run's declared reuse ceiling of 100 refuses to price a set that correlated, and the
pre-registration records that refusal in advance rather than discovering it afterwards.

The reference audit is the other case, and the difference matters: it declares no reuse
ceiling at all, since LINK-ALL-0006 makes the ceiling the caller's parameter with no
default, so it *does* print a depth-5 product bound, over all 732 chains, in
`derived/bridge.json`. Read those four rows knowing what the pre-registration refuses to
buy on: they are arithmetic over a pool that is 98% one family.

**One of the pre-registered kill tests is tripped by its own null.** On the constructible
population the predicted ordering departs from the singleton ordering at depth 3, because
that population is dominated by a family on which the systems rank differently. That is a
property of which composites the link graph can build rather than of composition, and it is
registered as an expected outcome so it cannot later be read as a finding.

**Until this project reviewed itself, no registered arm could tell a null result from a
broken run.** The product of accuracies never exceeds their maximum, so an all-zero
measurement passes the product-versus-max test by construction; the quarantine gate
likewise catches only composites that beat their bound. A positive-control arm was added
for that reason, and the gap is recorded in the pre-registration's own limitations.

## Two units, and why both appear

The composer works on **programs**. The benchmark scores **items**, which on the reference
corpus are program × profile × language. The audit and the archive it uses report 100
programs, pooling the fifteen rendering cells as replicates; the separately recorded
item-level statistics report all 1500 items. Both are true, neither is a rounding of the
other, and every number in the derived artifacts is labelled with its unit. Mixing them
would make a saturation statistic look like a composability statistic.

## The reference audit is a negative result

On the benchmark nonius was demonstrated against, the four families that are actually
saturated (900 of 1500 items, sitting at 0.99–1.00 for the top three systems) **cannot
start a chain**, and three of them (540 items) cannot appear in a composite at all. The
only two families that can start a chain are the two the systems are worst at. Every
constructible composite therefore contains an already-hard component, and composition on
that asset cannot address the saturation it was pointed at.

That is reported as the finding rather than buried, because a tool whose most valuable
output is "don't bother, and here is why" has to be willing to say it about itself.

## The noise band is biased toward zero, and not in the safe direction

The quarantine band is not a chosen constant. It is bootstrapped from the archive's own
replicate draws (BOUND-ALL-0002). But a cell whose k draws are unanimous has zero sample
variance, so the bootstrap returns a point interval and that cell contributes a structural
`0.0` to the mean. On the reference archive **315 of 400 (system, item) cells are
unanimous**, so most of the published band records that the resampler observed no
variation rather than that there is none to observe. A run of identical draws is weak evidence of
zero variance however long it is, and an interval that can express that uncertainty,
Wilson for instance, is materially wider on the same data.

The direction is the uncomfortable part. Quarantine fires on `observed − predicted > band`,
so a band biased small quarantines **more**, and the quarantine rate is exactly what the
pre-registered ceiling is read against. A gate that fires too readily is not the
conservative failure it sounds like: it would let the run reject composites for being
noisy when the band rather than the composite is the artefact.

The estimator is unchanged, because changing it after pre-registering a threshold against
its output would be the wrong repair. What changed is that `derived/audit.json` now
publishes `archive.noise_band_unanimous_cell_fraction` beside the band, and this paragraph
exists.

Two further things a reader should know. First, the band is estimated on **one (system,
item) cell's rate**, while the quantity it gates is `observed − predicted` for a whole
*composite*, where `predicted` is a product over components. Those are different variances
on different units; the band is being used as a stand-in for a spread it does not measure,
and no amount of care in estimating it fixes the mismatch. Second, the obvious repair,
which is to recompute over only the cells that vary, is itself biased, in the opposite direction and
by more than the bias it removes, because conditioning on having observed variation selects
the noisiest cells. There is no unbiased one-line substitute here. The honest recomputation
is over *all* cells with an interval that does not collapse on a unanimous sample.

## The paid run measured less than its first analysis claimed

run-01 bought 14268 completions against thresholds fixed in advance. Its first analysis
reported that composition preserved the construct and destroyed the instrument anyway.
Neither half survived an adversarial check, and the retraction is worth stating here
rather than only in a commit.

The grading was sound: an independent regrade of all 14268 completions with the subject's
own matcher agreed on every one. The interpretation was not. "Accuracy tracked the
product" rested on a statistic that passes by construction wherever the measurement is
zero, and 1848 of 2000 depth-2 cells measured exactly zero; of the seven genuinely
informative cells, the claim does not hold as stated. "Few shortcuts" quoted a 1.9%
quarantine rate against a 20% ceiling the data could not reach, since a cell measuring zero
can never exceed a bound; the reachable maximum was 7.6% and the rate among cells able to
exceed one was 25%.

Three things the run cannot establish, each for a reason visible in its own artifact.
Depth is perfectly confounded with item family, because the pre-registered cap of 500
dropped every `fsm_transition` chain at depth 2 and every non-`fsm` chain at depth 5, so
the composed depths measure disjoint populations. Depth 2 is the only row in the readout
where the top-two gap exceeds `m*`, so on the statistic this library tells you to prefer,
composition there bought resolution rather than losing it. And KT-4's magnitude is computed
across a unit mismatch that the pre-registration's own `baseline_caveat` anticipated: the
measured rows are one rendering cell at k = 3 against a baseline pooling fifteen cells at
k = 120.

What the run does support is narrow and is written up in
`validation/run_01/FINDING.md`: one chain link produces a composite all four systems fail
identically, on a single lookup rather than on depth.
