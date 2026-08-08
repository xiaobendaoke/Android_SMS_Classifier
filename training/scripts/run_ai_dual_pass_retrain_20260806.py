#!/usr/bin/env python3
"""Retrain the round-6 best config on the user-reviewed AI dual-pass data version."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
RUN = "ai_dual_pass_retrain_20260806_r1"
DATA = ROOT / "data" / "processed_ai_dual_pass_20260806_r1"
ARTIFACT = ROOT / "artifacts" / "experiments" / RUN
TARGETS = {
    "transaction_recall": 0.985,
    "transaction_precision": 0.920,
    "macro_f1": 0.860,
    "harass_f1": 0.800,
    "fraud_recall": 0.800,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-root", required=True, type=Path)
    args = parser.parse_args()
    report = args.report_root / RUN
    if ARTIFACT.exists() or report.exists():
        raise SystemExit(f"refusing to overwrite run_id: {RUN}")
    for name in ("train", "validation"):
        if not (DATA / f"{name}.jsonl").exists():
            raise SystemExit(f"missing {name} manifest in {DATA}")

    cfg = copy.deepcopy(
        yaml.safe_load((ROOT / "configs" / "student.yaml").read_text(encoding="utf-8"))
    )
    cfg["seed"] = 42
    cfg["data"]["train_manifest"] = "data/processed_ai_dual_pass_20260806_r1/train.jsonl"
    cfg["data"]["val_manifest"] = "data/processed_ai_dual_pass_20260806_r1/validation.jsonl"
    cfg["data"]["accepted_languages"] = ["zh"]
    cfg["training"]["learning_rate"] = 5e-4
    cfg["training"]["class_weight_multipliers"]["TRANSACTION"] = 1.8
    cfg["training"]["hard_boundary_multiplier"] = 1.5
    cfg["training"]["hard_boundary_labels"] = ["TRANSACTION", "AD", "FRAUD"]
    cfg["output"]["checkpoint_dir"] = str(ARTIFACT.relative_to(ROOT))
    cfg["output"]["keras_path"] = str((ARTIFACT / "sms_bytecnn_fp32.keras").relative_to(ROOT))

    ARTIFACT.mkdir(parents=True)
    report.mkdir(parents=True)
    config = ARTIFACT / "config.yaml"
    config.write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    train_proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "distill_student.py"),
            "--config",
            str(config),
            "--seed",
            "42",
            "--hard-only",
        ],
        cwd=REPO,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        check=False,
    )
    if train_proc.returncode != 0:
        print(json.dumps({"run_id": RUN, "stage": "train", "returncode": train_proc.returncode}))
        return train_proc.returncode

    metrics = report / "post_training_keras_metrics.json"
    eval_proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "evaluate.py"),
            "--test",
            str(DATA / "validation.jsonl"),
            "--mode",
            "keras",
            "--keras",
            str(ARTIFACT / "sms_bytecnn_fp32.keras"),
            "--output",
            str(metrics),
            "--seed",
            "42",
            "--stage",
            RUN,
            "--error-samples",
            "0",
            "--require-acceptance",
            "--targets-config",
            str(ROOT / "configs" / "student.yaml"),
        ],
        cwd=REPO,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        check=False,
    )
    if eval_proc.returncode != 0 or not metrics.exists():
        print(json.dumps({"run_id": RUN, "stage": "eval", "returncode": eval_proc.returncode}))
        return eval_proc.returncode

    m = json.loads(metrics.read_text(encoding="utf-8"))
    gates = {
        "transaction_recall": float(m.get("metrics", {}).get("transaction_recall", 0.0)),
        "transaction_precision": float(m.get("metrics", {}).get("transaction_precision", 0.0)),
        "macro_f1": float(m.get("metrics", {}).get("macro_f1", 0.0)),
        "harass_f1": float(m.get("metrics", {}).get("harass_f1", 0.0)),
        "fraud_recall": float(m.get("metrics", {}).get("fraud_recall", 0.0)),
    }
    failed = [name for name, value in gates.items() if value < TARGETS[name] - 1e-9]
    passed = [name for name in gates if name not in failed]
    decision = {
        "run_id": RUN,
        "status": "ACCEPTED_AUTOMATED_GATES" if not failed else "REJECTED_VALIDATION_GATES",
        "annotation_status": "USER_REVIEWED_AI_DUAL_PASS",
        "claim_allowed": not failed,
        "human_verified": True,
        "formal_acceptance_allowed": not failed,
        "locked_test_read": False,
        "independent_evaluation": "post_training_keras_metrics.json",
        "metrics": gates,
        "acceptance_targets": TARGETS,
        "failed_gates": failed,
        "passed_gates": passed,
        "config_sha256": sha256(config),
        "data_sha256": {name: sha256(DATA / f"{name}.jsonl") for name in ("train", "validation")},
        "model_sha256": sha256(ARTIFACT / "sms_bytecnn_fp32.keras"),
    }
    (report / "decision.json").write_text(
        json.dumps(decision, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({k: decision[k] for k in ("status", "metrics", "failed_gates")}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
