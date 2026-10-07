#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
RUN="stage2_xfyun_overlay_zh_pipeline_analysis_20260803_r1"
WORK="$ROOT/training/data/interim/experiments/$RUN"
REPORT="$ROOT/training/reports/experiments/$RUN"
mkdir -p "$WORK" "$REPORT"
ROOT="$ROOT" WORK="$WORK" "$ROOT/.venv/bin/python" - <<'PY'
import json,os
from pathlib import Path
root=Path(os.environ["ROOT"]); work=Path(os.environ["WORK"])
source=root/"training/data/processed_xfyun_ai_annotation_20260802_r1/validation.jsonl"
rows=[line for line in source.read_text(encoding="utf-8").splitlines() if line.strip() and json.loads(line).get("language")=="zh"]
(work/"validation_zh.jsonl").write_text("\n".join(rows)+"\n",encoding="utf-8")
print(json.dumps({"zh_records":len(rows),"locked_test_read":False}))
PY
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/analyze_transaction_errors.py" \
  --model "$ROOT/training/artifacts/experiments/stage2_xfyun_overlay_txn_weight_1p4_20260803_r1/sms_bytecnn_fp32.keras" \
  --validation "$WORK/validation_zh.jsonl" \
  --output "$REPORT/analysis.json"
