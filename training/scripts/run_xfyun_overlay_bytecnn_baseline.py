#!/usr/bin/env python3
"""Run one hard-label ByteCNN baseline on the provisional xfyun overlay only."""
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
RUN_ID = "stage2_xfyun_overlay_bytecnn_hard_20260803_r1"
DATA = TRAINING / "data/processed_xfyun_ai_annotation_20260802_r1"
ARTIFACT = TRAINING / "artifacts/experiments" / RUN_ID
REPORT = TRAINING / "reports/experiments" / RUN_ID


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if ARTIFACT.exists() or REPORT.exists():
        raise SystemExit(f"refusing to overwrite run_id: {RUN_ID}")
    cfg = yaml.safe_load((TRAINING / "configs/student.yaml").read_text(encoding="utf-8"))
    cfg = copy.deepcopy(cfg)
    cfg["seed"] = 42
    cfg["data"]["train_manifest"] = "data/processed_xfyun_ai_annotation_20260802_r1/train.jsonl"
    cfg["data"]["val_manifest"] = "data/processed_xfyun_ai_annotation_20260802_r1/validation.jsonl"
    cfg["output"]["checkpoint_dir"] = str((ARTIFACT).relative_to(TRAINING))
    cfg["output"]["keras_path"] = str((ARTIFACT / "sms_bytecnn_fp32.keras").relative_to(TRAINING))
    ARTIFACT.mkdir(parents=True)
    REPORT.mkdir(parents=True)
    config_path = ARTIFACT / "config.yaml"
    config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    command = [sys.executable, str(TRAINING / "scripts/distill_student.py"), "--config", str(config_path), "--seed", "42", "--hard-only"]
    env = {**os.environ, "PYTHONPATH": str(TRAINING)}
    completed = subprocess.run(command, cwd=REPO, env=env)
    manifest_path = ARTIFACT / "distill_manifest.json"
    result = {"run_id": RUN_ID, "status": "EXPLORATORY_PROVISIONAL_VALIDATION_ONLY", "claim_allowed": False, "formal_acceptance_allowed": False, "locked_test_read": False, "quantization_run": False, "android_export_run": False, "seed": 42, "hypothesis": "Provisional xfyun label corrections improve validation metrics over the stage-0 baseline without changing architecture or thresholds.", "only_changed_variable": "data=train/validation provisional overlay", "config_sha256": sha256(config_path), "data_sha256": {name: sha256(DATA / f"{name}.jsonl") for name in ("train", "validation")}, "returncode": completed.returncode}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result["val_metrics"] = manifest.get("val_metrics", {})
        result["best_epoch"] = manifest.get("best_epoch")
        result["model_sha256"] = sha256(ARTIFACT / "sms_bytecnn_fp32.keras") if (ARTIFACT / "sms_bytecnn_fp32.keras").exists() else None
    (REPORT / "experiment.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"run_id": RUN_ID, "returncode": completed.returncode, "has_manifest": manifest_path.exists()}, ensure_ascii=False))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
