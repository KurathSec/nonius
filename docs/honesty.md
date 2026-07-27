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
human reliability analysis (THERP / NUREG-CR-1278, 1983), and cascading errors in NLP
(Finkel, Manning and Ng 2006). In this decade: REval, DynaCode, NESTFUL, EvoEval, CHASE,
GSM-Infinite, GSM-Symbolic, MathGAP, DyVal. Four separate fields have owned pieces of this
under four different words for between two and forty-four years. What did not exist was a
package you can point at your own items.

**Not the first thing to manufacture difficulty without an examiner.** CHASE published
that framework in 2025.

**No claim that the composed instrument measures the same construct as the singleton.**
That is the question composition poses, not one nonius settles. If composite accuracy
tracks the maximum of the component accuracies rather than their product, or if the system
ordering inverts, the answer is no — and the honest report is a negative result about
composition rather than a harder benchmark.

**No claim to preserve comparability.** The bridge table is an arithmetic re-expression
under a stated independence assumption. It inherits every failure of that assumption, and
prints the residual so the failure is visible.

**No claim to be cheaper than current practice.** The evidence base behind this work
cannot price anything. The defensible claim is narrower and it is an availability
argument, not a price one: composition requires no examiner, and above human capability no
examiner is available.

**No generality beyond benchmarks with a callable execution oracle.** A benchmark whose
gold is a stored constant cannot be composed at all — which excludes most multiple-choice
suites and every human-labelled set.

## Assumptions that are load-bearing

**Independence.** The product bound assumes component failures are independent. That
assumption is what the bound tests and what the bridge table rests on. Biostatistics and
human reliability analysis both concluded, decades ago, that the better move is to *model*
the dependence rather than discard the composite — latent-class machinery in one field, a
five-level dependence correction in the other. nonius quarantines instead. That is a
weaker answer and it is v1's answer.

**Component exchangeability.** `c ** (1/depth)` treats a chain's components as
interchangeable draws. They are not, and heavy reuse makes it worse, which is why reuse
multiplicity is reported and `nonius.bound.guard_reuse` refuses to price a set whose worst
component exceeds a declared ceiling — a parameter with no default, because how much reuse
is tolerable depends on how the bound will be read (LINK-ALL-0006).

**The probe set.** Liveness for an unbounded int codomain is decided against eleven
declared values. A different probe set would move some links between live and dead, which
is exactly why changing it is a spec MAJOR.

## Circularities, named

**Difficulty strata are not independent of the systems.** Strata come from the same
systems a run would measure. Composing along a difficulty axis those systems defined, and
then measuring those systems, is circular in the stratification — though not in the gold.
Any claim about which stratum recovers the most resolution needs a system that contributed
nothing to the stratification.

**A dead link is invisible to the bound.** Liveness is enforced when a composite is built
(LINK-ALL-0007) and cannot be recovered from the measurement: a dead-link composite is a
conjunction of items, both of which must still be answered, so it sits exactly on the
product bound. The quarantine gate catches composites that are *easier* than the bound
allows, not ones that are the right difficulty for the wrong reason.

**The bound is both prediction and gate.** A composite that beats the bound is quarantined;
a distribution that matches it is confirmation. That is a rule that can only confirm itself
unless the quarantine rate has a ceiling fixed in advance — which is why the ceiling is a
required parameter with no default (BOUND-ALL-0004).

**The gold-agreement check can be vacuous.** For a realizer that computes the gold by
chaining the component oracles, the check compares that computation against itself. nonius
emits an info diagnostic saying so. The check has force only for a realizer that reaches
the gold independently.

## Two units, and why both appear

The composer works on **programs**. The benchmark scores **items**, which on the reference
corpus are program × profile × language. The audit and the archive it uses report 100
programs, pooling the fifteen rendering cells as replicates; the separately recorded
item-level statistics report all 1500 items. Both are true, neither is a rounding of the
other, and every number in the derived artifacts is labelled with its unit. Mixing them
would make a saturation statistic look like a composability statistic.

## The reference audit is a negative result

On the benchmark nonius was demonstrated against, the four families that are actually
saturated — 900 of 1500 items, sitting at 0.99–1.00 for the top three systems — **cannot
start a chain**, and three of them (540 items) cannot appear in a composite at all. The
only two families that can start a chain are the two the systems are worst at. Every
constructible composite therefore contains an already-hard component, and composition on
that asset cannot address the saturation it was pointed at.

That is reported as the finding rather than buried, because a tool whose most valuable
output is "don't bother, and here is why" has to be willing to say it about itself.
