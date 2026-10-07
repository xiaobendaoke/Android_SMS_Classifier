#!/usr/bin/env python3
"""Prepare local-only A/B blind packs for newly unreviewed transaction misses."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.prepare_transaction_specialist_freeze import coverage_subtype
from src.schema import LABEL_ORDER
from src.train_utils import load_labeled_records, records_to_xy, split_student_logits

RUN = "xfyun_unmatched_transaction_relabel_20260805_r1"
PACK = ROOT / "data" / "interim" / "annotation" / RUN
SAFE = ROOT / "reports" / "experiments" / f"{RUN}_export"
VALIDATION = ROOT / "data" / "processed_xfyun_carrier_repayment_relabel_20260804_r1" / "validation.jsonl"
MODEL = ROOT / "artifacts" / "experiments" / "stage2_xfyun_overlay_txn_weight_1p4_20260803_r1" / "sms_bytecnn_fp32.keras"
PREVIOUS_PACK = ROOT / "data" / "interim" / "annotation" / "xfyun_error_relabel_20260803_r1" / "pass_a_blind.jsonl"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ids_from(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {json.loads(line)["id"] for line in path.read_text(encoding="utf-8").splitlines() if line}


def main() -> int:
    if PACK.exists() or SAFE.exists():
        raise SystemExit(f"refusing to overwrite run_id: {RUN}")
    import tensorflow as tf

    records = [record for record in load_labeled_records(VALIDATION) if record.language == "zh"]
    model = tf.keras.models.load_model(MODEL)
    x, _ = records_to_xy(records, max_bytes=int(model.input_shape[-1]))
    logits, _ = split_student_logits(np.asarray(model.predict(x, verbose=0)))
    previous = ids_from(PREVIOUS_PACK)
    selected = [
        record
        for record, index in zip(records, np.argmax(logits, axis=-1))
        if record.label == "TRANSACTION"
        and LABEL_ORDER[int(index)] != "TRANSACTION"
        and not coverage_subtype(record.text)
        and record.id not in previous
    ][:25]
    if not selected:
        raise SystemExit("no newly unreviewed unmatched transaction misses")
    PACK.mkdir(parents=True)
    SAFE.mkdir(parents=True)
    rows = [
        {"review_key": hashlib.sha256((RUN + record.id).encode()).hexdigest()[:16], "id": record.id, "text": record.text}
        for record in selected
    ]
    for name, payload in (("pass_a", rows), ("pass_b", list(reversed(rows)))):
        (PACK / f"{name}_blind.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in payload), encoding="utf-8")
    manifest = {
        "run_id": RUN, "status": "PENDING_EXTERNAL_APPROVAL", "claim_allowed": False,
        "human_verified": False, "formal_acceptance_allowed": False, "locked_test_read": False,
        "candidate_count": len(rows), "excluded_previously_reviewed": len(previous),
        "blind_fields": ["review_key", "id", "text"],
        "excluded_fields": ["prior_label", "model_prediction", "confidence", "test", "pass_a", "pass_b"],
        "pass_a_sha256": sha256(PACK / "pass_a_blind.jsonl"),
        "pass_b_sha256": sha256(PACK / "pass_b_blind.jsonl"),
    }
    (SAFE / "preparation_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
