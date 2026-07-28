# Security

## Scope

nonius imports and calls a **practitioner-supplied oracle module** and, optionally, a
practitioner-supplied realizer. Loading a Python file executes it. Point nonius only at
oracle modules you trust, exactly as you would with any test harness or plugin.

nonius itself opens no sockets and makes no network requests. `tests/test_refusals.py`
asserts this by making `socket.socket` raise during a full audit and compose cycle.

The one module that can cause spending is `src/nonius/run.py`, and it refuses unless given
a pre-registration and an explicit authorisation; the `nonius run` verb has no code path
that spends at all.

In scope: anything that lets a crafted **manifest or archive**, which is data rather than
code, cause
code execution, a file write outside a path you named, or an unbounded resource
consumption that a cap should have covered.

Out of scope: a malicious oracle module. That is code you chose to load.

## Reporting

Please report privately through GitHub's security advisory form on the repository rather
than in a public issue. Include the output of `nonius env`, which states the package
version, the composition spec version and the probe set. Those are the three things that
determine what nonius decided.
