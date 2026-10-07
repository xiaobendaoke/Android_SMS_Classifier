#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/analyze_xfyun_overlay_length_buckets.py "$ROOT/training/scripts/analyze_xfyun_overlay_length_buckets.py"
"$ROOT/.venv/bin/python" - <<'PY'
import sys
from pathlib import Path
import numpy as np
import tensorflow as tf
ROOT=Path('/home/colab/projects/Android_SMS_Classifier_stage0_baseline_20260802_r2/training')
sys.path.insert(0,str(ROOT))
from src.schema import LABEL_ORDER
from src.train_utils import load_labeled_records,records_to_xy,split_student_logits
from scripts.prepare_transaction_specialist_freeze import coverage_subtype
records=[r for r in load_labeled_records(ROOT/'data/processed_xfyun_ai_annotation_20260802_r1/validation.jsonl') if r.language=='zh']
model=tf.keras.models.load_model(ROOT/'artifacts/experiments/stage2_xfyun_overlay_txn_weight_1p4_20260803_r1/sms_bytecnn_fp32.keras')
x,_=records_to_xy(records,max_bytes=int(model.input_shape[-1]))
logits,_=split_student_logits(np.asarray(model.predict(x,verbose=0)))
for r,index in zip(records,np.argmax(logits,axis=-1)):
    pred=LABEL_ORDER[int(index)]
    if r.label=='TRANSACTION' and pred!='TRANSACTION' and not coverage_subtype(r.text):
        print('ID='+r.id+' PRED='+pred+' TEXT='+r.text)
PY
