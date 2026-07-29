## The second audit: HumanEval+

nonius pointed at a benchmark its author did not build. EvalPlus supplies the items, the contracts, the canonical solutions and the oracle; this project claims none of them. Spec `2.0.0`, access read-only; dataset not vendored.

The adapter admits **109 of HumanEval's 164 items**. The rest are absent because their signature is not plain positional or their result is not a scalar nonius can pipe, plus two named exclusions: `HumanEval/39` is nondeterministic and `HumanEval/32` has a property oracle rather than a value one. HumanEval ships no topic label, so no family stratum is declared: any would be adapter-invented.

### The funnel

Four numbers, and the gaps between them are the finding:

| stage | count | share of previous |
| --- | ---: | ---: |
| type-compatible candidates | 3764 | |
| decidable (has a probe set) | 2564 | 68.1% |
| live (answer varies over the codomain) | 2279 | 88.9% |
| emittable (downstream contract accepts it) | 1835 | 80.5% |

1200 candidates were never *decided*: their upstream result has no probe set, so calling them dead would report an absent probe set as a fact about the benchmark. They are excluded from the denominator rather than counted against it.

The last row is the one this subject taught the project. Liveness asks whether the downstream answer varies over the upstream codomain. Emission additionally needs the downstream **contract** to accept the piped value, and EvalPlus's contracts are the only domain declaration these items carry. 444 live links are refused at realization (372 CompositionError, 72 OracleError), so liveness is necessary and not sufficient here in exactly the way type compatibility is necessary and not sufficient for liveness.

### Difficulty, and why the strata are not comparable across subjects

The archive holds 164 items across 6 systems at k = 0: `chatgpt, code-llama-34b, code-llama-7b, codegen-2b, gpt-j, incoder-6b`.

| stratum | items |
| --- | ---: |
| discriminating | 152 |
| floored | 12 |

**Strata depend on which systems are in the panel. This one holds gpt-j at pass@1 0.0407, so `dead` (every system perfect) is unreachable and the dead count is 0 against 18/100 on the first subject. That gap is the panel rather than the benchmark.**

**The noise band is refused on this archive, and that is the correct answer.** Three draws out of 196800 are unmeasurable: their worker dies and no verdict exists, so three cells hold 199 draws where every other cell holds 200. `Archive.k` returns 0 for a ragged archive rather than a mean, and the band depends on k, so quietly averaging would put a made-up number under the quarantine rule. No quarantine runs on this subject in any case, since nothing here is measured. 40.7% of cells are unanimous, which is the bias `docs/honesty.md` records for the first subject and would apply here too.

23 systems were released; 6 were graded. A subset is a bound and is reported beside what it withheld (AUDIT-ALL-0004).

### Resolution readout

Predicted rows, from the archive and the independence product bound. Nothing here is measured: no inference was bought for this subject. Two cautions come before the table, and both of them limit what it can be read to say.

**There are two depth-1 rows, and only one of them is a baseline.** `predicted/all` is the instrument as shipped, averaged over every item in the archive. `predicted/composable` is restricted to the items the live-link graph can reach, which is the population every composed row is drawn from. Reading depth 2 against `predicted/all` charges a change of population to depth. Here the composable items are the easier ones, so that reading overstates the fall; on the first subject they are harder and it understates it, which is why the row exists rather than a caveat.

**The predicted rows cannot test what a measured run would test.** Under the product bound a composite's accuracy is a product of its components', so the ordering over systems is preserved by construction and decay with depth is arithmetic rather than evidence. `m*` falls with depth for the same mechanical reason: predictions crowd toward zero, so their spread shrinks. That the gap exceeds `m*` at every depth is therefore not a finding about composition. It is the same shape of vacuity `docs/honesty.md` records for the gold-agreement check and for KT-1.

| depth | n | source/population | chatgpt | code-llama-34b | code-llama-7b | codegen-2b | gpt-j | incoder-6b | dead | floored | discriminating | gap | m\* | gap > m\* |
| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 164 | predicted/all | 0.5720 | 0.3137 | 0.2330 | 0.1318 | 0.0407 | 0.0668 | 0.0000 | 0.0732 | 0.9268 | 0.2584 | 0.1261 | yes |
| 1 | 65 | predicted/composable | 0.5944 | 0.3295 | 0.2487 | 0.1416 | 0.0582 | 0.0779 | 0.0000 | 0.0000 | 1.0000 | 0.2649 | 0.1874 | yes |
| 2 | 1760 | predicted/all | 0.3311 | 0.0984 | 0.0610 | 0.0193 | 0.0039 | 0.0059 | 0.0000 | 0.0051 | 0.9949 | 0.2327 | 0.0322 | yes |
| 3 | 10000 | predicted/all | 0.1688 | 0.0187 | 0.0078 | 0.0005 | 0.0000 | 0.0001 | 0.0000 | 0.0241 | 0.9759 | 0.1501 | 0.0096 | yes |
| 5 | 10000 | predicted/all | 0.0575 | 0.0000 | 0.0001 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0822 | 0.9178 | 0.0574 | 0.0038 | yes |

Verdict: **`composable`**.

Concentration, which is the disclosure that makes the rows readable:

* depth 2: the largest family contributes 0 of 1760 chains in the pool
* depth 3: the largest family contributes 0 of 10000 chains in the pool
* depth 5: the largest family contributes 0 of 10000 chains in the pool

### Caps

* `diagnostic_cap`: 25
* `diagnostic_counts`: {'codomain-unbounded': 29, 'link-dead': 285, 'slot-tag-not-composable': 2}
* `diagnostics_withheld`: 264
* `probe_bool`: [False, True]
* `probe_cap`: 64
* `probe_int`: [0, 1, 2, 5, 10, 50, 100, 1000, 10000, 60000, -1]
* `probe_str`: []
* `unprobeable_results`: ['HumanEval/10.value', 'HumanEval/103.value', 'HumanEval/11.value', 'HumanEval/110.value', 'HumanEval/118.value', 'HumanEval/119.value', 'HumanEval/127.value', 'HumanEval/140.value', 'HumanEval/141.value', 'HumanEval/143.value', 'HumanEval/15.value', 'HumanEval/153.value', 'HumanEval/156.value', 'HumanEval/158.value', 'HumanEval/161.value', 'HumanEval/162.value', 'HumanEval/19.value', 'HumanEval/27.value', 'HumanEval/28.value', 'HumanEval/38.value', 'HumanEval/44.value', 'HumanEval/50.value', 'HumanEval/51.value', 'HumanEval/65.value', 'HumanEval/79.value', 'HumanEval/84.value', 'HumanEval/86.value', 'HumanEval/89.value', 'HumanEval/93.value']

