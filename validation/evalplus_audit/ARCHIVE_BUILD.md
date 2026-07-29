# Building the EvalPlus verdict archive: specification and warning

The second audit currently reports structure (candidates, decidable, live, emittable) and
no difficulty. A verdict archive would give it a product bound, a noise band and strata,
which is what the first subject has and this one does not. EvalPlus published the raw
material in 2023, so it costs no inference.

**Status: downloaded, not built.** The 23 `temp_0.8` release assets are in
`.data/evalplus_samples/` (410 MB, gitignored). Nothing has been executed.

## What the input is

`gh release download v0.1.0 -R evalplus/evalplus --pattern '*temp_0.8.zip'`

23 archives, one per system, each holding 32800 files at
`humanEvalPlus/<system>/HumanEval_<task>/<draw>.py`: 164 tasks x 200 draws.
**754400 programs in total.**

## Read this before running anything

These are **model-written programs from 2023**, not EvalPlus's vetted reference solutions.
The hazards are mostly accidental rather than malicious, and they are the ordinary output
of a weak model asked to write code: unbounded loops, allocation until the machine swaps,
writes into the working directory, a stray `os.system` or `open(..., "w")`.

`src/nonius/adapters/_evalplus_worker.py` is **not sufficient for this**. It was written for
the reference path and carries `RLIMIT_AS`, `RLIMIT_CPU` and an alarm, with no filesystem
isolation and no environment scrubbing. The subject's own harness is stricter: see
`bench/grade.py::network_isolation_prefix` and `_sanitized_env` in Spaghetti Architect.

Before any of this runs, the worker needs:

* a scratch working directory per execution, discarded afterwards, so a write lands nowhere
  that matters;
* no network (the subject's `network_isolation_prefix` shows the shape);
* a scrubbed environment, so a credential in the ambient environment is not readable by
  754400 pieces of third-party code;
* the limits it already has.

## Why it cannot use the current oracle

`evalplus.oracle` spawns one subprocess per call. At roughly 50 ms that is over ten hours
for this input, and it is the wrong shape besides: the 200 draws of one task all run the
same inputs against the same expected outputs. Batch them. One worker process per
`(system, task)` evaluating all 200 draws against the recomputed gold turns 754400 spawns
into 3772, which is the difference between a coffee break and a weekend.

## The build, in order

1. Harden the worker as above. Prove the hardening: a sample that writes a file, one that
   allocates without bound, one that never returns, one that opens a socket. Each must be
   contained and reported, not merely survived.
2. Recompute the gold once per task, from `prompt + canonical_solution` over
   `base_input + plus_input`, and cache it. This is `get_groundtruth()`'s job in EvalPlus
   and it is deterministic.
3. Grade one system end to end, then **byte-compare the resulting `pass@1` against
   EvalPlus's own published figure for that system**. That is a real correctness check on
   the whole pipeline, and it is available: `evalplus.github.io/results.json` carries the
   aggregate per system. Do not proceed past a mismatch.
4. Grade the remaining 22, resumable, appending as they land so an interruption costs
   nothing already done.
5. Emit `(system, item, draw, correct)` as a nonius `Archive`, gzipped with `mtime=0`, the
   way `validation/run_01/derived/composite_archive.jsonl.gz` is written.

## A cheaper option that is not a cheat

Six systems rather than 23 gives a genuine noise band and a product bound at about a
quarter of the cost. Subsetting is legitimate **if the artifact says so**: record which
systems were graded and which were skipped, next to the numbers derived from them
(AUDIT-ALL-0004). A bound applied to a search is reported beside what it withheld, and a
subset is a bound.

## What this unlocks, and what it does not

With an archive the second audit can carry a product-bound prediction, difficulty strata
and a noise band, so it becomes comparable in kind to the first. It still cannot fix the
things the survey named: the items carry no family label, so the reachability table stays
dark; results are anonymous, so result naming remains synthetic; `str` results carry no
live link at all; and every HumanEval item is in every model's training data, which makes
the quarantine gate ambiguous between a shortcut and a memory.
