#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH=/mnt/c/dev/Android_SMS_Classifier/training
export TF_CPP_MIN_LOG_LEVEL=2
/home/colab/projects/Android_SMS_Classifier/.venv/bin/python -u - <<'PY'
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import tensorflow as tf
from src.metrics import summarize_metrics
from src.schema import LABEL_ORDER
from src.train_utils import load_labeled_records, records_to_xy, softmax_np

root = Path("/mnt/c/dev/Android_SMS_Classifier/training")
models = {
    "default_distill": root / "artifacts/student/sms_bytecnn_fp32.keras",
    "clipped_distill": root / "artifacts/experiments/student_v4_distill_clipped/sms_bytecnn_fp32.keras",
}
val = load_labeled_records(root / "data/processed/validation.jsonl")
x, y = records_to_xy(val, max_bytes=512)
y_true = [LABEL_ORDER[i] for i in y.tolist()]
txn_idx = LABEL_ORDER.index("TRANSACTION")
thresholds = [round(t, 2) for t in np.arange(0.10, 0.91, 0.05)]
out = {"locked_test_read": False, "models": {}}

for name, path in models.items():
    if not path.exists():
        continue
    model = tf.keras.models.load_model(path)
    logits = model.predict(x, verbose=0)
    probs = softmax_np(logits)
    rows = []
    for thr in thresholds:
        preds = []
        for p in probs:
            if p[txn_idx] >= thr:
                preds.append("TRANSACTION")
            else:
                # among non-txn, pick max
                masked = p.copy()
                masked[txn_idx] = -1.0
                preds.append(LABEL_ORDER[int(np.argmax(masked))])
        m = summarize_metrics(y_true, preds, LABEL_ORDER)
        rows.append({
            "txn_threshold": thr,
            "macro_f1": float(m["macro_f1"]),
            "transaction_recall": float(m["per_class"]["TRANSACTION"]["recall"]),
            "transaction_precision": float(m["per_class"]["TRANSACTION"]["precision"]),
            "harass_f1": float(m["per_class"]["HARASS"]["f1"]),
            "fraud_recall": float(m["per_class"]["FRAUD"]["recall"]),
        })
    # find best under soft constraints
    hit = [r for r in rows if r["transaction_recall"] >= 0.985]
    near = min(rows, key=lambda r: abs(r["transaction_recall"] - 0.985))
    out["models"][name] = {
        "curve": rows,
        "rows_meeting_txn_recall_0.985": hit,
        "closest_to_0.985": near,
    }
    print(name, "closest", near)
    if hit:
        best = max(hit, key=lambda r: (r["transaction_precision"], r["macro_f1"]))
        print(name, "best@>=0.985", best)
    else:
        print(name, "NO threshold reaches txn_recall>=0.985")

path = root / "reports/metrics/student_v4_threshold_sweep.json"
path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("Wrote", path)
PY
