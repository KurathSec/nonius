#!/usr/bin/env python3
"""Grade EvalPlus's released samples into a nonius verdict archive. Executes third-party
model-written code, so read ARCHIVE_BUILD.md before running it.

Six systems rather than all 23, deliberately. `Archive.stratum` calls an item `dead` when
EVERY system is perfect and `floored` when every system is zero, so the strata are a
function of how many systems are in the archive. The first subject's archive has four. An
archive of 23 would make subject two's dead and floored fractions incomparable with subject
one's for a reason that has nothing to do with either benchmark, which is the same
unit-mismatch error that corrupted run-01's first analysis. Six spans the capability ladder
and stays comparable. The omission is recorded in the payload, because a subset is a bound
and a bound is reported beside what it withheld (AUDIT-ALL-0004).

    NONIUS_EVALPLUS_DATA=... python validation/evalplus_audit/build_archive.py [--systems N]

Resumable: verdicts append per (system, task) and a re-run skips what is already on disk.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent.parent / "src"))

from nonius.adapters import evalplus as ep  # noqa: E402

SAMPLES = ROOT.parent.parent / ".data" / "evalplus_samples"
OUT = ROOT / "derived" / "verdicts.raw.jsonl"

#: Chosen to span the ladder rather than to flatter it: weakest, weak, mid, mid, strong,
#: frontier as of the 2023 release. Named here so the choice is auditable.
SYSTEMS = [
    "gpt-j", "codegen-2b", "incoder-6b",
    "code-llama-7b", "code-llama-34b", "chatgpt",
]

WORKER = r'''
import json, os, resource, signal, sys, tempfile

def _timeout(signum, frame):
    raise TimeoutError("draw did not terminate")

req = json.loads(sys.stdin.read())
# Third-party code prints. stdout is therefore NOT a usable result channel -- a single
# print() inside a candidate corrupts the JSON and loses the whole 200-draw batch, which is
# how the first smoke test lost one. Results go to a file the parent names; stdout and
# stderr are sent to devnull for the duration of the untrusted call.
_sink = open(os.devnull, "w")
# Contain the damage before a single line of third-party code runs: a scratch cwd nothing
# depends on, a hard address-space cap, and a per-draw alarm. The parent has already
# scrubbed the environment, so a credential in the ambient env is not readable here.
os.chdir(tempfile.mkdtemp(prefix="ep-grade-"))
resource.setrlimit(resource.RLIMIT_AS, (1 << 31, 1 << 31))
signal.signal(signal.SIGALRM, _timeout)

entry, inputs, gold = req["entry_point"], req["inputs"], req["gold"]
out = []
_real_out, _real_err = sys.stdout, sys.stderr
for draw, src in req["draws"]:
    ok = 0
    signal.alarm(req["seconds"])
    sys.stdout = sys.stderr = _sink
    try:
        ns = {}
        exec(src, ns)
        fn = ns[entry]
        ok = 1 if all(fn(*i) == g for i, g in zip(inputs, gold)) else 0
    except BaseException:
        ok = 0
    finally:
        signal.alarm(0)
        sys.stdout, sys.stderr = _real_out, _real_err
    out.append([draw, ok])
with open(req["result_path"], "w") as fh:
    json.dump(out, fh)
'''


def gold_for(row: dict[str, object]) -> tuple[list, list] | None:
    """Recompute the task's expected outputs from its canonical solution.

    This is EvalPlus's own get_groundtruth(), redone here rather than trusted: the point of
    the exercise is an archive whose every value this repository can re-derive.
    """
    src = str(row["prompt"]) + str(row["canonical_solution"])
    entry = str(row["entry_point"])
    ins = list(row["base_input"]) + list(row.get("plus_input") or [])  # type: ignore[arg-type]
    scope: dict[str, object] = {}
    try:
        exec(src, scope)
        fn = scope[entry]
    except BaseException:
        return None
    got = []
    for i in ins:
        try:
            got.append(fn(*i))
        except BaseException:
            return None
    return ins, got


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--systems", type=int, default=len(SYSTEMS))
    ap.add_argument("--seconds", type=int, default=3, help="per-draw wall limit")
    ap.add_argument("--tasks", type=int, default=0, help="0 = all")
    args = ap.parse_args()

    rows = {}
    with gzip.open(ep.data_path(), "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                rows[str(r["task_id"])] = r

    done: set[tuple[str, str]] = set()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").split("\n"):
            if line.strip():
                d = json.loads(line)
                done.add((d["system"], d["task"]))
        print(f"resuming: {len(done)} (system, task) pairs already graded")

    env = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1", "HOME": "/nonexistent"}
    fh = OUT.open("a", encoding="utf-8")
    for system in SYSTEMS[: args.systems]:
        zp = SAMPLES / f"{system}_temp_0.8.zip"
        if not zp.exists():
            print(f"missing {zp}; skipping")
            continue
        z = zipfile.ZipFile(zp)
        by_task: dict[str, list[tuple[int, str]]] = {}
        for n in z.namelist():
            if not n.endswith(".py") or "/HumanEval_" not in n:
                continue
            task = "HumanEval/" + n.split("/HumanEval_")[1].split("/")[0]
            draw = int(n.rsplit("/", 1)[1][:-3])
            by_task.setdefault(task, []).append((draw, n))
        tasks = sorted(by_task)[: args.tasks or None]
        graded = incomplete = 0
        for task in tasks:
            if (system, task) in done or task not in rows:
                continue
            g = gold_for(rows[task])
            if g is None:
                continue
            ins, gold = g
            draws = [[d, z.read(n).decode("utf-8", "replace")] for d, n in sorted(by_task[task])]
            rp = tempfile.mktemp(suffix=".json", prefix="ep-res-")
            req = json.dumps({"entry_point": str(rows[task]["entry_point"]), "inputs": ins,
                              "gold": gold, "seconds": args.seconds, "draws": draws,
                              "result_path": rp})
            # A worker that dies takes its whole batch with it: a draw can call os._exit,
            # trip the address-space cap hard, or segfault a C extension, and none of that
            # is catchable inside the loop. Record WHY rather than writing an empty list,
            # which would silently drop 200 draws and read downstream as 200 failures.
            failure = None
            try:
                proc = subprocess.run([sys.executable, "-c", WORKER], input=req,
                                      capture_output=True, text=True, env=env,
                                      timeout=args.seconds * len(draws) + 60)
                if os.path.exists(rp):
                    verdicts = json.loads(pathlib.Path(rp).read_text())
                    os.unlink(rp)
                else:
                    verdicts, failure = [], f"worker exited {proc.returncode}: {proc.stderr[-200:]}"
            except subprocess.TimeoutExpired:
                verdicts, failure = [], "batch exceeded its wall limit"
            except json.JSONDecodeError:
                verdicts, failure = [], "result file was not JSON"
            if len(verdicts) != len(draws) and failure is None:
                failure = f"worker returned {len(verdicts)} of {len(draws)} draws"
            rec = {"system": system, "task": task, "verdicts": verdicts}
            if failure:
                rec["incomplete"] = failure
                incomplete += 1
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            graded += 1
        print(f"{system}: graded {graded} tasks"
              + (f" ({incomplete} INCOMPLETE)" if incomplete else ""), flush=True)
    fh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
