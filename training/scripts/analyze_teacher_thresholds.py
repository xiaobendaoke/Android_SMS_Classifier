#!/usr/bin/env python3
"""Validation-only threshold analysis for the BERT transaction boundary."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.metrics import summarize_metrics  # noqa: E402
from src.normalize import normalize_text  # noqa: E402
from src.schema import LABEL_ORDER  # noqa: E402
from src.train_utils import (  # noqa: E402
    filter_records_by_languages,
    load_labeled_records,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        type=Path,
        default=ROOT / "artifacts" / "teacher",
    )
    parser.add_argument(
        "--validation",
        type=Path,
        default=ROOT / "data" / "processed" / "validation.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "metrics" / "teacher_threshold_analysis.json",
    )
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    records = filter_records_by_languages(
        load_labeled_records(args.validation),
        ["zh"],
    )
    tokenizer = AutoTokenizer.from_pretrained(
        args.model,
        local_files_only=True,
        fix_mistral_regex=True,
    )
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model,
        local_files_only=True,
    )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device).eval()
    logits = []
    with torch.no_grad():
        for start in range(0, len(records), args.batch_size):
            batch = records[start : start + args.batch_size]
            encoded = tokenizer(
                [normalize_text(record.text) for record in batch],
                padding=True,
                truncation=True,
                max_length=128,
                return_tensors="pt",
            )
            outputs = model(
                **{key: value.to(device) for key, value in encoded.items()}
            ).logits
            logits.append(outputs.cpu().numpy())
    all_logits = np.concatenate(logits, axis=0)
    shifted = all_logits - np.max(all_logits, axis=1, keepdims=True)
    probabilities = np.exp(shifted)
    probabilities /= probabilities.sum(axis=1, keepdims=True)
    true_labels = [record.label for record in records]
    transaction_index = LABEL_ORDER.index("TRANSACTION")

    curve = []
    for threshold in np.arange(0.01, 1.0, 0.01):
        predictions = []
        for row in probabilities:
            if row[transaction_index] >= threshold:
                prediction = transaction_index
            else:
                masked = row.copy()
                masked[transaction_index] = -1.0
                prediction = int(np.argmax(masked))
            predictions.append(LABEL_ORDER[prediction])
        metrics = summarize_metrics(true_labels, predictions, LABEL_ORDER)
        curve.append(
            {
                "threshold": round(float(threshold), 2),
                "transaction_recall": float(
                    metrics["per_class"]["TRANSACTION"]["recall"]
                ),
                "transaction_precision": float(
                    metrics["per_class"]["TRANSACTION"]["precision"]
                ),
                "macro_f1": float(metrics["macro_f1"]),
                "harass_f1": float(metrics["per_class"]["HARASS"]["f1"]),
                "fraud_recall": float(
                    metrics["per_class"]["FRAUD"]["recall"]
                ),
            }
        )
    feasible = [
        row
        for row in curve
        if row["transaction_precision"] >= 0.92
        and row["macro_f1"] >= 0.86
        and row["harass_f1"] >= 0.80
        and row["fraud_recall"] >= 0.80
    ]
    payload = {
        "split": "validation",
        "languages": ["zh"],
        "locked_test_read": False,
        "count": len(records),
        "best_recall_with_other_gates": max(
            feasible,
            key=lambda row: row["transaction_recall"],
            default=None,
        ),
        "best_recall_with_precision_at_least_0_92": max(
            (
                row
                for row in curve
                if row["transaction_precision"] >= 0.92
            ),
            key=lambda row: row["transaction_recall"],
            default=None,
        ),
        "best_recall_with_precision_and_macro_gates": max(
            (
                row
                for row in curve
                if row["transaction_precision"] >= 0.92
                and row["macro_f1"] >= 0.86
            ),
            key=lambda row: row["transaction_recall"],
            default=None,
        ),
        "best_precision_with_recall_at_least_0_985": max(
            (
                row
                for row in curve
                if row["transaction_recall"] >= 0.985
            ),
            key=lambda row: row["transaction_precision"],
            default=None,
        ),
        "curve": curve,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {key: value for key, value in payload.items() if key.startswith("best_")},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
