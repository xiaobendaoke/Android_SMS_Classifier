#!/usr/bin/env python3
"""Audit a four-class teacher/student probability ensemble on validation only."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.byte_encoder import encode_text  # noqa: E402
from src.metrics import summarize_metrics  # noqa: E402
from src.normalize import normalize_text  # noqa: E402
from src.schema import LABEL_ORDER  # noqa: E402
from src.train_utils import (  # noqa: E402
    filter_records_by_languages,
    load_labeled_records,
    split_student_logits,
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_directory(path: Path) -> str:
    digest = hashlib.sha256()
    for child in sorted(path.rglob("*")):
        if child.is_file():
            digest.update(child.relative_to(path).as_posix().encode("utf-8"))
            digest.update(child.read_bytes())
    return digest.hexdigest()


def softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits, axis=1, keepdims=True)
    values = np.exp(shifted)
    return values / np.sum(values, axis=1, keepdims=True)


def compact(metrics: dict[str, object]) -> dict[str, float]:
    per_class = metrics["per_class"]
    assert isinstance(per_class, dict)
    return {
        "transaction_recall": float(per_class["TRANSACTION"]["recall"]),
        "transaction_precision": float(per_class["TRANSACTION"]["precision"]),
        "macro_f1": float(metrics["macro_f1"]),
        "harass_f1": float(per_class["HARASS"]["f1"]),
        "fraud_recall": float(per_class["FRAUD"]["recall"]),
    }


def gate_errors(metrics: dict[str, float]) -> list[str]:
    targets = {
        "transaction_recall": 0.985,
        "transaction_precision": 0.92,
        "macro_f1": 0.86,
        "harass_f1": 0.80,
        "fraud_recall": 0.80,
    }
    return [
        f"{name}={metrics[name]:.6f} < {target:.6f}"
        for name, target in targets.items()
        if metrics[name] < target
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--student", type=Path, required=True)
    parser.add_argument("--teacher", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    import tensorflow as tf
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    records = filter_records_by_languages(load_labeled_records(args.validation), ["zh"])
    if not records:
        raise SystemExit("No Chinese validation records.")

    student = tf.keras.models.load_model(args.student)
    max_bytes = int(student.input_shape[-1])
    encoded = np.asarray(
        [encode_text(normalize_text(record.text), length=max_bytes) for record in records],
        dtype=np.int32,
    )
    student_logits, _ = split_student_logits(
        np.asarray(student.predict(encoded, verbose=0)), len(LABEL_ORDER)
    )

    tokenizer = AutoTokenizer.from_pretrained(
        args.teacher, local_files_only=True, fix_mistral_regex=True
    )
    teacher = AutoModelForSequenceClassification.from_pretrained(
        args.teacher, local_files_only=True
    )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    teacher.to(device).eval()
    teacher_chunks = []
    with torch.no_grad():
        for start in range(0, len(records), args.batch_size):
            batch = records[start : start + args.batch_size]
            inputs = tokenizer(
                [normalize_text(record.text) for record in batch],
                padding=True,
                truncation=True,
                max_length=128,
                return_tensors="pt",
            )
            teacher_chunks.append(
                teacher(**{name: value.to(device) for name, value in inputs.items()})
                .logits.cpu()
                .numpy()
            )
    teacher_logits = np.concatenate(teacher_chunks, axis=0)
    if teacher_logits.shape != student_logits.shape:
        raise SystemExit(
            f"Class-logit shape mismatch: student={student_logits.shape}, teacher={teacher_logits.shape}"
        )

    labels = [record.label for record in records]
    student_probabilities = softmax(student_logits)
    teacher_probabilities = softmax(teacher_logits)
    rows = []
    for teacher_weight in np.arange(0.0, 1.01, 0.05):
        probabilities = (
            (1.0 - teacher_weight) * student_probabilities
            + teacher_weight * teacher_probabilities
        )
        predictions = [LABEL_ORDER[index] for index in np.argmax(probabilities, axis=1)]
        metrics = compact(summarize_metrics(labels, predictions, LABEL_ORDER))
        failures = gate_errors(metrics)
        rows.append(
            {
                "teacher_weight": round(float(teacher_weight), 2),
                **metrics,
                "acceptance_passed": not failures,
                "gate_errors": failures,
            }
        )

    def min_ratio(row: dict[str, object]) -> float:
        targets = {
            "transaction_recall": 0.985,
            "transaction_precision": 0.92,
            "macro_f1": 0.86,
            "harass_f1": 0.80,
            "fraud_recall": 0.80,
        }
        return min(float(row[name]) / target for name, target in targets.items())

    payload = {
        "status": "EXPLORATORY_PROVISIONAL_VALIDATION_ONLY",
        "annotation_status": "PROVISIONAL_AUTOMATED_MULTI_PASS",
        "claim_allowed": False,
        "human_verified": False,
        "formal_acceptance_allowed": False,
        "locked_test_read": False,
        "language": "zh",
        "validation_count": len(records),
        "student_sha256": sha256_file(args.student),
        "teacher_sha256": sha256_directory(args.teacher),
        "student_input_bytes": max_bytes,
        "fusion": "linear four-class softmax probability average; no per-class threshold or rule override",
        "grid": rows,
        "acceptance_candidates": [row for row in rows if row["acceptance_passed"]],
        "best_minimum_gate_ratio": max(rows, key=min_ratio),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "acceptance_candidate_count": len(payload["acceptance_candidates"]),
                "best_minimum_gate_ratio": payload["best_minimum_gate_ratio"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
