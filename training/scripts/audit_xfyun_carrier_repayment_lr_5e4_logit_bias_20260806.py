#!/usr/bin/env python3
"""Audit single-class logit-bias postprocessing on the lr=5e-4 front."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

import numpy as np
import tensorflow as tf

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.byte_encoder import encode_text  # noqa: E402
from src.metrics import summarize_metrics  # noqa: E402
from src.normalize import normalize_text  # noqa: E402
from src.schema import LABEL_ORDER, load_jsonl  # noqa: E402
from src.train_utils import split_student_logits  # noqa: E402


RUN_ID = "stage2_xfyun_carrier_repayment_lr_5e4_logit_bias_audit_20260806_r1"
DATA = ROOT / "data" / "processed_xfyun_carrier_repayment_relabel_20260804_r1"
TARGETS = {
    "transaction_recall": 0.985,
    "transaction_precision": 0.920,
    "macro_f1": 0.860,
    "harass_f1": 0.800,
    "fraud_recall": 0.800,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics_for(logits: np.ndarray, y_true: Sequence[str]) -> Dict[str, object]:
    indices = np.argmax(logits, axis=-1)
    y_pred = [LABEL_ORDER[int(index)] for index in indices]
    summary = summarize_metrics(y_true, y_pred, LABEL_ORDER)
    per_class = summary["per_class"]
    return {
        "transaction_recall": per_class["TRANSACTION"]["recall"],
        "transaction_precision": per_class["TRANSACTION"]["precision"],
        "macro_f1": summary["macro_f1"],
        "harass_f1": per_class["HARASS"]["f1"],
        "fraud_recall": per_class["FRAUD"]["recall"],
        "summary": summary,
    }


def passes(metric: Dict[str, object]) -> bool:
    return all(float(metric[name]) >= target for name, target in TARGETS.items())


def min_gate_margin(metric: Dict[str, object]) -> float:
    return min(float(metric[name]) - target for name, target in TARGETS.items())


def compact(metric: Dict[str, object], bias_name: str, bias_value: float) -> Dict[str, object]:
    return {
        "bias_name": bias_name,
        "bias_value": bias_value,
        "transaction_recall": metric["transaction_recall"],
        "transaction_precision": metric["transaction_precision"],
        "macro_f1": metric["macro_f1"],
        "harass_f1": metric["harass_f1"],
        "fraud_recall": metric["fraud_recall"],
        "confusion_matrix": metric["summary"]["confusion_matrix"],
        "min_gate_margin": min_gate_margin(metric),
    }


def best_candidates(
    logits: np.ndarray,
    y_true: Sequence[str],
    label: str,
    values: Iterable[float],
) -> Dict[str, object]:
    label_index = LABEL_ORDER.index(label)
    rows: List[Dict[str, object]] = []
    feasible: List[Dict[str, object]] = []
    for value in values:
        biased = np.array(logits, copy=True)
        biased[:, label_index] += float(value)
        metric = metrics_for(biased, y_true)
        row = compact(metric, f"{label.lower()}_logit_bias", float(value))
        rows.append(row)
        if passes(metric):
            feasible.append(row)

    return {
        "label": label,
        "sweep_count": len(rows),
        "feasible_count": len(feasible),
        "first_feasible": feasible[0] if feasible else None,
        "best_min_gate_margin": max(
            rows,
            key=lambda row: (row["min_gate_margin"], row["macro_f1"], row["harass_f1"]),
        ),
        "best_with_transaction_precision_guard": max(
            rows,
            key=lambda row: (
                row["transaction_precision"] >= TARGETS["transaction_precision"],
                row["transaction_recall"],
                row["macro_f1"],
                row["harass_f1"],
            ),
        ),
        "best_with_transaction_recall_guard": max(
            rows,
            key=lambda row: (
                row["transaction_recall"] >= TARGETS["transaction_recall"],
                row["transaction_precision"],
                row["macro_f1"],
                row["harass_f1"],
            ),
        ),
    }


def audit_model(model_path: Path, records, bias_values: List[float]) -> Dict[str, object]:
    model = tf.keras.models.load_model(model_path)
    max_bytes = int(model.input_shape[-1])
    encoded = np.asarray(
        [
            encode_text(normalize_text(record.text), length=max_bytes)
            for record in records
        ],
        dtype=np.int32,
    )
    outputs = model.predict(encoded, verbose=0)
    logits, _ = split_student_logits(np.asarray(outputs), len(LABEL_ORDER))
    y_true = [record.label for record in records]
    baseline = compact(metrics_for(logits, y_true), "none", 0.0)
    return {
        "model_path": str(model_path).replace("\\", "/"),
        "model_sha256": sha256(model_path),
        "baseline": baseline,
        "single_variable_sweeps": [
            best_candidates(logits, y_true, label, bias_values)
            for label in LABEL_ORDER
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-root", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    args = parser.parse_args()

    report = args.report_root / RUN_ID
    if report.exists():
        raise SystemExit(f"refusing to overwrite run_id: {RUN_ID}")
    report.mkdir(parents=True)

    records = [
        record
        for record in load_jsonl(DATA / "validation.jsonl")
        if record.language == "zh" and record.label in LABEL_ORDER
    ]
    bias_values = [round(value, 2) for value in np.arange(-2.0, 2.0001, 0.05)]
    model_result = audit_model(args.model, records, bias_values)
    feasible_sweeps = [
        sweep
        for sweep in model_result["single_variable_sweeps"]
        if sweep["feasible_count"] > 0
    ]
    result = {
        "run_id": RUN_ID,
        "status": "EXPLORATORY_PROVISIONAL_VALIDATION_ONLY",
        "annotation_status": "PROVISIONAL_AUTOMATED_MULTI_PASS",
        "claim_allowed": False,
        "human_verified": False,
        "formal_acceptance_allowed": False,
        "locked_test_read": False,
        "quantization_run": False,
        "android_export_run": False,
        "hypothesis": (
            "A single fixed class-logit bias on the lr=5e-4 front might recover "
            "one acceptance tradeoff, but must pass all five zh validation gates on one candidate."
        ),
        "search_space": {
            "bias_labels": LABEL_ORDER,
            "bias_min": -2.0,
            "bias_max": 2.0,
            "bias_step": 0.05,
            "single_variable_only": True,
        },
        "acceptance_targets": TARGETS,
        "data_sha256": {
            "train": sha256(DATA / "train.jsonl"),
            "validation": sha256(DATA / "validation.jsonl"),
        },
        "evaluated_count": len(records),
        "model": model_result,
        "feasible_sweeps": feasible_sweeps,
        "decision": "rejected" if not feasible_sweeps else "candidate_found",
        "decision_reason": (
            "No audited single-variable logit-bias point on the lr=5e-4 front satisfied all five zh validation gates."
            if not feasible_sweeps
            else "At least one single-variable logit-bias point satisfied all five zh validation gates and requires fixed-candidate evaluation."
        ),
    }
    (report / "audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "run_id": RUN_ID,
                "decision": result["decision"],
                "feasible_count": len(feasible_sweeps),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
