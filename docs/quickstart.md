# Quickstart

## 1. Describe your items

A JSONL manifest, one record per item, declaring typed named input slots and typed named
results — things a benchmark with an execution oracle already has but never exposes.

```json
{"id": "sum-a", "family": "aggregate",
 "results": [{"name": "total", "tag": "int"}],
 "payload": {"op": "sum", "values": [1, 2, 3], "prompt": "Sum the list [1, 2, 3]."}}
{"id": "thr-live", "family": "threshold",
 "slots":   [{"name": "subject", "tag": "int", "consumer": "threshold"}],
 "results": [{"name": "verdict", "tag": "str", "codomain": ["high", "low"]}],
 "payload": {"op": "threshold", "subject": 4, "cut": 10, "hi": "high", "lo": "low",
             "prompt": "Report high if {subject} >= 10, otherwise low."}}
```

The records above are wrapped for reading. JSONL means **one record per line**: unwrap
them before saving, or the manifest will not parse.

They are the first and third items of the shipped calibration corpus,
`tests/corpus/items.jsonl`.
The rest of this page runs against that whole file, which is why its verdict is deeper than
two items alone could reach.

`codomain` is the exact set of values a result can take. Declare it when you know it: it
is what liveness is decided against. Omit it and an int falls back to the versioned probe
set, while a str carries no live link at all.

## 2. Point at your oracle

`oracle(item, bindings) -> results`, where bindings are *overrides* on the item's own
values. This is usually a ten-line wrapper around the program your benchmark already runs
to produce gold.

```python
def answer(item, bindings):
    p = {**item.payload, **bindings}
    ...
    return {"total": ...}
```

## 3. Audit before you compose

```console
$ nonius audit --items tests/corpus/items.jsonl --oracle tests/corpus/oracle.py:answer
verdict: composable_to_depth_3
```

Free, offline, seconds. If it says `not_composable`, it tells you which items cannot start
a chain, which cannot continue one, and which type tags carry no live link. Stop there and
you have spent nothing.

## 4. Compose

```console
$ nonius compose --items tests/corpus/items.jsonl --oracle tests/corpus/oracle.py:answer \
      --depths 2,3 --limit 500 --out composites.jsonl
```

Every emitted composite has passed two by-construction checks: no linked slot survives as a
literal, and its gold agrees with the gold from evaluating the components one at a time in
topological order. With the default realizer that second check is vacuous — the realizer
reaches the gold by the same chaining the check uses as its reference — and nonius says so
with an info diagnostic rather than letting a tautology read as evidence. The check has
force only for a realizer that reaches the gold independently, as the Spaghetti Architect
adapter does by merging the components into one program and running that program's oracle.

## 5. Run it in the harness you already use

```console
$ nonius compose ... --export lm-eval  > composites.jsonl
$ nonius compose ... --export inspect  > samples.jsonl
```

Scoring is your harness's exact-match scorer — the same one your singleton items were
graded with, which is the point.

## 6. Plan a paid run

```console
$ nonius run --composites composites.jsonl --prereg preregistration/run-01.toml
```

Prints the plan and the completion count. This verb has no code path that can spend.
