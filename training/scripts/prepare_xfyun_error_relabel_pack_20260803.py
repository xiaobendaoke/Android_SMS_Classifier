#!/usr/bin/env python3
"""Prepare local-only independent blind packs for unmatched transaction errors."""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.prepare_transaction_specialist_freeze import coverage_subtype
from src.schema import LABEL_ORDER
from src.train_utils import load_labeled_records, records_to_xy, split_student_logits

RUN = "xfyun_error_relabel_20260803_r1"
PACK = ROOT / "data/interim/annotation" / RUN
SAFE = ROOT / "reports/experiments" / f"{RUN}_export"
MODEL = ROOT / "artifacts/experiments/stage2_xfyun_overlay_txn_weight_1p4_20260803_r1/sms_bytecnn_fp32.keras"
VALIDATION = ROOT / "data/processed_xfyun_ai_annotation_20260802_r1/validation.jsonl"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if PACK.exists() or SAFE.exists():
        raise SystemExit(f"refusing to overwrite run_id: {RUN}")
    import tensorflow as tf
    records = [row for row in load_labeled_records(VALIDATION) if row.language == "zh"]
    model = tf.keras.models.load_model(MODEL)
    x, _ = records_to_xy(records, max_bytes=int(model.input_shape[-1]))
    logits, _ = split_student_logits(np.asarray(model.predict(x, verbose=0)))
    selected = [row for row, index in zip(records, np.argmax(logits, axis=-1)) if row.label == "TRANSACTION" and LABEL_ORDER[int(index)] != "TRANSACTION" and not coverage_subtype(row.text)]
    PACK.mkdir(parents=True)
    SAFE.mkdir(parents=True)
    rows = [{"review_key": hashlib.sha256((RUN + row.id).encode()).hexdigest()[:16], "id": row.id, "text": row.text} for row in selected]
    for name, payload in (("pass_a", rows), ("pass_b", random.Random(20260803).sample(rows, len(rows)))):
        path = PACK / f"{name}_blind.jsonl"
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in payload), encoding="utf-8")
    manifest = {"run_id": RUN, "status": "PENDING_EXTERNAL_APPROVAL", "claim_allowed": False, "human_verified": False, "formal_acceptance_allowed": False, "locked_test_read": False, "candidate_count": len(rows), "input_model_sha256": sha(MODEL), "validation_sha256": sha(VALIDATION), "pass_a_sha256": sha(PACK / "pass_a_blind.jsonl"), "pass_b_sha256": sha(PACK / "pass_b_blind.jsonl"), "blind_fields": ["review_key", "id", "text"], "excluded_fields": ["prior_label", "model_prediction", "confidence", "pass_a", "pass_b", "test"]}
    (SAFE / "preparation_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
