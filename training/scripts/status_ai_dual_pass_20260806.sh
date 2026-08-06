#!/usr/bin/env bash
set -u

ROOT="${WSL_RUN_ROOT:-$HOME/projects/Android_SMS_Classifier}"
RUN="$ROOT/training/data/interim/annotation/ai_dual_pass_20260806_r1"

total=$(ls "$RUN/status" 2>/dev/null | wc -l)
ok=$(grep -l 'exit_code=0' "$RUN"/status/*.txt 2>/dev/null | wc -l)
fail=$(grep -l 'exit_code=[^0]' "$RUN"/status/*.txt 2>/dev/null | wc -l)
echo "STATUS_TOTAL=$total"
echo "STATUS_OK=$ok"
echo "STATUS_FAIL=$fail"
echo "RECONCILE_DONE=$(test -f "$RUN/conflicts.jsonl" && echo yes || echo no)"
echo "REVIEW_READY=$(test -f "$RUN/user_review_table.csv" && echo yes || echo no)"
echo "PROCS=$(pgrep -fc 'opencode run' || true)"
newest=$(ls -t "$RUN/status" 2>/dev/null | head -1)
echo "NEWEST_STATUS=$newest"
if [[ -n "$newest" ]]; then
  echo "NEWEST_STDOUT_BYTES=$(wc -c < "$RUN/stdout/$newest" 2>/dev/null || echo 0)"
fi
echo "PROC_ELAPSED=$(ps -eo etime,comm | grep opencode | head -1 | awk '{print $1}')"
