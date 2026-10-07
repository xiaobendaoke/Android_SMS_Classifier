#!/usr/bin/env python3
"""Count remaining TRANSACTION/AD model-boundary rows after three arbitration rounds."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "data" / "processed_transaction_ad_boundary_arbitration_20260806_r1"
PREV_LABELS = [
    ROOT / "data" / "processed_harass_boundary_arbitration_20260806_r1" / "provisional_labels.jsonl",
    ROOT / "data" / "processed_harass_fraud_boundary_arbitration_20260806_r1" / "provisional_labels.jsonl",
    BASE / "provisional_labels.jsonl",
]
MODEL = (
    ROOT
    / "artifacts"
    / "experiments"
    / "stage2_xfyun_txn_ad_overlay_lr_5e4_hard_boundary_both_1p5_txn_w1p8_20260806_r1"
    / "sms_bytecnn_fp32.keras"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_records(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
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

    rows = []
    for r, pred in zip(zh, preds):
        rows.append(
            {
                "id": r["id"],
                "label": r["label"],
                "split": r.get("split", ""),
                "pred": pred,
                "template_group": r.get("template_group", ""),
            }
        )

    all_txn_ad = [r for r in rows if r["label"] in ("TRANSACTION", "AD")]
    boundary_misclassified = [
        r
        for r in all_txn_ad
        if r["pred"] != r["label"] and r["id"] not in prev_ids
    ]
    boundary_misclassified_all = [
        r for r in all_txn_ad if r["pred"] != r["label"]
    ]
    cross_confusion = [
        r
        for r in boundary_misclassified
        if r["label"] in ("TRANSACTION", "AD")
        and r["pred"] in ("TRANSACTION", "AD")
    ]
    txn_misclassified = [
        r for r in boundary_misclassified if r["label"] == "TRANSACTION"
    ]
    txn_misclassified_all = [
        r for r in boundary_misclassified_all if r["label"] == "TRANSACTION"
    ]
    ad_misclassified = [r for r in boundary_misclassified if r["label"] == "AD"]

    groups = defaultdict(list)
    for r in rows:
        tg = r["template_group"]
        if tg:
            groups[tg].append(r)
    boundary_group_rows = []
    for tg, group_rows in groups.items():
        labels = {r["label"] for r in group_rows}
        if {"TRANSACTION", "AD"}.issubset(labels):
            boundary_group_rows.extend(group_rows)


    def summarize(name: str, pool: list[dict]) -> dict:
        by_split = Counter(r["split"] for r in pool)
        by_label = Counter(r["label"] for r in pool)
        by_true_pred = Counter(f"{r['label']}->{r['pred']}" for r in pool)
        return {
            "pool": name,
            "count": len(pool),
            "train_count": by_split.get("train", 0),
            "validation_count": by_split.get("validation", 0),
            "true_label_counts": dict(sorted(by_label.items())),
            "true_pred_pair_counts": dict(
                sorted(by_true_pred.items(), key=lambda x: (-x[1], x[0]))
            ),
        }

    report = {
        "run_id": "size_txn_remaining_boundary_candidates_20260806_r1",
        "status": "ANALYSIS_ONLY_NO_CANDIDATE",
        "locked_test_read": False,
        "base_data_sha256": {
            name: sha256(BASE / f"{name}.jsonl") for name in ("train", "validation")
        },
        "model_sha256": sha256(MODEL),
        "previous_arbitration_excluded_ids": len(prev_ids),
        "zh_evaluated_count": len(zh),
        "pools": [
            summarize("all_zh_transaction_ad", all_txn_ad),
            summarize("boundary_misclassified", boundary_misclassified),
            summarize("boundary_misclassified_all_no_exclusion", boundary_misclassified_all),
            summarize("transaction_ad_cross_confusion", cross_confusion),
            summarize("transaction_misclassified", txn_misclassified),
            summarize("transaction_misclassified_all_no_exclusion", txn_misclassified_all),
            summarize("ad_misclassified", ad_misclassified),
            summarize("template_boundary_groups_transaction_ad", boundary_group_rows),
        ],
        "privacy": {
            "raw_sms_text_written": False,
            "raw_sample_ids_written": False,
            "raw_ai_outputs_written": False,
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
