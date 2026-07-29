# Validation: the reference audit

nonius pointed at a real benchmark. Everything below is transcluded from the derived
artifact, so this page cannot drift from the numbers.

Regenerate with:

```console
NONIUS_SPAGHETTI_HOME=/path/to/checkout python validation/spaghetti_audit/run.py
```

--8<-- "validation/spaghetti_audit/derived/audit_report.md"

## The paid run

`validation/run_01/` carries the executed run: the graded archive, the harness that
re-derives every pre-registered threshold from it, and `FINDING.md`, which states what the
run established and at greater length what it does not license. The raw completions are not
committed; their hashes are in `inputs.json`.

--8<-- "validation/run_01/FINDING.md"
