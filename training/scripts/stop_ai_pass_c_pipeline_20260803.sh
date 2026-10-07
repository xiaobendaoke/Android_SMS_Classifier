#!/usr/bin/env bash
set -euo pipefail

PIPELINES=$(pgrep -f '[r]un_pass_c_resume_[0-9][0-9][0-9].sh' || true)
MODELS=$(pgrep -f '[o]pencode run --model xfyun/xopdeepseekv4flash' || true)
for pid in $PIPELINES $MODELS; do
  kill -TERM "$pid" 2>/dev/null || true
done
printf '{"status":"PASS_C_PIPELINE_TERMINATION_REQUESTED","pipeline_processes":%s,"model_processes":%s}\n' "$(wc -w <<<"$PIPELINES")" "$(wc -w <<<"$MODELS")"
