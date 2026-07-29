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
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent.parent / "src"))

from nonius.adapters import evalplus as ep  # noqa: E402

# Some HumanEval golds are integers with more than 4300 digits (factorial- and
# fibonacci-shaped tasks), and Python 3.11 refuses to str() those by default. The guard
# exists against a DoS through untrusted input; what is serialised here is the REFERENCE
# gold computed from EvalPlus's own canonical solution, so lifting it is safe in this
# process. The worker never needs it: it compares with == and returns only ints.
sys.set_int_max_str_digits(0)

SAMPLES = ROOT.parent.parent / ".data" / "evalplus_samples"
OUT = ROOT / "derived" / "verdicts.raw.jsonl"
ARCHIVE = ROOT / "derived" / "singleton_archive.jsonl.gz"
INCOMPLETE = ROOT / "derived" / "incomplete.json"

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

# Same 4300-digit guard as the parent, hit here on the way IN: json.loads has to build
# those integers to compare against them. Bounded by RLIMIT_CPU and the per-draw alarm, so
# a candidate that tries to abuse the lifted limit still cannot run away.
sys.set_int_max_str_digits(0)
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


#: EvalPlus's own leaderboard figures, transcribed from the source below on 2026-07-29.
#: External constants, so they are pinned here with their provenance rather than fetched at
#: run time: a check whose reference value can change under it is not a check.
PUBLISHED = {
    "gpt-j": 12.2, "incoder-6b": 15.9, "codegen-2b": 24.4,
    "code-llama-7b": 37.8, "code-llama-34b": 51.8, "chatgpt": 73.2,
}
PUBLISHED_SOURCE = "https://evalplus.github.io/results.json"


def check() -> int:
    """Compare the archive's pass@1 against EvalPlus's published figures.

    ARCHIVE_BUILD.md step 3 asked for a byte-comparison against the published pass@1. That
    check is NOT available, and running it as specified would have repeated the unit
    mismatch that corrupted run-01's KT-4. The published figure is greedy decoding at
    temperature 0; this archive is 200 samples per task at temperature 0.8. Those are
    different estimands, and equality is the wrong expectation rather than a passing bar.

    What survives is weaker and still has force, because both parts could fail:

    * the ordering over the six systems must reproduce the published ordering exactly;
    * every measured value must sit strictly BELOW its published figure, since sampling at
      0.8 is worse than greedy and HumanEval+ grades against the plus inputs as well.

    The second holds whichever split the published number refers to: if it is the base
    split, the plus inputs widen the same gap rather than narrowing it, so the direction of
    the inequality does not depend on disambiguating it.
    """
    arch = json.loads("{}")
    total: dict[str, int] = {}
    right: dict[str, int] = {}
    with gzip.open(ARCHIVE, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                d = json.loads(line)
                s = str(d["system"])
                total[s] = total.get(s, 0) + 1
                right[s] = right.get(s, 0) + int(d["correct"])
    measured = {s: right[s] / total[s] for s in sorted(total)}
    ours = [s for s, _ in sorted(measured.items(), key=lambda kv: kv[1])]
    theirs = [s for s, _ in sorted(PUBLISHED.items(), key=lambda kv: kv[1])]
    below = {s: measured[s] * 100 < PUBLISHED[s] for s in measured}
    arch = {
        "estimand": "pass@1 over 200 samples per task at temperature 0.8, HumanEval+ inputs",
        "published_estimand": "greedy decoding, pass@1, as served by the leaderboard",
        "published_source": PUBLISHED_SOURCE,
        "comparable": False,
        "why_not_comparable": "different decoding regimes; equality is not the expectation. "
                              "See check() for what is tested instead.",
        "measured_pass_at_1": {s: round(v, 4) for s, v in measured.items()},
        "published_pass_at_1": dict(sorted(PUBLISHED.items())),
        "sampling_ratio": {s: round(measured[s] * 100 / PUBLISHED[s], 4) for s in measured},
        "ordering_ours": ours,
        "ordering_published": theirs,
        "ordering_agrees": ours == theirs,
        "all_below_greedy": all(below.values()),
        "systems_below_greedy": dict(sorted(below.items())),
    }
    (ROOT / "derived" / "pass_at_1.json").write_text(
        json.dumps(arch, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ok = arch["ordering_agrees"] and arch["all_below_greedy"]
    print(f"ordering agrees: {arch['ordering_agrees']}; all below greedy: "
          f"{arch['all_below_greedy']}")
    for s in ours:
        print(f"  {s:16s} ours {measured[s]*100:6.2f}  published {PUBLISHED[s]:5.1f}")
    return 0 if ok else 2


def emit() -> int:
    """Fold the raw grades into the nonius archive the audit reads.

    Separate from grading so it is cheap to re-run, and committed rather than done by hand:
    an artifact whose derivation lives only in a shell history is a number with no
    provenance, which this repository does not allow.

    Later records win. Grading appends, so a batch regraded after a failure leaves the
    original line in place, and the resume set treats an incomplete batch as unfinished.
    """
    latest: dict[tuple[str, str], dict[str, object]] = {}
    for line in OUT.read_text(encoding="utf-8").split("\n"):
        if line.strip():
            d = json.loads(line)
            latest[(str(d["system"]), str(d["task"]))] = d

    rows, bad = [], []
    for (system, task), d in latest.items():
        if d.get("incomplete"):
            bad.append({"system": system, "task": task, "reason": str(d["incomplete"])})
        for draw, ok in d["verdicts"]:  # type: ignore[union-attr]
            rows.append({"correct": int(ok), "draw": int(draw), "item": task, "system": system})
    # Sorted, and gzipped with mtime=0: the artifact is a function of its inputs alone, so
    # a rebuild on identical grades is byte-identical (tests/test_determinism.py's rule).
    rows.sort(key=lambda r: (str(r["item"]), str(r["system"]), int(r["draw"])))
    body = "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows).encode("utf-8")
    # filename="" as well as mtime=0: gzip stores the source name in its header, so writing
    # by path would stamp the artifact with where it was built. Both fields are clocks or
    # paths leaking into a file that must be a function of its inputs alone.
    with open(ARCHIVE, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            gz.write(body)
    bad.sort(key=lambda b: (b["system"], b["task"]))
    INCOMPLETE.write_text(json.dumps({
        "batches": bad, "count": len(bad), "of_pairs": len(latest),
        "note": "batches whose worker died; recorded rather than scored as failures, "
                "because an empty verdict list reads downstream as 200 model failures "
                "rather than as no measurement (AUDIT-ALL-0004)",
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(rows)} verdicts over {len(latest)} pairs -> {ARCHIVE.name}; "
          f"{len(bad)} incomplete")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit", action="store_true", help="fold existing grades into the archive")
    ap.add_argument("--check", action="store_true", help="compare pass@1 against EvalPlus's own")
    ap.add_argument("--systems", type=int, default=len(SYSTEMS))
    ap.add_argument("--seconds", type=int, default=3, help="per-draw wall limit")
    ap.add_argument("--tasks", type=int, default=0, help="0 = all")
    # The parent only waits on subprocesses, so threads are the right pool: the work is in
    # the children and the GIL is never contended. Default leaves two cores for the
    # machine, because every worker is CPU-bound and a weak model's output is mostly
    # non-terminating code burning its full alarm.
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    args = ap.parse_args()
    if args.emit:
        return emit()
    if args.check:
        return check()

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
                # An incomplete batch is unfinished, so a resume retries it. Before the
                # per-draw fallback existed there was nothing to gain by retrying and these
                # counted as done, which quietly froze seven holes into the archive.
                if d.get("incomplete"):
                    done.discard((d["system"], d["task"]))
                else:
                    done.add((d["system"], d["task"]))
        print(f"resuming: {len(done)} (system, task) pairs already graded")

    env = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1", "HOME": "/nonexistent"}
    fh = OUT.open("a", encoding="utf-8")
    lock = threading.Lock()
    counts: dict[str, list[int]] = {}

    def grade(system: str, task: str, draws: list[list[object]]) -> None:
        """One (system, task) batch. Runs in a thread; the real work is the child.

        Never raises. A task that cannot be prepared is recorded as incomplete, because a
        thrown exception here takes the whole pool down and discards every batch already in
        flight -- which is how a single 4300-digit gold destroyed a six-minute run.
        """
        try:
            _grade(system, task, draws)
        except Exception as exc:  # noqa: BLE001 - recorded, never fatal
            with lock:
                fh.write(json.dumps({"system": system, "task": task, "verdicts": [],
                                     "incomplete": f"{type(exc).__name__}: {exc}"[:300]}) + "\n")
                fh.flush()
                counts.setdefault(system, [0, 0])[1] += 1

    def _one(task: str, ins: list, gold: list, draw: list[object]) -> list[object] | None:
        """One draw in its own worker. None means unmeasurable, which is not the same as 0."""
        rp = tempfile.mktemp(suffix=".json", prefix="ep-one-")
        req = json.dumps({"entry_point": str(rows[task]["entry_point"]), "inputs": ins,
                          "gold": gold, "seconds": args.seconds, "draws": [draw],
                          "result_path": rp})
        try:
            subprocess.run([sys.executable, "-c", WORKER], input=req, capture_output=True,
                           text=True, env=env, timeout=args.seconds + 30)
            if not os.path.exists(rp):
                return None
            out = json.loads(pathlib.Path(rp).read_text())
            os.unlink(rp)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            return None
        return out[0] if len(out) == 1 else None

    def _grade(system: str, task: str, draws: list[list[object]]) -> None:
        g = gold_for(rows[task])
        if g is None:
            return
        ins, gold = g
        rp = tempfile.mktemp(suffix=".json", prefix="ep-res-")
        req = json.dumps({"entry_point": str(rows[task]["entry_point"]), "inputs": ins,
                          "gold": gold, "seconds": args.seconds, "draws": draws,
                          "result_path": rp})
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
        # A batch shares one interpreter, so a single draw that reaches past the sandbox --
        # os._exit(), closing fd 2, exhausting RLIMIT_AS mid-serialisation -- kills the
        # other 199 with it. Seven batches died that way on the first build, and losing 1400
        # verdicts to 7 bad draws is a harness artefact masquerading as missing data. Retry
        # in isolation: one worker per draw, so only the draw that actually misbehaves goes
        # unmeasured, and it is named rather than scored 0. Slow, so only on failure.
        if failure is not None and len(draws) > 1:
            verdicts, lost = [], []
            for one in draws:
                got = _one(task, ins, gold, one)
                if got is None:
                    lost.append(one[0])
                else:
                    verdicts.append(got)
            failure = (
                f"batch failed ({failure}); regraded per draw, "
                f"{len(lost)} of {len(draws)} unmeasurable: {sorted(lost)[:10]}"
            ) if lost else None
        rec: dict[str, object] = {"system": system, "task": task, "verdicts": verdicts}
        if failure:
            rec["incomplete"] = failure
        # One writer at a time: the append is a whole line and must not interleave.
        with lock:
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            c = counts.setdefault(system, [0, 0])
            c[0] += 1
            c[1] += 1 if failure else 0
            total = sum(x[0] for x in counts.values())
            if total % 25 == 0:
                bad = sum(x[1] for x in counts.values())
                print(f"  {total} pairs graded" + (f", {bad} INCOMPLETE" if bad else ""),
                      flush=True)
    pending: list[tuple[str, str, list[list[object]]]] = []
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
        for task in tasks:
            if (system, task) in done or task not in rows:
                continue
            draws = [[d, z.read(n).decode("utf-8", "replace")]
                     for d, n in sorted(by_task[task])]
            pending.append((system, task, draws))
    print(f"{len(pending)} (system, task) pairs to grade on {args.jobs} workers", flush=True)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        list(pool.map(lambda a: grade(*a), pending))
    fh.close()
    bad = sum(x[1] for x in counts.values())
    for system in sorted(counts):
        c = counts[system]
        print(f"{system}: graded {c[0]}" + (f" ({c[1]} INCOMPLETE)" if c[1] else ""))
    print(f"total {sum(x[0] for x in counts.values())} graded, {bad} incomplete")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
