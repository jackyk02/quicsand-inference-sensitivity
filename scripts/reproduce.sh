#!/usr/bin/env bash
# Rebuild data/windows.csv from the raw TapeBox replay traces, then redraw all figures.
# Usage: TAPEBOX=/path/to/TapeBox scripts/reproduce.sh
# Expects traces under $TAPEBOX/output/replay/<bench>/<recording>/<policy>/ (incl. strict-ref/strict-speed0).
set -euo pipefail
: "${TAPEBOX:?set TAPEBOX to a TapeBox checkout with output/replay populated}"
HERE=$(cd "$(dirname "$0")/.." && pwd)
PY="$TAPEBOX/.venv/bin/python"
RECORDINGS=(algotune/run4-max-50 algotune/run1-deepseek-v4.1-flash
            terminal-bench-4.0/run2-medium terminal-bench-4.0/run1-deepseek-v4.1-flash
            terminal-bench-science/run1-rand50)
tmp=$(mktemp -d)
for rec in "${RECORDINGS[@]}"; do
  "$PY" "$HERE/scripts/extract_windows.py" "$tmp/$(echo "$rec" | tr / _).csv" "$rec"
done
files=("$tmp"/*.csv)
{ head -1 "${files[0]}"; for f in "${files[@]}"; do tail -n +2 "$f"; done; } > "$HERE/data/windows.csv"
rm -r "$tmp"
"$PY" "$HERE/scripts/plot_share.py"
