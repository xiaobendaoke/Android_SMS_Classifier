#!/usr/bin/env bash
set -u

ROOT="${WSL_RUN_ROOT:-$HOME/projects/Android_SMS_Classifier}"
RUN="$ROOT/training/data/interim/annotation/ai_dual_pass_20260806_r1"
PROBE="$ROOT/training/data/interim/annotation/probe_step_20260807.txt"
OUT="$ROOT/training/data/interim/annotation/probe_step_20260807.out"
ERR="$ROOT/training/data/interim/annotation/probe_step_20260807.err"

export PYTHONPATH="$ROOT/training"
cd "$ROOT"
"$ROOT/.venv/bin/python" - "$RUN" >"$PROBE" <<'PYEOF'
import json, sys
from pathlib import Path

run = Path(sys.argv[1])
rows = [json.loads(line) for line in (run / "blind_rows.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()][:2]
guide = "四分类唯一判断顺序：1) 是否在骗->FRAUD 2) 是否业务结果告知->TRANSACTION 3) 是否正规促销->AD 4) 是否催收/灰产/骚扰->HARASS 5) 其他->NEEDS_REVIEW；看到银行/验证码/链接不等于事务或诈骗，按正文主意图判断，吃不准就 NEEDS_REVIEW。"
lines = [
    "ANNOTATOR_ID: AUTO_STEP3_7FLASH_PASS_A_001",
    "TASK: blind four-class SMS annotation",
    'Return exactly one JSON object per input row as JSONL: {"review_id":"...","id":"...","label":"TRANSACTION|AD|HARASS|FRAUD|NEEDS_REVIEW","confidence":0.0,"rationale":"..."}.',
    "confidence must be 0..1; rationale must be non-empty Chinese.",
    "LABELING GUIDE: " + guide,
    "INPUT RECORDS:",
    json.dumps([{"review_id": r["review_id"], "id": r["id"], "text": r["text"]} for r in rows], ensure_ascii=False),
    "",
]
sys.stdout.write("\n".join(lines))
PYEOF

start=$(date +%s)
timeout --foreground --signal=TERM 300 bash -ic 'opencode run -m nvidia/stepfun-ai/step-3.7-flash "$(cat /home/colab/projects/Android_SMS_Classifier/training/data/interim/annotation/probe_step_20260807.txt)"' >"$OUT" 2>"$ERR"
rc=$?
end=$(date +%s)
echo "RC=$rc ELAPSED=$((end - start))s OUT_BYTES=$(wc -c < "$OUT" 2>/dev/null || echo 0)"
