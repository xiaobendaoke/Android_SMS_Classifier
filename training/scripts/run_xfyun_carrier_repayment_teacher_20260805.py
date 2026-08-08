#!/usr/bin/env python3
"""Train the prescribed Chinese BERT teacher on the provisional overlay."""
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
RUN = "stage2_xfyun_carrier_repayment_teacher_20260805_r1"
ARTIFACT = ROOT / "artifacts" / "experiments" / RUN
DATA = ROOT / "data" / "processed_xfyun_carrier_repayment_relabel_20260804_r1"
MODEL_PATH = "/home/colab/hf_cache/bert-base-chinese"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-root", required=True, type=Path)
    args = parser.parse_args()
    report = args.report_root / RUN
    if ARTIFACT.exists() or report.exists():
        raise SystemExit(f"refusing to overwrite run_id: {RUN}")
    cfg = copy.deepcopy(yaml.safe_load((ROOT / "configs" / "teacher.yaml").read_text(encoding="utf-8")))
    cfg["seed"] = 42
    cfg["data"]["train_manifest"] = "data/processed_xfyun_carrier_repayment_relabel_20260804_r1/train.jsonl"
    cfg["data"]["val_manifest"] = "data/processed_xfyun_carrier_repayment_relabel_20260804_r1/validation.jsonl"
    cfg["output"]["checkpoint_dir"] = str(ARTIFACT.relative_to(ROOT))
    cfg["output"]["manifest"] = str((ARTIFACT / "teacher_manifest.json").relative_to(ROOT))
    ARTIFACT.mkdir(parents=True)
    report.mkdir(parents=True)
    config = ARTIFACT / "config.yaml"
    config.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "train_teacher.py"), "--config", str(config), "--model-path", MODEL_PATH, "--seed", "42", "--logits-manifest", str(ARTIFACT / "teacher_logits_manifest.json")],
        cwd=REPO,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        check=False,
    )
    manifest_path = ARTIFACT / "teacher_manifest.json"
    result = {
        "run_id": RUN, "status": "EXPLORATORY_PROVISIONAL_VALIDATION_ONLY", "claim_allowed": False,
        "human_verified": False, "formal_acceptance_allowed": False, "locked_test_read": False,
        "quantization_run": False, "android_export_run": False, "seed": 42,
        "hypothesis": "The prescribed bert-base-chinese teacher can improve Chinese category separation versus the ByteCNN-only path on the same provisional overlay.",
        "only_changed_variable": "model_family=bert-base-chinese teacher",
        "config_sha256": sha256(config),
        "data_sha256": {name: sha256(DATA / f"{name}.jsonl") for name in ("train", "validation")},
        "returncode": completed.returncode,
    }
    if manifest_path.exists():
        result["teacher_manifest"] = json.loads(manifest_path.read_text(encoding="utf-8"))
    (report / "experiment.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"run_id": RUN, "returncode": completed.returncode, "has_manifest": manifest_path.exists()}, ensure_ascii=False))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
