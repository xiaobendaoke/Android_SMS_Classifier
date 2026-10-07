#!/usr/bin/env python3
"""Analyze validation-only transaction errors without exposing SMS text."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.prepare_transaction_specialist_freeze import coverage_subtype  # noqa: E402
from src.metrics import summarize_metrics  # noqa: E402
from src.schema import LABEL_ORDER  # noqa: E402
from src.train_utils import load_labeled_records, records_to_xy, split_student_logits  # noqa: E402
from src.transaction_protection import (  # noqa: E402
    apply_transaction_protection_batch,
    load_protection_rules,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        type=Path,
        default=ROOT / "artifacts" / "student" / "sms_bytecnn_fp32.keras",
    )
    parser.add_argument(
        "--validation",
        type=Path,
        default=ROOT / "data" / "processed" / "validation.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "metrics" / "transaction_error_analysis.json",
    )
    return parser


def _metrics(records, predictions):
    return summarize_metrics(
        [record.label for record in records],
        predictions,
        LABEL_ORDER,
    )


def _compact(metrics):
    return {
        "macro_f1": float(metrics["macro_f1"]),
        "transaction_recall": float(
            metrics["per_class"]["TRANSACTION"]["recall"]
        ),
        "transaction_precision": float(
            metrics["per_class"]["TRANSACTION"]["precision"]
        ),
        "harass_f1": float(metrics["per_class"]["HARASS"]["f1"]),
        "fraud_recall": float(metrics["per_class"]["FRAUD"]["recall"]),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    import tensorflow as tf

    records = load_labeled_records(args.validation)
    model = tf.keras.models.load_model(args.model)
    x, _ = records_to_xy(records, max_bytes=int(model.input_shape[-1]))
    outputs = np.asarray(model.predict(x, verbose=0))
    class_logits, protection_logits = split_student_logits(outputs)
    class_probs = np.exp(class_logits - np.max(class_logits, axis=-1, keepdims=True))
    class_probs /= np.sum(class_probs, axis=-1, keepdims=True)
    primary_indices = np.argmax(class_logits, axis=-1)
    primary = [LABEL_ORDER[int(index)] for index in primary_indices]
    protection_probs = (
        1.0 / (1.0 + np.exp(-protection_logits))
        if protection_logits is not None
        else np.zeros(len(records), dtype=np.float32)
    )
    rules = load_protection_rules(ROOT / "rules" / "rules")

    threshold_curve = []
    for threshold in np.arange(0.05, 1.0, 0.05):
        decisions = apply_transaction_protection_batch(
            [record.text for record in records],
            primary,
            rules,
            model_transaction_protect=[
                bool(score >= threshold) for score in protection_probs
            ],
        )
        predictions = [decision.predicted_label for decision in decisions]
        zh_threshold_indices = [
            index
            for index, record in enumerate(records)
            if record.language == "zh"
        ]
        zh_threshold_records = [
            records[index] for index in zh_threshold_indices
        ]
        zh_threshold_predictions = [
            predictions[index] for index in zh_threshold_indices
        ]
        zh_threshold_metrics = _compact(
            _metrics(zh_threshold_records, zh_threshold_predictions)
        )
        threshold_curve.append(
            {
                "threshold": round(float(threshold), 2),
                **_compact(_metrics(records, predictions)),
                "zh_transaction_recall": zh_threshold_metrics[
                    "transaction_recall"
                ],
                "zh_transaction_precision": zh_threshold_metrics[
                    "transaction_precision"
                ],
                "zh_macro_f1": zh_threshold_metrics["macro_f1"],
                "zh_harass_f1": zh_threshold_metrics["harass_f1"],
                "protected_count": sum(
                    decision.protected for decision in decisions
                ),
            }
        )

    default_decisions = apply_transaction_protection_batch(
        [record.text for record in records],
        primary,
        rules,
        model_transaction_protect=[
            bool(score >= 0.5) for score in protection_probs
        ],
    )
    default_predictions = [
        decision.predicted_label for decision in default_decisions
    ]
    transaction_index = LABEL_ORDER.index("TRANSACTION")
    transaction_misses = [
        (record, prediction)
        for record, prediction in zip(records, default_predictions)
        if record.label == "TRANSACTION" and prediction != "TRANSACTION"
    ]
    transaction_false_positives = [
        (record, prediction)
        for record, prediction in zip(records, default_predictions)
        if record.label != "TRANSACTION" and prediction == "TRANSACTION"
    ]

    changed_by_rules = Counter()
    rule_true_rescues = Counter()
    rule_false_rescues = Counter()
    for record, raw, decision in zip(records, primary, default_decisions):
        if decision.predicted_label == raw:
            continue
        for rule_id in decision.matched_rule_ids:
            changed_by_rules[rule_id] += 1
            if record.label == "TRANSACTION":
                rule_true_rescues[rule_id] += 1
            else:
                rule_false_rescues[rule_id] += 1

    zh_indices = [
        index for index, record in enumerate(records) if record.language == "zh"
    ]
    zh_records = [records[index] for index in zh_indices]
    zh_predictions = [default_predictions[index] for index in zh_indices]
    payload = {
        "split": str(args.validation).replace("\\", "/"),
        "locked_test_read": False,
        "count": len(records),
        "default_pipeline": _compact(_metrics(records, default_predictions)),
        "zh_pipeline": _compact(_metrics(zh_records, zh_predictions)),
        "threshold_curve": threshold_curve,
        "best_recall_with_precision_at_least_0_92": max(
            (
                row
                for row in threshold_curve
                if row["transaction_precision"] >= 0.92
            ),
            key=lambda row: row["transaction_recall"],
            default=None,
        ),
        "transaction_misses": {
            "count": len(transaction_misses),
            "predicted_as": dict(
                Counter(prediction for _, prediction in transaction_misses)
            ),
            "language": dict(
                Counter(record.language for record, _ in transaction_misses)
            ),
            "source": dict(
                Counter(record.source for record, _ in transaction_misses)
            ),
            "coverage_subtype": dict(
                Counter(
                    coverage_subtype(record.text) or "UNMATCHED"
                    for record, _ in transaction_misses
                )
            ),
        },
        "transaction_false_positives": {
            "count": len(transaction_false_positives),
            "true_label": dict(
                Counter(record.label for record, _ in transaction_false_positives)
            ),
            "source": dict(
                Counter(record.source for record, _ in transaction_false_positives)
            ),
        },
        "rule_effects": {
            "changed_count": dict(changed_by_rules),
            "true_transaction_rescues": dict(rule_true_rescues),
            "false_transaction_rescues": dict(rule_false_rescues),
        },
        "score_distribution": {
            "transaction_aux_quantiles": np.quantile(
                protection_probs[
                    np.asarray(
                        [record.label == "TRANSACTION" for record in records]
                    )
                ],
                [0.01, 0.05, 0.10, 0.25, 0.50],
            ).tolist(),
            "non_transaction_aux_quantiles": np.quantile(
                protection_probs[
                    np.asarray(
                        [record.label != "TRANSACTION" for record in records]
                    )
                ],
                [0.50, 0.75, 0.90, 0.95, 0.99],
            ).tolist(),
            "transaction_class_probability_quantiles": np.quantile(
                class_probs[
                    np.asarray(
                        [record.label == "TRANSACTION" for record in records]
                    ),
                    transaction_index,
                ],
                [0.01, 0.05, 0.10, 0.25, 0.50],
            ).tolist(),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
