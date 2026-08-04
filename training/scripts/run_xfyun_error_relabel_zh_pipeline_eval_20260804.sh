#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
RUN="stage2_xfyun_error_relabel_zh_pipeline_eval_20260804_r2"
INTERIM="$ROOT/training/data/interim/experiments/$RUN"
REPORT="$ROOT/training/reports/experiments/$RUN"
mkdir -p "$INTERIM" "$REPORT"
"$ROOT/.venv/bin/python" - "$ROOT/training/data/processed_xfyun_error_relabel_20260803_r1/validation.jsonl" "$INTERIM/validation_zh.jsonl" <<'PY'
import json, sys
source, target = map(__import__('pathlib').Path, sys.argv[1:])
rows = [json.loads(line) for line in source.read_text(encoding='utf-8').splitlines() if line]
zh = [row for row in rows if row.get('language') == 'zh']
target.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in zh), encoding='utf-8')
print(json.dumps({'source_count': len(rows), 'zh_count': len(zh)}, ensure_ascii=False))
PY
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/evaluate.py" --mode pipeline --keras "$ROOT/training/artifacts/experiments/stage2_xfyun_overlay_txn_weight_1p4_20260803_r1/sms_bytecnn_fp32.keras" --test "$INTERIM/validation_zh.jsonl" --stage "$RUN" --output "$REPORT/evaluation.json" --seed 42
