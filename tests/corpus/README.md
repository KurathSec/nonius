# The calibration corpus

**This is a fixture, not a benchmark.** It exists so that every decision the composer makes
can be checked against arithmetic a person can do on paper. It is not an item set anyone
should score a system on, and no number derived from it is a finding about any model.

## Layout

```
items.jsonl        the shared item set, 10 items
oracle.py          the oracle, five operations, deterministic and total
cases/<id>.toml    one scenario per file
```

Each case names the rulings it exercises, states `computed_by = "hand"`, and shows the
arithmetic in `notes`. `tests/test_corpus.py` rejects a case that does neither: a case
whose numbers cannot be checked on paper is a snapshot, not calibration.

## Why these ten items

They are chosen to make each decision visible in isolation:

| item | what it is there to show |
|---|---|
| `sum-a`, `sum-b` | unbounded int results, so liveness falls back to the probe set |
| `thr-live` | a **live** int slot: the cut sits inside the probe set |
| `thr-dead` | a **dead** int slot: the cut is below every probe, so the answer never moves |
| `dual-a` | two int slots on one sink — the fan-in shape |
| `lk-live` | a live str slot: the upstream codomain lands on this table's keys |
| `lk-miss` | a dead str slot: every upstream value misses, so the default always wins |
| `lk-nocodomain` | a str result with no declared codomain, so liveness is undecidable |
| `mem-a` | a bool result, which no slot here accepts — bool tested before int matters |
| `float-item` | a float slot, never composable, though its str result can still start a chain |

The pair `thr-live` / `thr-dead` is the corpus's reason for existing. They are
type-identical and one of them is useless, which is the whole argument for `LINK-ALL-0007`
compressed into two records.

## Editor hygiene

`.gitattributes` marks this tree `-text` and `.editorconfig` turns off trailing-whitespace
trimming here. A helpful editor silently normalising a fixture surfaces much later as a
baffling composition-drift failure.
