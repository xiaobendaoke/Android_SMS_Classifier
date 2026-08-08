#!/usr/bin/env python3
"""Run dropout=0.10 with a narrower balanced class-weight clip."""
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
RUN = "stage2_xfyun_carrier_repayment_dropout_0p10_class_clip_0p90_1p30_20260806_r1"
ARTIFACT = ROOT / "artifacts" / "experiments" / RUN
DATA = ROOT / "data" / "processed_xfyun_carrier_repayment_relabel_20260804_r1"
TEACHER = ROOT / "artifacts" / "experiments" / "stage2_xfyun_carrier_repayment_teacher_20260805_r1" / "teacher_logits_manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-root", required=True, type=Path)
    args = parser.parse_args()
    report = args.report_root / RUN
    if ARTIFACT.exists() or report.exists():
        raise SystemExit(f"refusing to overwrite run_id: {RUN}")
    if not TEACHER.exists():
        raise SystemExit("teacher logits manifest missing")

    cfg = copy.deepcopy(yaml.safe_load((ROOT / "configs" / "student.yaml").read_text(encoding="utf-8")))
    cfg["seed"] = 42
    cfg["data"]["train_manifest"] = "data/processed_xfyun_carrier_repayment_relabel_20260804_r1/train.jsonl"
    cfg["data"]["val_manifest"] = "data/processed_xfyun_carrier_repayment_relabel_20260804_r1/validation.jsonl"
    cfg["training"]["class_weight_multipliers"]["TRANSACTION"] = 1.4
    cfg["training"]["class_weight_clip"] = [0.90, 1.30]
    cfg["model"]["dropout"] = 0.10
    cfg["distillation"]["teacher_manifest"] = str(TEACHER.relative_to(ROOT))
    cfg["output"]["checkpoint_dir"] = str(ARTIFACT.relative_to(ROOT))
    cfg["output"]["keras_path"] = str((ARTIFACT / "sms_bytecnn_fp32.keras").relative_to(ROOT))

    ARTIFACT.mkdir(parents=True)
    report.mkdir(parents=True)
    config = ARTIFACT / "config.yaml"
    config.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "distill_student.py"), "--config", str(config), "--seed", "42"],
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
        "baseline": "stage2_xfyun_carrier_repayment_dropout_0p10_20260805_r1",
        "hypothesis": (
            "Narrowing only the balanced class-weight clip raises the low hard-CE weights for majority "
            "TRANSACTION/AD while reducing minority extremes, testing whether recall can improve without "
            "the precision collapse seen in focal/bias experiments."
        ),
        "only_changed_variable": "training.class_weight_clip=[0.90, 1.30] (baseline=[0.75, 1.50])",
        "carried_forward_from_baseline": {
            "model.dropout": 0.10
        },
        "config_sha256": sha256(config),
        "teacher_manifest_sha256": sha256(TEACHER),
        "data_sha256": {name: sha256(DATA / f"{name}.jsonl") for name in ("train", "validation")},
        "returncode": completed.returncode,
    }
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result["training_manifest_val_metrics"] = manifest.get("val_metrics", {})
        result["best_epoch"] = manifest.get("best_epoch")
        result["training_manifest_gate_errors"] = manifest.get("gate_errors", [])
        result["authoritative_final_evaluation"] = "post_training_keras_metrics.json"
    (report / "experiment.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"run_id": RUN, "returncode": completed.returncode, "has_manifest": manifest_path.exists()}, ensure_ascii=False))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
