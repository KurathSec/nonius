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

The archive holds 164 items across 6 systems at k = 200: `chatgpt, code-llama-34b, code-llama-7b, codegen-2b, gpt-j, incoder-6b`.

| stratum | items |
| --- | ---: |
| discriminating | 146 |
| floored | 12 |
| unknown | 6 |

**Strata depend on which systems are in the panel. This one holds gpt-j at pass@1 0.0415, so `dead` (every system perfect) is unreachable and the dead count is 0 against 18/100 on the first subject. That gap is the panel rather than the benchmark.**

The noise band is 0.0232 with 40.5% of cells unanimous, so the same bias `docs/honesty.md` records for the first subject applies here and is larger.

23 systems were released; 6 were graded. A subset is a bound and is reported beside what it withheld (AUDIT-ALL-0004).

### Resolution readout

Predicted rows, from the archive and the independence product bound. Nothing here is measured: no inference was bought for this subject. Two cautions come before the table, and both of them limit what it can be read to say.

**The depth-1 row is not a baseline for the rows below it.** `singleton_row` averages over every item in the archive, while the composed rows are built only from the items the adapter admits. Those populations differ here, and not randomly: the admitted items are easier for every one of the six systems.

| system | depth-1 row (all archive items) | restricted to the composable items | difference |
| --- | ---: | ---: | ---: |
| chatgpt | 0.5717 | 0.6084 | +0.0367 |
| code-llama-34b | 0.3203 | 0.3502 | +0.0299 |
| code-llama-7b | 0.2395 | 0.2663 | +0.0268 |
| codegen-2b | 0.1367 | 0.1500 | +0.0133 |
| gpt-j | 0.0423 | 0.0508 | +0.0085 |
| incoder-6b | 0.0692 | 0.0713 | +0.0021 |

So the depth 1 to depth 2 fall is measured across a change of population as well as a change of depth. The same report says 109 chains at depth 1 and 158 items in the depth-1 row, which is the inconsistency in one line. Read the composed rows against the middle column, never the left one. This is a defect in the audit rather than in the subject, and it applies to the first subject's readout too.

**The predicted rows cannot test what a measured run would test.** Under the product bound a composite's accuracy is a product of its components', so the ordering over systems is preserved by construction and decay with depth is arithmetic rather than evidence. `m*` falls with depth for the same mechanical reason: predictions crowd toward zero, so their spread shrinks. That the gap exceeds `m*` at every depth is therefore not a finding about composition. It is the same shape of vacuity `docs/honesty.md` records for the gold-agreement check and for KT-1.

| depth | n | source | chatgpt | code-llama-34b | code-llama-7b | codegen-2b | gpt-j | incoder-6b | dead | floored | discriminating | gap | m\* | gap > m\* |
| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 158 | predicted | 0.5717 | 0.3203 | 0.2395 | 0.1367 | 0.0423 | 0.0692 | 0.0000 | 0.0759 | 0.9241 | 0.2514 | 0.1273 | yes |
| 2 | 1723 | predicted | 0.3256 | 0.0974 | 0.0606 | 0.0197 | 0.0040 | 0.0061 | 0.0000 | 0.0052 | 0.9948 | 0.2283 | 0.0320 | yes |
| 3 | 9280 | predicted | 0.1589 | 0.0172 | 0.0069 | 0.0006 | 0.0000 | 0.0001 | 0.0000 | 0.0252 | 0.9748 | 0.1417 | 0.0098 | yes |
| 5 | 10000 | predicted | 0.0575 | 0.0000 | 0.0001 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0822 | 0.9178 | 0.0574 | 0.0038 | yes |

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

