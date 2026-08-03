#!/usr/bin/env python3
"""Emit validation-only, text-free length buckets for transaction errors."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.prepare_transaction_specialist_freeze import coverage_subtype
from src.schema import LABEL_ORDER
from src.train_utils import load_labeled_records, records_to_xy, split_student_logits


def quantiles(values: list[int]) -> list[float]:
    return np.quantile(values, [0.0, 0.25, 0.5, 0.75, 0.9, 1.0]).tolist() if values else []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import tensorflow as tf

    records = [row for row in load_labeled_records(args.validation) if row.language == "zh"]
    model = tf.keras.models.load_model(args.model)
    x, _ = records_to_xy(records, max_bytes=int(model.input_shape[-1]))
    logits, _ = split_student_logits(np.asarray(model.predict(x, verbose=0)))
    predictions = [LABEL_ORDER[int(index)] for index in np.argmax(logits, axis=-1)]
    misses = [(record, prediction) for record, prediction in zip(records, predictions) if record.label == "TRANSACTION" and prediction != "TRANSACTION"]
    false_positives = [(record, prediction) for record, prediction in zip(records, predictions) if record.label != "TRANSACTION" and prediction == "TRANSACTION"]
    def bucket(rows):
        grouped = defaultdict(list)
        for record, prediction in rows:
            grouped[(coverage_subtype(record.text) or "UNMATCHED", prediction)].append(record)
        return [{"coverage_subtype": key[0], "predicted_label": key[1], "count": len(group), "char_length_quantiles": quantiles([len(row.text) for row in group]), "utf8_byte_length_quantiles": quantiles([len(row.text.encode("utf-8")) for row in group]), "at_or_above_model_limit": sum(len(row.text.encode("utf-8")) >= int(model.input_shape[-1]) for row in group)} for key, group in sorted(grouped.items())]
    payload = {"locked_test_read": False, "language": "zh", "model_input_bytes": int(model.input_shape[-1]), "transaction_misses": {"count": len(misses), "by_bucket": bucket(misses)}, "transaction_false_positives": {"count": len(false_positives), "true_label": dict(Counter(row.label for row, _ in false_positives)), "char_length_quantiles": quantiles([len(row.text) for row, _ in false_positives]), "utf8_byte_length_quantiles": quantiles([len(row.text.encode("utf-8")) for row, _ in false_positives])}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
