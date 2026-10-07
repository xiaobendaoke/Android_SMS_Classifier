#!/usr/bin/env bash
set -eu
export PATH="/home/colab/.local/bin:/usr/bin:/bin"
PIDFILE="$HOME/formal_v2_local_rerun.pid"
pid=$(cat "$PIDFILE" 2>/dev/null || echo "")
echo "PIDFILE=$pid"
if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
  ps -p "$pid" -o pid,etime,cmd
else
  echo "LAUNCHER_DEAD"
fi
LOG=$(ls -t "$HOME"/formal_v2_continue_*.log 2>/dev/null | head -1)
echo "LOG=$LOG"
if [[ -n "$LOG" ]]; then
  wc -c "$LOG"
  tail -n 100 "$LOG"
fi
pgrep -af colab | head -20 || true
ls -dt "$HOME"/colab_formal_v2_continue_* 2>/dev/null | head -3
