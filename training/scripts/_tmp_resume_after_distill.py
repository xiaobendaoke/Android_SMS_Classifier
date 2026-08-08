#!/usr/bin/env python3
"""Resume formal v2 after distill succeeded: rep -> quantize -> prune/verify -> eval -> export."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("/content/Android_SMS_Classifier")
os.chdir(ROOT)
os.environ["PYTHONPATH"] = str(ROOT / "training")
os.environ["PYTHONUNBUFFERED"] = "1"
SEED = "42"
STATUS = Path("/content/formal_v2_status.json")


def write_status(stage: str, **extra) -> None:
    import time

    payload = {"stage": stage, "ts": time.time(), "pid": os.getpid(), **extra}
    STATUS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("STATUS", stage, flush=True)


def run(*args: str, allow_fail: bool = False) -> int:
    cmd = [sys.executable, "-u", *args]
    print("RUN", " ".join(cmd), flush=True)
    write_status("running", cmd=" ".join(cmd))
    p = subprocess.run(cmd)
    if p.returncode != 0 and not allow_fail:
        write_status("failed", cmd=" ".join(cmd), returncode=p.returncode)
        raise SystemExit(p.returncode)
    return p.returncode


write_status("resume_after_distill")
student_dir = ROOT / "training/artifacts/student"
dense_keras = student_dir / "sms_bytecnn_fp32.keras"
assert dense_keras.is_file(), dense_keras
assert (ROOT / "training/scripts/generate_representative_manifest.py").is_file()

cfg = ROOT / "training/configs/student.yaml"
run(
    "training/scripts/generate_representative_manifest.py",
    "--summary",
    "training/reports/metrics/representative_summary.json",
    "--seed",
    SEED,
)
# Dense Keras eval skipped: older evaluate.py on this branch has no --mode keras.
# Quantize/validation metrics still cover dense FP32 vs TFLite agreement.
run(
    "training/scripts/quantize_int8.py",
    "--input-model",
    "training/artifacts/student/sms_bytecnn_fp32.keras",
    "--output-tflite",
    "training/artifacts/student/sms_bytecnn_dense_int8.tflite",
    "--report",
    "training/reports/metrics/quantize_dense.json",
    "--profile",
    "formal",
    "--seed",
    SEED,
)

pruned_keras = student_dir / "sms_bytecnn_pruned.keras"
final_tflite = student_dir / "sms_bytecnn_int8.tflite"
dense_tflite = student_dir / "sms_bytecnn_dense_int8.tflite"
prune_cmd = [
    sys.executable,
    "training/scripts/prune_channels.py",
    "--seed",
    SEED,
    "--student-config",
    str(cfg),
    "--distill-finetune",
]
print("RUN", " ".join(prune_cmd), flush=True)
prune_rc = subprocess.run(prune_cmd).returncode
prune_ok = prune_rc == 0 and pruned_keras.is_file()
print("PRUNE_OK", prune_ok, "rc", prune_rc, flush=True)

if prune_ok:
    run(
        "training/scripts/quantize_int8.py",
        "--input-model",
        "training/artifacts/student/sms_bytecnn_pruned.keras",
        "--output-tflite",
        "training/artifacts/student/sms_bytecnn_int8.tflite",
        "--report",
        "training/reports/metrics/quantize.json",
        "--profile",
        "formal",
        "--seed",
        SEED,
    )
    verify_rc = run(
        "training/scripts/verify_tflite.py",
        "--keras",
        "training/artifacts/student/sms_bytecnn_pruned.keras",
        "--tflite",
        "training/artifacts/student/sms_bytecnn_int8.tflite",
        "--quant-report",
        "training/reports/metrics/quantize.json",
        "--test",
        "training/data/processed/validation.jsonl",
        "--seed",
        SEED,
        allow_fail=True,
    )
    selected_tflite = "training/artifacts/student/sms_bytecnn_int8.tflite"
    selected_kind = "pruned_int8"
else:
    if dense_tflite.is_file():
        shutil.copy2(dense_tflite, final_tflite)
    verify_rc = run(
        "training/scripts/verify_tflite.py",
        "--keras",
        "training/artifacts/student/sms_bytecnn_fp32.keras",
        "--tflite",
        "training/artifacts/student/sms_bytecnn_dense_int8.tflite",
        "--quant-report",
        "training/reports/metrics/quantize_dense.json",
        "--test",
        "training/data/processed/validation.jsonl",
        "--seed",
        SEED,
        allow_fail=True,
    )
    selected_tflite = "training/artifacts/student/sms_bytecnn_dense_int8.tflite"
    selected_kind = "dense_int8"

print("SELECTED_MODEL", selected_kind, selected_tflite, "verify_rc", verify_rc, flush=True)
Path("training/reports/metrics/selected_model.json").write_text(
    json.dumps(
        {
            "kind": selected_kind,
            "tflite": selected_tflite,
            "prune_ok": prune_ok,
            "verify_rc": verify_rc,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

stages = ROOT / "training/scripts/evaluate_pipeline_stages.py"
if stages.is_file():
    run(
        "training/scripts/evaluate_pipeline_stages.py",
        "--split",
        "training/data/processed/validation.jsonl",
        "--dense-keras",
        "training/artifacts/student/sms_bytecnn_fp32.keras",
        "--pruned-keras",
        "training/artifacts/student/sms_bytecnn_pruned.keras",
        "--tflite",
        selected_tflite,
        "--output",
        "training/reports/metrics/stage_comparison_validation.json",
        "--seed",
        SEED,
        allow_fail=True,
    )

run(
    "training/scripts/evaluate.py",
    "--mode",
    "tflite",
    "--tflite",
    selected_tflite,
    "--test",
    "training/data/processed/test.jsonl",
    "--stage",
    "final_locked_test",
    "--output",
    "training/reports/metrics/evaluate.json",
    "--error-samples",
    "40",
    "--error-output",
    "training/reports/metrics/error_samples.json",
    "--seed",
    SEED,
)

metrics_dir = ROOT / "training/reports/metrics"
export_dir = Path("/content/colab_export_formal_v2")
if export_dir.exists():
    shutil.rmtree(export_dir)
(export_dir / "artifacts" / "student").mkdir(parents=True)
(export_dir / "artifacts" / "teacher").mkdir(parents=True)
for name in [
    "sms_bytecnn_int8.tflite",
    "sms_bytecnn_dense_int8.tflite",
    "sms_bytecnn_fp32.keras",
    "sms_bytecnn_pruned.keras",
    "distill_manifest.json",
]:
    src = student_dir / name
    if src.exists():
        shutil.copy2(src, export_dir / "artifacts" / "student" / name)
for src in [
    ROOT / "training/data/manifests/teacher_logits_manifest.json",
    ROOT / "training/data/manifests/teacher_manifest.json",
]:
    if src.exists():
        shutil.copy2(src, export_dir / "artifacts" / "teacher" / src.name)
if metrics_dir.exists():
    shutil.copytree(metrics_dir, export_dir / "metrics", dirs_exist_ok=True)
shutil.make_archive("/content/colab_export_formal_v2", "zip", export_dir)
zip_size = Path("/content/colab_export_formal_v2.zip").stat().st_size
print("EXPORT_ZIP", zip_size, flush=True)
write_status(
    "done",
    export_zip="/content/colab_export_formal_v2.zip",
    zip_size=zip_size,
    selected_kind=selected_kind,
    verify_rc=verify_rc,
)
print("RESUME_OK", flush=True)
