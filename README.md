# QuicSand: sensitivity to model inference time

Code, data and figures behind Appendix B of the QuicSand paper ("Sensitivity to Inference Time"). The write-up is in [APPENDIX_B.md](APPENDIX_B.md); this file explains how to reproduce the plots.

## What is measured

Existing TapeBox replay runs are cut into 10-minute windows. For each window we record:

- **On-time tool call (%)**: the share of judged tool calls whose execution time (proxy holds excluded) is at most 1.10x the slowest of five uncontended strict-reservation reruns of the same call, with reference times floored at 1 s.
- **Share of sandbox time waiting on the model** (`inference_share`): time spent between a model request and its last response byte, divided by resident sandbox time.
- **Median model response latency** (`median_model_s`): the median request-to-last-byte time of the model calls issued in the window.

Windows with fewer than 20 judged tool calls are dropped (for latency, also windows with fewer than 5 model calls). We compare QuicSand (`quicksand-v6` and `quicksand-v7` pooled) with `overcommit-1.0`, shown as "Overcommit".

## Results

| Share of sandbox time waiting on the model | Overcommit | QuicSand |
|---|---|---|
| < 30% | 37% | 85% |
| 30–50% | 58% | 88% |
| 50–70% | 74% | 94% |
| > 70% | 87% | 96% |

On-time tool calls (%), pooled over AlgoTune, Terminal-Bench 4.0 (Sonnet and DeepSeek) and Terminal-Bench Science. Overcommit loses on-time calls as fewer sandboxes are waiting on the model; QuicSand stays at 85–96%.

| Median model latency per window | Overcommit | QuicSand |
|---|---|---|
| < 5 s | 76% | 90% |
| 5–10 s | 46% | 89% |
| 10–15 s | 66% | 91% |
| > 15 s | 49% | 94% |

Median latency shows no clean trend for Overcommit once workloads are pooled: windows with different latencies come from different workloads and models (for example AlgoTune with Sonnet is almost entirely above 13 s), so latency is confounded with load. The share-of-time metric captures the load effect directly.

Both analyses are observational. A controlled sweep (TapeBox `--speed`) would separate load from latency.

## Layout

```
data/windows.csv       one row per (recording, policy run, 10-min window); 552 rows
scripts/extract_windows.py   builds windows.csv from TapeBox replay output (needs the raw traces)
scripts/plot_share.py        figures against share of sandbox time waiting on the model
scripts/plot_latency.py      figures against median model latency
figures/                     the generated PDFs and PNGs
APPENDIX_B.md                the paper text and captions
```

`windows.csv` columns: `recording, run, window, inference_share, resident_h, judged, on_time, tool_calls_done, fleet_usd_per_h, median_model_s, model_calls`. The `fleet_usd_per_h` column is left over from an earlier cost analysis and is unused.

## Reproduce the figures (no raw traces needed)

```bash
git clone https://github.com/depetrol/TapeBox     # tested at 1dadbd09fc6b6082fcbef9c8f2fde671e615a632
cd TapeBox && python -m venv .venv && .venv/bin/pip install -e .[host] && cd ..
export TAPEBOX=$PWD/TapeBox                       # only the plot style module is used
$TAPEBOX/.venv/bin/python scripts/plot_share.py   # writes figures/on_time_vs_inference_share*.{pdf,png}
$TAPEBOX/.venv/bin/python scripts/plot_latency.py # writes figures/on_time_vs_model_latency*.{pdf,png}
```

Any Python with `matplotlib` works if `TAPEBOX` points at a TapeBox checkout (the scripts import `tapecollect.plot.style` from it).

## Regenerate `windows.csv` (needs the raw replay traces)

The raw traces are not in this repository (about 1.1 TB). They come from the TapeBox replay runs of `strict`, `overcommit` and `quicksand` on AlgoTune, Terminal-Bench 4.0 and Terminal-Bench Science. Place them under `$TAPEBOX/output/replay/<bench>/<recording>/<policy>/` (including `strict-ref/strict-speed0`, the uncontended reference), then run one command per recording and concatenate the results (header once):

```bash
for rec in algotune/run4-max-50 algotune/run1-deepseek-v4.1-flash \
           terminal-bench-4.0/run2-medium terminal-bench-4.0/run1-deepseek-v4.1-flash \
           terminal-bench-science/run1-rand50; do
  $TAPEBOX/.venv/bin/python scripts/extract_windows.py out-$(basename $rec).csv $rec
done
```

`extract_windows.py` calls TapeBox's `tapecollect.plot.compare` with `--reference-stat max`, a 1.10 threshold and a 1000 ms floor, the on-time definition from TapeBox commit 5a1580d.

## Caveats

- The result is observational: windows with few sandboxes waiting on the model also tend to be the most heavily loaded.
- "QuicSand" pools the `quicksand-v6` and `quicksand-v7` runs.
- ScienceAgentBench is excluded because its fleet never saturates.
