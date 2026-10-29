"""Per-window fleet inference share vs. on-time tool calls, from existing replay runs.

Usage: python windows.py OUT.csv bench/recording
Each run is cut into WINDOW_MIN windows. Per window: the share of resident sandbox-time spent
waiting on the model (request -> last byte; proxy holds excluded), the tool calls judged and on
time (compare.analyse, reference strict-ref/strict-speed0, slowest copy, 1.10x, 1 s floor), and
the tool calls completed. One CSV row per (run, window), appended as each run finishes.
"""
import csv
import hashlib
import json
import os
import pickle
import sys
from pathlib import Path

TAPEBOX = Path(os.environ.get("TAPEBOX", "TapeBox")).resolve()
sys.path[:0] = [str(TAPEBOX / "workload"), str(TAPEBOX)]
SCRATCH = Path(__file__).resolve().parent
os.environ.setdefault("TAPEBOX_PLOT_CACHE", str(SCRATCH / "analyse-cache"))
from tapecollect.plot import compare  # noqa: E402

REPLAY = TAPEBOX / "output/replay"
INDEX_CACHE = SCRATCH / "index-cache"
WINDOW_MIN = 10
POLICIES = ["overcommit-0.6", "overcommit-0.8", "overcommit-1.0", "quicksand-v6", "quicksand-v7"]

_index_tape = compare.index_tape


def cached_index_tape(path: str) -> list[dict]:
    """compare.index_tape, memoised on disk by path, size and mtime."""
    st = os.stat(path)
    key = hashlib.sha256(f"{path}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()
    f = INDEX_CACHE / f"{key}.pickle"
    try:
        return pickle.loads(f.read_bytes())
    except (OSError, pickle.UnpicklingError, EOFError):
        pass
    steps = _index_tape(path)
    INDEX_CACHE.mkdir(exist_ok=True)
    tmp = f.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_bytes(pickle.dumps(steps))
    tmp.replace(f)
    return steps


compare.index_tape = cached_index_tape  # the analyse pool forks after this, so its workers use it too


def main() -> None:
    out, rec = Path(sys.argv[1]), sys.argv[2]
    ref = REPLAY / rec / "strict-ref/strict-speed0"
    runs = [REPLAY / rec / p for p in POLICIES if (REPLAY / rec / p / ".complete").exists()]
    exclude = compare.reruns(runs)
    new = not out.exists()
    with open(out, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["recording", "run", "window", "inference_share", "resident_h", "judged", "on_time", "tool_calls_done", "fleet_usd_per_h"])
        for run in runs:
            a = compare.analyse(ref, run, 1.10, 1000, 0, 16, exclude, "max")
            starts = compare.harness_starts(run)
            t0 = a["t0_rep"]
            span = max(a["rep_tool_done"] + [r[0] for r in a["rows"]])
            n = int(span * 60 // WINDOW_MIN) + 1
            wait = [0.0] * n
            resident = [0.0] * n

            def add(acc, lo, hi):  # hours since t0 -> the overlap with each window
                lo, hi = max(lo, 0.0), min(hi, n * WINDOW_MIN / 60)
                i = int(lo * 60 // WINDOW_MIN)
                while lo < hi and i < n:
                    end = min(hi, (i + 1) * WINDOW_MIN / 60)
                    acc[i] += end - lo
                    lo, i = end, i + 1

            for t, (s, e, _) in zip(a["tasks"], a["rep_residency"]):
                add(resident, s, e)
                meta = compare.replay_record(run / t)[0]
                start = starts.get(t) or compare._unit_start(meta, run / t)
                for st in cached_index_tape(str(run / t / "tape.json")):
                    if st["request_at"] is None or st["last_byte_at"] is None:
                        continue
                    add(wait, (start + st["request_at"] / 1000 - t0) / 3600, (start + st["last_byte_at"] / 1000 - t0) / 3600)
            judged, ontime, done = [0] * n, [0] * n, [0] * n
            for r in a["rows"]:
                i = min(n - 1, int(r[0] * 60 // WINDOW_MIN))
                judged[i] += 1
                ontime[i] += bool(r[1])
            for h in a["rep_tool_done"]:
                done[min(n - 1, int(h * 60 // WINDOW_MIN))] += 1
            meta0 = compare.replay_record(run / a["tasks"][0])[0]
            cap = ((meta0.get("admission") or {}).get("node") or {}).get("capacity") or {}
            price = float(cap.get("cpu_millicores", 0)) / 1000 * 0.00003942 * 3600 + float(cap.get("memory_bytes", 0)) / (1 << 30) * 0.00000667 * 3600
            for i in range(n):
                if resident[i] > 0:
                    w.writerow([rec, run.name, i, round(wait[i] / resident[i], 4), round(resident[i], 3), judged[i], ontime[i], done[i], round(price, 3)])
            f.flush()
            print(f"{rec} {run.name}: {n} windows", flush=True)


if __name__ == "__main__":
    main()
