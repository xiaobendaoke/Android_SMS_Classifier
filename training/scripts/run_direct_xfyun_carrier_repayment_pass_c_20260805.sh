#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
RUN="xfyun_carrier_repayment_relabel_20260804_r1"
PACK="$ROOT/training/data/interim/annotation/$RUN"
DEMO="/mnt/c/Users/woshinibaba/AppData/Local/Temp/opencode/xf_demo.py"
if [[ -e "$PACK/pass_c_raw.txt" ]]; then
  echo "refusing to overwrite existing Pass C output" >&2
  exit 1
fi
cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/direct_xfyun_call.py "$ROOT/training/scripts/direct_xfyun_call.py"
"$ROOT/.venv/bin/python" "$ROOT/training/scripts/direct_xfyun_call.py" --demo-config "$DEMO" --model xopdeepseekv4flash --prompt "$PACK/pass_c_prompt.txt" > "$PACK/pass_c_raw.txt"
echo '{"run_id":"xfyun_carrier_repayment_relabel_20260804_r1","pass_c":4}'
