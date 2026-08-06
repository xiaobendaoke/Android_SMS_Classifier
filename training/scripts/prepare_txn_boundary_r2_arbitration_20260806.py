#!/usr/bin/env python3
"""Prepare blind packs for the second-round TRANSACTION/AD boundary arbitration."""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "data" / "processed_transaction_ad_boundary_arbitration_20260806_r1"
PREV_LABELS = [
    ROOT / "data" / "processed_harass_boundary_arbitration_20260806_r1" / "provisional_labels.jsonl",
    ROOT / "data" / "processed_harass_fraud_boundary_arbitration_20260806_r1" / "provisional_labels.jsonl",
    BASE / "provisional_labels.jsonl",
]
RUN = "txn_boundary_r2_arbitration_20260806_r1"
PACK = ROOT / "data" / "interim" / "annotation" / RUN
REPORT_WIN = Path("/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments") / RUN
MODEL = (
    ROOT
    / "artifacts"
    / "experiments"
    / "stage2_xfyun_txn_ad_overlay_lr_5e4_hard_boundary_both_1p5_txn_w1p8_20260806_r1"
    / "sms_bytecnn_fp32.keras"
)
EXPECTED_SHA = {
    "train": "7fefb075b3167800087a47e0c5640df1c38be125315a5b37626b5ff0edabf1e1",
    "validation": "2aecc6f10412d4307ee5abba1791c1b3fabf865faff82b9f0ee1674ee21da116",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_records(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    if PACK.exists() or REPORT_WIN.exists():
        raise SystemExit(f"refusing to overwrite run_id: {RUN}")
    for name in ("train", "validation"):
        actual = sha256(BASE / f"{name}.jsonl")
        if actual != EXPECTED_SHA[name]:
            raise SystemExit(f"base {name} SHA mismatch: {actual}")
    if not MODEL.exists():
        raise SystemExit(f"model missing: {MODEL}")

    sys.path.insert(0, str(ROOT))
    from src.byte_encoder import encode_text
    from src.normalize import normalize_text
    from src.schema import LABEL_ORDER
    from src.train_utils import split_student_logits

    import tensorflow as tf

    prev_ids = set()
    for path in PREV_LABELS:
        if path.exists():
            prev_ids.update(r["id"] for r in load_records(path))
    records = load_records(BASE / "train.jsonl") + load_records(
        BASE / "validation.jsonl"
    )
    zh = [
        r
        for r in records
        if r.get("language") == "zh" and r["label"] in LABEL_ORDER
    ]
    model = tf.keras.models.load_model(MODEL)
    max_bytes = int(model.input_shape[-1])
    x = np.asarray(
        [encode_text(normalize_text(r["text"]), length=max_bytes) for r in zh],
        dtype=np.int32,
    )
    logits = model.predict(x, verbose=0)
    class_logits, _ = split_student_logits(np.asarray(logits), len(LABEL_ORDER))
    preds = [LABEL_ORDER[int(i)] for i in np.argmax(class_logits, axis=-1)]

    selected = [
        (r, pred)
        for r, pred in zip(zh, preds)
        if r["label"] in ("TRANSACTION", "AD") and pred != r["label"]
    ]
    if not selected:
        raise SystemExit("no model-boundary candidates found")

    rows = [
        {
            "review_key": hashlib.sha256((RUN + r["id"]).encode()).hexdigest()[:16],
            "id": r["id"],
            "text": r["text"],
        }
        for r, _ in selected
    ]
    pass_b_rows = random.Random(20260806).sample(rows, len(rows))
    PACK.mkdir(parents=True)
    REPORT_WIN.mkdir(parents=True)
    (PACK / "pass_a_blind.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )
    (PACK / "pass_b_blind.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in pass_b_rows),
        encoding="utf-8",
    )

    by_split = {}
    for r, _ in selected:
        split = r.get("split", "")
        by_split[split] = by_split.get(split, 0) + 1
    true_pred = {}
    for r, pred in selected:
        key = f"{r['label']}->{pred}"
        true_pred[key] = true_pred.get(key, 0) + 1
    manifest = {
        "run_id": RUN,
        "status": "PENDING_EXTERNAL_APPROVAL",
        "claim_allowed": False,
        "human_verified": False,
        "formal_acceptance_allowed": False,
        "locked_test_read": False,
        "base_data_sha256": {name: EXPECTED_SHA[name] for name in ("train", "validation")},
        "base_data_version": str(BASE.relative_to(ROOT)).replace("\\", "/"),
        "candidate_selection": "zh_transaction_ad_model_boundary_all_no_exclusion",
        "previous_arbitration_excluded_ids": len(prev_ids),
        "candidate_count": len(rows),
        "split_counts": by_split,
        "true_pred_pair_counts": dict(
            sorted(true_pred.items(), key=lambda x: (-x[1], x[0]))
        ),
        "model_sha256": sha256(MODEL),
        "blind_fields": ["review_key", "id", "text"],
        "excluded_fields": ["prior_label", "model_prediction", "split", "annotator_ids"],
        "pass_a_sha256": sha256(PACK / "pass_a_blind.jsonl"),
        "pass_b_sha256": sha256(PACK / "pass_b_blind.jsonl"),
        "privacy": {
            "raw_sms_text_committed": False,
            "raw_sample_ids_committed": False,
            "raw_ai_outputs_committed": False,
        },
    }
    (REPORT_WIN / "preparation_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                key: manifest[key]
                for key in (
                    "run_id",
                    "candidate_count",
                    "split_counts",
                    "pass_a_sha256",
                    "pass_b_sha256",
                )
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
