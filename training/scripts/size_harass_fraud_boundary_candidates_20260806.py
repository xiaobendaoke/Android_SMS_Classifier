#!/usr/bin/env python3
"""Count text-free candidate pools for the next HARASS/FRAUD boundary arbitration."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "processed_xfyun_carrier_repayment_relabel_20260804_r1"
MODEL = (
    ROOT
    / "artifacts"
    / "experiments"
    / "stage2_xfyun_carrier_repayment_lr_5e4_hard_boundary_both_1p5_20260806_r1"
    / "sms_bytecnn_fp32.keras"
)
ALLOWED = {"TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"}


def load_records(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from src.byte_encoder import encode_text
    from src.normalize import normalize_text
    from src.schema import LABEL_ORDER
    from src.train_utils import split_student_logits

    import tensorflow as tf

    if not MODEL.exists():
        raise SystemExit(f"model missing: {MODEL}")
    model = tf.keras.models.load_model(MODEL)
    max_bytes = int(model.input_shape[-1])

    records = load_records(DATA / "train.jsonl") + load_records(
        DATA / "validation.jsonl"
    )
    zh = [
        r
        for r in records
        if r.get("language") == "zh" and r["label"] in LABEL_ORDER
    ]
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

    all_harass_fraud = [r for r in rows if r["label"] in ("HARASS", "FRAUD")]
    boundary_misclassified = [
        r
        for r in all_harass_fraud
        if r["pred"] != r["label"]
        and (r["label"] in ("HARASS", "FRAUD") or r["pred"] in ("HARASS", "FRAUD"))
    ]
    cross_confusion = [
        r
        for r in all_harass_fraud
        if r["label"] in ("HARASS", "FRAUD")
        and r["pred"] in ("HARASS", "FRAUD")
        and r["pred"] != r["label"]
    ]
    harass_misclassified = [
        r for r in all_harass_fraud if r["label"] == "HARASS" and r["pred"] != "HARASS"
    ]
    fraud_misclassified = [
        r for r in all_harass_fraud if r["label"] == "FRAUD" and r["pred"] != "FRAUD"
    ]

    groups = defaultdict(list)
    for r in rows:
        tg = r["template_group"]
        if tg:
            groups[tg].append(r)
    boundary_group_rows = []
    for tg, group_rows in groups.items():
        labels = {r["label"] for r in group_rows}
        if {"HARASS", "FRAUD"}.issubset(labels):
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
        "run_id": "size_harass_fraud_boundary_candidates_20260806_r1",
        "status": "ANALYSIS_ONLY_NO_CANDIDATE",
        "locked_test_read": False,
        "data_sha256": {
            name: __import__("hashlib").sha256(
                (DATA / f"{name}.jsonl").read_bytes()
            ).hexdigest()
            for name in ("train", "validation")
        },
        "model_sha256": __import__("hashlib").sha256(MODEL.read_bytes()).hexdigest(),
        "zh_evaluated_count": len(zh),
        "pools": [
            summarize("all_zh_harass_fraud", all_harass_fraud),
            summarize("boundary_misclassified", boundary_misclassified),
            summarize("harass_fraud_cross_confusion", cross_confusion),
            summarize("harass_misclassified", harass_misclassified),
            summarize("fraud_misclassified", fraud_misclassified),
            summarize("template_boundary_groups_harass_fraud", boundary_group_rows),
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
