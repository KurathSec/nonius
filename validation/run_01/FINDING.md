# run-01: what the paid run established, and what it did not

14268 completions, four systems, k = 3, against thresholds fixed before any of them was
bought. Every number here comes from `derived/results.json`, which
`analyse.py` re-derives from `derived/composite_archive.jsonl.gz`. Nothing is hand-entered.

## The finding

**On the drawn population, one chain link produces a composite that all four systems fail
identically, and it fails on a single lookup rather than on depth.**

At depth 5 the chain injects `c0_next_start = 'running'` into a table keyed
`idle / paused / stopped`, so the composed gold is `"ERR"`. All 5986 parsed depth-5
completions, from every system, answered `'running'`. None produced `ERR`. Whole-dict exact
matching makes that row identically zero before capability enters. At depth 3 the same
field is wrong in 1440 of 1440 fsm completions, and the remaining 14 chains all contain a
component no system scores above zero.

That is a real departure from the independence bound. For the 120 fsm chains at depth 3,
P(all zero | product) is 5.3e-32 for the strongest system. But it is a fact about six
near-duplicate programs and one string, not about composition depth.

## What the thresholds returned

| arm | outcome |
|---|---|
| KT-0 execution validity | passes: control accuracy 0.7576 against a 0.60 floor, parse rate 0.9909 against 0.90 |
| KT-1 product vs max | registered for one system at one depth (DeepSeek, depth 3). Vacuous: measured 0.0 cannot be closer to the max, because product <= max |
| KT-2 quarantine | depth 2 only. 0.019 against a 0.20 ceiling, but the reachable maximum was 0.076 and the rate among cells able to exceed a bound was 0.25 |
| KT-2b ordering | fires at depth 2: measured order departs from predicted by 0.1123 against a yardstick of 0.0648 |
| KT-4 floor not ceiling | fires. Best composed depth 2 discriminates 0.1728 |
| reuse ceiling | depth 5 REFUSED a product bound: fsm_transition appears in 428 of 500 composites |

## What this does not license

**It does not show resolution decaying with depth.** Depth is perfectly confounded with
item family. The pre-registered cap of 500 dropped every fsm chain at depth 2 and every
non-fsm chain at depth 5, so no family is held constant across any two composed depths.
The three depths measure three disjoint populations.

**It does not show that composition destroys an instrument.** Depth 2 is the only row in
the readout where the top-two gap exceeds m\* (0.1123 against 0.0648). Neither singleton
row clears its own. On the statistic `resolution.py` instructs you to prefer, composition
at depth 2 bought resolution rather than losing it.

**It does not settle KT-4's magnitude.** The delta against the program-level baseline is
computed across a unit mismatch: the measured composed rows are one program x one profile
x one language at k = 3, while the 0.7200 baseline pools fifteen rendering cells at
k = 120. Subsampling that same archive to k = 3 gives 0.4687. A large part of the apparent
delta is replicate depth, not composition, and the pre-registration's own
`baseline_caveat` anticipated exactly this.

**It says nothing about accuracy tracking the product.** That claim was made and withdrawn.
Of the depth-2 cells, 1848 of 2000 measured exactly zero and pass the comparison by
construction; only 7 are genuinely informative once the degenerate cases are removed.

## The correction that produced this document

The first analysis of this run asserted that composition preserved the construct and
destroyed the instrument anyway. An adversarial verification raised 34 findings, 13 of
which survived refutation, and neither half of that claim stood. The grading was sound --
an independent regrade of all 14268 completions agreed 14268/14268 -- and the
interpretation was not. The harness defects behind it are listed in the commit that fixed
them; the largest were counting quarantined composites as successes, never applying the
reuse ceiling, and reporting an unregistered pooled statistic in place of the registered
one.
