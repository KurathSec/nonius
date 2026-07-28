"""Out-of-process executor for EvalPlus reference solutions.

Runs as ``python -m nonius.adapters._evalplus_worker`` with one JSON request on stdin and
one JSON response on stdout. It exists because the EvalPlus adapter executes third-party
code, and three of that code's failure modes cannot be contained in-process:

* it can loop forever. ``PROBE_INT`` carries 60000 and 10000 (compose.py), and piping
  either into a downstream's loop bound hangs the audit. EvalPlus's own ``trusted_exec``
  applies no time limit at all.
* it can exhaust memory building a list of that size.
* it can leave interpreter state behind, since the reference solutions are exec'd.

``tests/test_layering.py`` walks the adapter's AST for write calls, which says nothing
about what exec'd subject code does. The isolation here is what carries that guarantee, and
the audit says so rather than implying the layering gate covers it.
"""

from __future__ import annotations

import json
import resource
import signal
import sys
from typing import Any

MEM_BYTES = 1 << 30  # 1 GiB
CPU_SECONDS = 2


def _limit() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (MEM_BYTES, MEM_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    # Wall-clock too: RLIMIT_CPU does not fire on a sleeping or blocked process.
    signal.alarm(CPU_SECONDS + 1)


def main() -> int:
    req = json.loads(sys.stdin.read())
    _limit()
    scope: dict[str, Any] = {}
    try:
        exec(req["source"], scope)  # noqa: S102 - executing the subject is the whole job
        fn = scope[req["entry_point"]]
        out = fn(*req["args"])
    except BaseException as exc:  # SystemExit and MemoryError included, deliberately
        json.dump({"ok": False, "error": f"{type(exc).__name__}: {exc}"[:400]}, sys.stdout)
        return 0
    try:
        json.dump({"ok": True, "value": out}, sys.stdout)
    except (TypeError, ValueError):
        # Not JSON-representable, so not a Scalar nonius can carry as a result.
        json.dump({"ok": False, "error": f"unserialisable result: {type(out).__name__}"}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
