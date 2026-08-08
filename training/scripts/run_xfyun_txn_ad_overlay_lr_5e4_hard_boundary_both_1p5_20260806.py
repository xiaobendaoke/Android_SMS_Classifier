#!/usr/bin/env python3
"""Run round4 config on the stacked TRANSACTION/AD boundary arbitration overlay."""
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
RUN = "stage2_xfyun_txn_ad_overlay_lr_5e4_hard_boundary_both_1p5_20260806_r1"
ARTIFACT = ROOT / "artifacts" / "experiments" / RUN
DATA = ROOT / "data" / "processed_transaction_ad_boundary_arbitration_20260806_r1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-root", required=True, type=Path)
    args = parser.parse_args()
    report = args.report_root / RUN
    if ARTIFACT.exists() or report.exists():
        raise SystemExit(f"refusing to overwrite run_id: {RUN}")

    cfg = copy.deepcopy(
        yaml.safe_load((ROOT / "configs" / "student.yaml").read_text(encoding="utf-8"))
    )
    cfg["seed"] = 42
    cfg["data"]["train_manifest"] = (
        "data/processed_transaction_ad_boundary_arbitration_20260806_r1/train.jsonl"
    )
    cfg["data"]["val_manifest"] = (
        "data/processed_transaction_ad_boundary_arbitration_20260806_r1/validation.jsonl"
    )
    cfg["training"]["learning_rate"] = 5e-4
    cfg["training"]["class_weight_multipliers"]["TRANSACTION"] = 1.4
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
    completed = subprocess.run(
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
    manifest_path = ARTIFACT / "distill_manifest.json"
    result = {
        "run_id": RUN,
        "status": "EXPLORATORY_PROVISIONAL_VALIDATION_ONLY",
        "annotation_status": "PROVISIONAL_AUTOMATED_MULTI_PASS",
        "claim_allowed": False,
        "human_verified": False,
        "formal_acceptance_allowed": False,
        "locked_test_read": False,
        "quantization_run": False,
        "android_export_run": False,
        "seed": 42,
        "baseline": "stage2_xfyun_harass_fraud_overlay_lr_5e4_hard_boundary_both_1p5_20260806_r1",
        "hypothesis": (
            "Round 3 of the data-arbitration direction: stack 152 model-boundary "
            "misclassified zh TRANSACTION/AD rows (arbitrated A/B/C) on top of the "
            "HARASS/FRAUD stacked overlay while keeping all round4 training settings "
            "unchanged. This targets the binding TRANSACTION recall/precision gap "
            "and the CARRIER/UNMATCHED TRANSACTION/AD entanglement."
        ),
        "only_changed_variable": (
            "data manifest=processed_transaction_ad_boundary_arbitration_20260806_r1 "
            "(stacked TRANSACTION/AD boundary arbitration overlay; all training settings unchanged)"
        ),
        "carried_forward_from_baseline": {
            "training.learning_rate": 5e-4,
            "training.class_weight_multipliers.TRANSACTION": 1.4,
            "training_mode": "hard_only",
            "training.hard_boundary_multiplier": 1.5,
            "training.hard_boundary_labels": ["TRANSACTION", "AD", "FRAUD"],
        },
        "config_sha256": sha256(config),
        "data_sha256": {
            name: sha256(DATA / f"{name}.jsonl") for name in ("train", "validation")
        },
        "returncode": completed.returncode,
    }
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result["training_manifest_val_metrics"] = manifest.get("val_metrics", {})
        result["best_epoch"] = manifest.get("best_epoch")
        model_path = ARTIFACT / "sms_bytecnn_fp32.keras"
        result["model_sha256"] = (
            sha256(model_path) if model_path.exists() else manifest.get("keras_sha256")
        )
        result["hard_boundary_count"] = manifest.get("hard_boundary_count")
        result["hard_boundary_label_counts"] = manifest.get(
            "hard_boundary_label_counts"
        )
        result["hard_boundary_labels"] = manifest.get("hard_boundary_labels")
        result["training_manifest_gate_errors"] = manifest.get("gate_errors", [])
        result["authoritative_final_evaluation"] = "post_training_keras_metrics.json"
    (report / "experiment.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "run_id": RUN,
                "returncode": completed.returncode,
                "has_manifest": manifest_path.exists(),
            },
            ensure_ascii=False,
        )
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
