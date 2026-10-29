"""On-time tool calls against the fleet inference share, from data/windows.csv.

Writes eval_inference_share.{pdf,png} (double column: on-time tool calls per workload) and
eval_inference_share_pooled.{pdf,png} (single column: on-time tool calls pooled over workloads).
"""
import collections
import os
import csv
import sys
from pathlib import Path

TAPEBOX = Path(os.environ.get("TAPEBOX", "TapeBox")).resolve()
sys.path.insert(0, str(TAPEBOX / "workload"))
from tapecollect.plot import style  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "figures"
MIN_JUDGED = 20  # a window with fewer judged tool calls says nothing about on-time tool calls
MIN_WINDOWS = 3  # cells with fewer windows are drawn hollow
# Most inference time on the left, so the axis reads toward faster models (less time waiting) on the right.
BINS = [(0.7, 1.01, ">70"), (0.5, 0.7, "50–70"), (0.3, 0.5, "30–50"), (0.0, 0.3, "<30")]
# Overcommit (threshold 1.0) in the paper's vermillion, QuicSand in its green; markers and
# line styles are the second channel.
SERIES = [("overcommit-1.0", "Overcommit", style.VERMILLION, "s", "--"),
          ("quicksand", "QuicSand", style.GREEN, "D", "-")]
PANELS = [("algotune/run4-max-50", "AlgoTune\nSonnet"), ("algotune/run1-deepseek-v4.1-flash", "AlgoTune\nDeepSeek"),
          ("terminal-bench-4.0/run2-medium", "Terminal-Bench 4.0\nSonnet"),
          ("terminal-bench-4.0/run1-deepseek-v4.1-flash", "Terminal-Bench 4.0\nDeepSeek"),
          ("terminal-bench-science/run1-rand50", "Terminal-Bench Science\nSonnet")]


# The metrics, as the axes state them. On-time tool call: a tool call is on time when its execution
# (proxy hold excluded) takes at most 1.1x the slowest of five uncontended strict runs of the same
# call (1 s floor). Inference share: per 10-minute window, sandbox-time spent waiting on a model
# response over sandbox-time resident.
Y_LABEL = "On-time tool call (%)"
X_LABEL = "Model Inference Time (% of sandbox time), per 10-min window"
X_LABEL_SHORT = "Model Inference Time (% of sandbox time),\nper 10-min window"


def family(run: str) -> str:
    return "quicksand" if run.startswith("quicksand") else run


def load():
    agg = collections.defaultdict(lambda: [0, 0, 0, 0.0])  # judged, on time, windows, fleet $/h
    for r in csv.DictReader(open(HERE.parent / "data" / "windows.csv")):
        judged = int(r["judged"])
        if judged < MIN_JUDGED:
            continue
        share = float(r["inference_share"])
        b = next(i for i, (lo, hi, _) in enumerate(BINS) if lo <= share < hi)
        for rec in (r["recording"], "all"):
            a = agg[(rec, family(r["run"]), b)]
            a[0] += judged
            a[1] += int(r["on_time"])
            a[2] += 1
            a[3] = float(r["fleet_usd_per_h"])
    return agg


def series(agg, rec, fam, metric):
    xs, ys, ns = [], [], []
    for b in range(len(BINS)):
        a = agg.get((rec, fam, b))
        if not a or not a[1]:
            continue
        xs.append(b)
        ys.append(100 * a[1] / a[0] if metric == "on-time tool calls" else 1000 * a[3] * a[2] / 6 / a[1])
        ns.append(a[2])
    return xs, ys, ns


def draw(ax, agg, rec, metric):
    for fam, label, color, marker, ls in SERIES:
        xs, ys, ns = series(agg, rec, fam, metric)
        if not xs:
            continue
        lw = 1.6 if fam == "quicksand" else 1.0
        ax.plot(xs, ys, ls=ls, color=color, lw=lw, label=label, zorder=3 if fam == "quicksand" else 2)
        for x, y, n in zip(xs, ys, ns):
            ax.plot(x, y, marker=marker, ms=4.5, color=color, mfc=color if n >= MIN_WINDOWS else "white",
                    mec="white" if n >= MIN_WINDOWS else color, mew=0.6 if n >= MIN_WINDOWS else 0.9, ls="none",
                    zorder=4 if fam == "quicksand" else 3)
    ax.set_xticks(range(len(BINS)), [lab for *_, lab in BINS])
    ax.set_xlim(-0.35, len(BINS) - 0.65)


def main() -> None:
    style.apply()
    agg = load()

    # Main text: pooled over every judged tool call of the five workloads, single column.
    fig, ax = plt.subplots(figsize=(style.SINGLE_COLUMN, 2.0))
    draw(ax, agg, "all", "on-time tool calls")
    ax.set_ylim(30, 100)
    ax.set_xlabel(X_LABEL_SHORT)
    ax.set_ylabel(Y_LABEL)
    # The gap the figure is about: QuicSand against the most aggressive threshold where
    # the fewest sandboxes are waiting on the model.
    (_, qs, _), (_, oc, _) = series(agg, "all", "quicksand", "on-time tool calls"), series(agg, "all", "overcommit-1.0", "on-time tool calls")
    ax.annotate("", xy=(2.88, qs[-1] - 1), xytext=(2.88, oc[-1] + 1),
                arrowprops=dict(arrowstyle="<->", color=style.GREY, lw=0.7, shrinkA=0, shrinkB=0))
    ax.text(2.8, (qs[-1] + oc[-1]) / 2, f"+{qs[-1] - oc[-1]:.0f} pts", fontsize=7, color=style.GREY, va="center", ha="right")
    style.legend_above(ax, ncol=2)
    for p in style.save(fig, OUT / "on_time_vs_inference_share"):
        print(p)

    # Appendix: one panel per workload, double column.
    fig, axes = plt.subplots(1, len(PANELS), figsize=(style.DOUBLE_COLUMN, 1.9), sharey=True)
    for ax, (rec, title) in zip(axes, PANELS):
        draw(ax, agg, rec, "on-time tool calls")
        ax.set_title(title, fontsize=7.5)
        ax.set_ylim(20, 102)
    axes[0].set_ylabel(Y_LABEL)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=4)
    fig.supxlabel(X_LABEL, fontsize=8, y=0.0)
    fig.tight_layout(h_pad=0.6, w_pad=0.4)
    for p in style.save(fig, OUT / "on_time_vs_inference_share_by_workload"):
        print(p)


if __name__ == "__main__":
    main()
