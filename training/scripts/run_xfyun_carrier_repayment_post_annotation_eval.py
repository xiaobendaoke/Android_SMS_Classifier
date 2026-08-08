#!/usr/bin/env python3
"""Re-evaluate a fixed exploratory model against a newer provisional validation overlay."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
RUN = "stage2_xfyun_carrier_repayment_post_annotation_eval_20260805_r1"
MODEL = ROOT / "artifacts/experiments/stage2_xfyun_overlay_txn_weight_1p4_20260803_r1/sms_bytecnn_fp32.keras"
VALIDATION = ROOT / "data/processed_xfyun_carrier_repayment_relabel_20260804_r1/validation.jsonl"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-root", required=True, type=Path)
    args = parser.parse_args()
    report = args.report_root / RUN
    if report.exists():
        raise SystemExit(f"refusing to overwrite run_id: {RUN}")
    if not MODEL.exists() or not VALIDATION.exists():
        raise SystemExit("required model or validation overlay missing")
    report.mkdir(parents=True)
    metrics = report / "metrics.json"
    command = [
        sys.executable, str(ROOT / "scripts/evaluate.py"),
        "--test", str(VALIDATION), "--mode", "keras", "--keras", str(MODEL),
        "--output", str(metrics), "--seed", "42", "--stage", RUN,
        "--error-samples", "0", "--require-acceptance",
        "--targets-config", str(ROOT / "configs/student.yaml"),
    ]
    completed = subprocess.run(command, cwd=REPO, env={**os.environ, "PYTHONPATH": str(ROOT)}, check=False)
    metric_payload = json.loads(metrics.read_text(encoding="utf-8")) if metrics.exists() else {}
    result = {
        "run_id": RUN,
        "status": "EXPLORATORY_PROVISIONAL_VALIDATION_ONLY",
        "claim_allowed": False,
        "human_verified": False,
        "formal_acceptance_allowed": False,
        "locked_test_read": False,
        "quantization_run": False,
        "android_export_run": False,
        "seed": 42,
        "hypothesis": "The fixed ByteCNN's validation metrics change only because seven provisional A/B/C label corrections update the reference labels.",
        "only_changed_variable": "validation manifest=processed_xfyun_carrier_repayment_relabel_20260804_r1",
        "model_sha256": sha256(MODEL),
        "validation_sha256": sha256(VALIDATION),
        "config_sha256": sha256(ROOT / "configs/student.yaml"),
        "command": command,
        "returncode": completed.returncode,
        "gate_errors": metric_payload.get("gate_errors", []),
        "metrics": {
            "transaction_recall": metric_payload.get("transaction_recall"),
            "transaction_precision": metric_payload.get("transaction_precision"),
            "macro_f1": metric_payload.get("macro_f1"),
            "per_class": metric_payload.get("acceptance_scope", {}).get("metrics", {}).get("per_class", {}),
        },
    }
    (report / "experiment.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"run_id": RUN, "returncode": completed.returncode, "metrics_written": metrics.exists()}, ensure_ascii=False))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
