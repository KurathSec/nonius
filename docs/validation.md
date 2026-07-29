# Validation: the reference audits

nonius pointed at a real benchmark. Everything below is transcluded from the derived
artifact, so this page cannot drift from the numbers.

Regenerate with:

```console
NONIUS_SPAGHETTI_HOME=/path/to/checkout python validation/spaghetti_audit/run.py
```

--8<-- "validation/spaghetti_audit/derived/audit_report.md"

## A second subject

The first audit's subject is a benchmark this project's author also wrote, which is the
obvious objection to it: a tool and its demonstration asset built by the same hand can
agree for reasons that have nothing to do with either being right. `validation/evalplus_audit/`
answers that with a subject nonius did not build, EvalPlus's HumanEval+.

It is not a second confirmation. It found a stage the project did not know it had, because
EvalPlus's items carry explicit contracts and the reference asset's do not: a link can be
live and still not emit, when the downstream contract rejects the piped value. Regenerate
with:

```console
NONIUS_EVALPLUS_DATA=/path/to/HumanEvalPlus.jsonl.gz python validation/evalplus_audit/run.py
python validation/evalplus_audit/run.py --report
```

The verdict archive behind the difficulty rows costs no inference: it is EvalPlus's own 2023
sample release, regraded here. `validation/evalplus_audit/ARCHIVE_BUILD.md` records how it
was built, which six of the 23 released systems are in it, and why the check against
EvalPlus's published `pass@1` is a consistency check rather than the identity check it was
first specified as.

--8<-- "validation/evalplus_audit/derived/audit_report.md"

## The paid run

`validation/run_01/` carries the executed run: the graded archive, the harness that
re-derives every pre-registered threshold from it, and `FINDING.md`, which states what the
run established and at greater length what it does not license. The raw completions are not
committed; their hashes are in `inputs.json`.

--8<-- "validation/run_01/FINDING.md"
