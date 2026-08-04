#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
TARGET="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments/stage2_xfyun_class_weight_effect_20260804_r1_export"
mkdir -p "$TARGET"
"$ROOT/.venv/bin/python" - "$ROOT" "$TARGET/analysis.json" <<'PY'
import json, sys
from pathlib import Path
import numpy as np
root, target = map(Path, sys.argv[1:])
sys.path.insert(0, str(root / 'training'))
from src.schema import LABEL_ORDER
from src.train_utils import balanced_class_weights, load_labeled_records
rows = [r for r in load_labeled_records(root / 'training/data/processed_xfyun_ai_annotation_20260802_r1/train.jsonl') if r.language == 'zh']
y = np.array([LABEL_ORDER.index(r.label) for r in rows])
def values(multiplier, clip):
    w = balanced_class_weights(y, 4, multipliers={'TRANSACTION': multiplier, 'AD': 1.0, 'HARASS': 1.0, 'FRAUD': 1.0})
    before = w.tolist()
    if clip:
        w = np.clip(w, *clip); w *= 4.0 / float(w.sum())
    return {'pre_clip': before, 'effective': w.tolist()}
out = {'locked_test_read': False, 'zh_train_count': len(rows), 'class_counts': dict(zip(LABEL_ORDER, np.bincount(y, minlength=4).tolist())), 'weight_cases': {'txn_1p1_clip': values(1.1, [0.75, 1.5]), 'txn_1p4_clip': values(1.4, [0.75, 1.5]), 'txn_1p4_no_clip': values(1.4, None)}}
target.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(out, ensure_ascii=False))
PY
