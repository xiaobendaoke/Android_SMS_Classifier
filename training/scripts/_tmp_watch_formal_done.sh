#!/usr/bin/env bash
# Watch continue launcher until done/failed; print final zip path.
set -eu
export PATH="/home/colab/.local/bin:/usr/bin:/bin"
PIDFILE="$HOME/formal_v2_local_rerun.pid"
WIN_ZIP="/mnt/c/Users/woshinibaba/Documents/oppo的项目/Android_SMS_Classifier/training/reports/colab_export_formal_v2.zip"
deadline=$((SECONDS + 20000))
while (( SECONDS < deadline )); do
  LOG=$(ls -t "$HOME"/formal_v2_continue_*.log 2>/dev/null | head -1 || true)
  pid=$(cat "$PIDFILE" 2>/dev/null || true)
  alive=0
  if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
    alive=1
  fi
  echo "==== $(date -Is) alive=$alive pid=${pid:-none} log=${LOG:-none} ===="
  if [[ -n "${LOG:-}" ]]; then
    tail -n 25 "$LOG" || true
    if grep -q 'COPIED_TO' "$LOG"; then
      echo "SUCCESS"
      ls -lh "$WIN_ZIP" || true
      exit 0
    fi
    if grep -qE 'FATAL:|POLL_STATE=failed|POLL_STATE=dead' "$LOG" && [[ "$alive" -eq 0 ]]; then
      echo "FAILED"
      exit 1
    fi
  fi
  if [[ "$alive" -eq 0 ]]; then
    # launcher exited; give it a moment then decide
    sleep 5
    if [[ -f "$WIN_ZIP" ]]; then
      echo "SUCCESS_ZIP_PRESENT"
      ls -lh "$WIN_ZIP"
      exit 0
    fi
    if [[ -n "${LOG:-}" ]] && grep -qE 'FATAL:|POLL_STATE=failed|POLL_STATE=dead' "$LOG"; then
      echo "FAILED"
      exit 1
    fi
    echo "LAUNCHER_EXIT_UNKNOWN"
    exit 2
  fi
  sleep 180
done
echo "TIMEOUT"
exit 3
