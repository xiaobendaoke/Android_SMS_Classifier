#!/usr/bin/env python3
"""One-variable focal-loss ablation on the provisional xfyun overlay."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

TRAINING = Path(__file__).resolve().parent.parent
REPO = TRAINING.parent
RUN_ID = "stage2_xfyun_overlay_focal_gamma_0_20260804_r1"
TRAIN = "data/processed_xfyun_ai_annotation_20260802_r1/train.jsonl"
VALIDATION = "data/processed_xfyun_error_relabel_20260803_r1/validation.jsonl"
ARTIFACT = TRAINING / "artifacts/experiments" / RUN_ID
REPORT = TRAINING / "reports/experiments" / RUN_ID


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if ARTIFACT.exists() or REPORT.exists():
        raise SystemExit(f"refusing to overwrite run_id: {RUN_ID}")
    cfg = copy.deepcopy(yaml.safe_load((TRAINING / "configs/student.yaml").read_text(encoding="utf-8")))
    cfg["seed"] = 42
    cfg["data"]["train_manifest"] = TRAIN
    cfg["data"]["val_manifest"] = VALIDATION
    cfg["training"]["class_weight_multipliers"]["TRANSACTION"] = 1.4
    cfg["distillation"]["primary_focal_gamma"] = 0.0
    cfg["output"]["checkpoint_dir"] = str(ARTIFACT.relative_to(TRAINING))
    cfg["output"]["keras_path"] = str((ARTIFACT / "sms_bytecnn_fp32.keras").relative_to(TRAINING))
    ARTIFACT.mkdir(parents=True)
    REPORT.mkdir(parents=True)
    config = ARTIFACT / "config.yaml"
    config.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    completed = subprocess.run([sys.executable, str(TRAINING / "scripts/distill_student.py"), "--config", str(config), "--seed", "42", "--hard-only"], cwd=REPO, env={**os.environ, "PYTHONPATH": str(TRAINING)})
    manifest_path = ARTIFACT / "distill_manifest.json"
    result = {"run_id": RUN_ID, "status": "EXPLORATORY_PROVISIONAL_VALIDATION_ONLY", "claim_allowed": False, "formal_acceptance_allowed": False, "locked_test_read": False, "quantization_run": False, "android_export_run": False, "seed": 42, "hypothesis": "Removing focal modulation improves weighted hard-label class boundaries and training stability.", "only_changed_variable": "distillation.primary_focal_gamma=0.0 (baseline=0.5)", "config_sha256": sha256(config), "returncode": completed.returncode}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")); result["val_metrics"] = manifest.get("val_metrics", {}); result["best_epoch"] = manifest.get("best_epoch")
    (REPORT / "experiment.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"run_id": RUN_ID, "returncode": completed.returncode, "has_manifest": manifest_path.exists()}))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
