#!/usr/bin/env python3
"""Text-free validation error clustering for the user-reviewed AI dual-pass retrain."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.prepare_transaction_specialist_freeze import coverage_subtype  # noqa: E402
from src.metrics import summarize_metrics  # noqa: E402
from src.schema import LABEL_ORDER, SmsRecord  # noqa: E402
from src.train_utils import load_labeled_records, records_to_xy, split_student_logits  # noqa: E402


RUN_ID = "ai_dual_pass_retrain_20260806_r1_error_clusters"
DATA = ROOT / "data" / "processed_ai_dual_pass_20260806_r1"
TARGETS = {
    "transaction_recall": 0.985,
    "transaction_precision": 0.920,
    "macro_f1": 0.860,
    "harass_f1": 0.800,
    "fraud_recall": 0.800,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_hash(namespace: str, value: str) -> str:
    if not value:
        value = "<empty>"
    digest = hashlib.sha256(f"{namespace}:{value}".encode("utf-8")).hexdigest()
    return digest[:16]


def quantiles(values: Sequence[int]) -> List[float]:
    if not values:
        return []
    return [float(value) for value in np.quantile(values, [0.0, 0.25, 0.5, 0.75, 0.9, 1.0])]


def length_bucket(record: SmsRecord) -> str:
    byte_len = len(record.text.encode("utf-8"))
    char_len = len(record.text)
    if byte_len >= 512:
        return "bytes_ge_512"
    if char_len <= 64:
        return "chars_000_064"
    if char_len <= 128:
        return "chars_065_128"
    if char_len <= 256:
        return "chars_129_256"
    return "chars_ge_257"


def top_counts(counter: Counter, limit: int = 10) -> List[Dict[str, object]]:
    return [
        {"key": str(key), "count": int(count)}
        for key, count in counter.most_common(limit)
    ]


def gate_metrics(summary: Dict[str, object]) -> Dict[str, float]:
    per_class = summary["per_class"]
    return {
        "transaction_recall": float(per_class["TRANSACTION"]["recall"]),
        "transaction_precision": float(per_class["TRANSACTION"]["precision"]),
        "macro_f1": float(summary["macro_f1"]),
        "harass_f1": float(per_class["HARASS"]["f1"]),
        "fraud_recall": float(per_class["FRAUD"]["recall"]),
    }


def failed_gates(metrics: Dict[str, float]) -> List[str]:
    return [
        f"{name}={metrics[name]:.6f} < {target:.6f}"
        for name, target in TARGETS.items()
        if metrics[name] < target
    ]


def predict_model(model_path: Path, records: Sequence[SmsRecord]) -> Tuple[List[str], Dict[str, object]]:
    import tensorflow as tf

    model = tf.keras.models.load_model(model_path)
    max_bytes = int(model.input_shape[-1])
    x, _ = records_to_xy(records, max_bytes=max_bytes)
    logits, _ = split_student_logits(np.asarray(model.predict(x, verbose=0)))
    predictions = [LABEL_ORDER[int(index)] for index in np.argmax(logits, axis=-1)]
    return predictions, {"model_input_bytes": max_bytes}


def cluster_rows(rows: Iterable[Tuple[SmsRecord, str]], *, limit: int = 10) -> Dict[str, object]:
    materialized = list(rows)
    char_lengths = [len(record.text) for record, _ in materialized]
    byte_lengths = [len(record.text.encode("utf-8")) for record, _ in materialized]
    return {
        "count": len(materialized),
        "predicted_label": top_counts(Counter(pred for _, pred in materialized), limit),
        "length_bucket": top_counts(Counter(length_bucket(record) for record, _ in materialized), limit),
        "coverage_subtype": top_counts(
            Counter(coverage_subtype(record.text) or "UNMATCHED" for record, _ in materialized),
            limit,
        ),
        "source": top_counts(Counter(record.source for record, _ in materialized), limit),
        "sender_group_hash": top_counts(
            Counter(safe_hash("sender_group", record.sender_group) for record, _ in materialized),
            limit,
        ),
        "template_group_hash": top_counts(
            Counter(safe_hash("template_group", record.template_group) for record, _ in materialized),
            limit,
        ),
        "is_synthetic": dict(Counter(str(record.is_synthetic).lower() for record, _ in materialized)),
        "is_adversarial": dict(Counter(str(record.is_adversarial).lower() for record, _ in materialized)),
        "char_length_quantiles": quantiles(char_lengths),
        "utf8_byte_length_quantiles": quantiles(byte_lengths),
    }


def analyze_one(name: str, model_path: Path, records: Sequence[SmsRecord]) -> Dict[str, object]:
    predictions, meta = predict_model(model_path, records)
    truth = [record.label for record in records]
    summary = summarize_metrics(truth, predictions, LABEL_ORDER)
    gates = gate_metrics(summary)
    pairs = Counter(
        f"{record.label}->{prediction}"
        for record, prediction in zip(records, predictions)
        if record.label != prediction
    )
    miss_clusters = {}
    for true_label in LABEL_ORDER:
        for predicted_label in LABEL_ORDER:
            if true_label == predicted_label:
                continue
            rows = [
                (record, prediction)
                for record, prediction in zip(records, predictions)
                if record.label == true_label and prediction == predicted_label
            ]
            if rows:
                miss_clusters[f"{true_label}->{predicted_label}"] = cluster_rows(rows)
    return {
        "name": name,
        "model_path": str(model_path).replace("\\", "/"),
        "model_sha256": sha256(model_path),
        **meta,
        "metrics": gates,
        "failed_gates": failed_gates(gates),
        "confusion_matrix": summary["confusion_matrix"],
        "error_pair_counts": top_counts(pairs, 16),
        "error_clusters": miss_clusters,
    }


def parse_model_arg(value: str) -> Tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--model must be NAME=PATH")
    name, path = value.split("=", 1)
    if not name.strip():
        raise argparse.ArgumentTypeError("model NAME cannot be empty")
    return name.strip(), Path(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-root", required=True, type=Path)
    parser.add_argument("--model", required=True, type=parse_model_arg)
    args = parser.parse_args()

    report = args.report_root / RUN_ID
    if report.exists():
        raise SystemExit(f"refusing to overwrite run_id: {RUN_ID}")
    _, model_path = args.model
    if not model_path.exists():
        raise SystemExit(f"model missing: {model_path}")

    records = [
        record
        for record in load_labeled_records(DATA / "validation.jsonl")
        if record.language == "zh" and record.label in LABEL_ORDER
    ]
    name, _ = args.model
    payload = analyze_one(name, model_path, records)

    result = {
        "run_id": RUN_ID,
        "status": "TEXT_FREE_VALIDATION_ERROR_ANALYSIS",
        "annotation_status": "USER_REVIEWED_AI_DUAL_PASS",
        "claim_allowed": False,
        "human_verified": True,
        "formal_acceptance_allowed": False,
        "locked_test_read": False,
        "quantization_run": False,
        "android_export_run": False,
        "language": "zh",
        "analysis_privacy": {
            "raw_sms_text_written": False,
            "raw_sample_ids_written": False,
            "raw_ai_outputs_written": False,
            "group_hashes_are_truncated_sha256": True,
        },
        "data_sha256": {
            "train": sha256(DATA / "train.jsonl"),
            "validation": sha256(DATA / "validation.jsonl"),
        },
        "evaluated_count": len(records),
        "acceptance_targets": TARGETS,
        "model": payload,
        "decision": "analysis_only_no_candidate",
        "decision_reason": (
            "Clusters validation errors without raw text or IDs to prioritize expanded "
            "AI dual-pass arbitration coverage. Does not read locked test or change labels."
        ),
    }
    report.mkdir(parents=True)
    (report / "analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "run_id": RUN_ID,
                "model": payload["name"],
                "evaluated_count": result["evaluated_count"],
                "error_count": int(sum(1 for pair in payload["error_pair_counts"] for _ in range(0))),
                "failed_gates": payload["failed_gates"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
