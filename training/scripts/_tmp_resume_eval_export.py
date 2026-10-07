#!/usr/bin/env python3
"""Resume: locked test eval (compat evaluate.py) + export zip. Dense INT8 already exists."""
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
STATUS = Path("/content/formal_v2_status.json")


def write_status(stage: str, **extra) -> None:
    import time

    payload = {"stage": stage, "ts": time.time(), "pid": os.getpid(), **extra}
    STATUS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("STATUS", stage, flush=True)


def run(*args: str) -> None:
    cmd = [sys.executable, "-u", *args]
    print("RUN", " ".join(cmd), flush=True)
    write_status("running", cmd=" ".join(cmd))
    p = subprocess.run(cmd)
    if p.returncode != 0:
        write_status("failed", cmd=" ".join(cmd), returncode=p.returncode)
        raise SystemExit(p.returncode)


write_status("resume_eval_export")
student_dir = ROOT / "training/artifacts/student"
dense_tflite = student_dir / "sms_bytecnn_dense_int8.tflite"
final_tflite = student_dir / "sms_bytecnn_int8.tflite"
assert dense_tflite.is_file(), dense_tflite
shutil.copy2(dense_tflite, final_tflite)

selected_tflite = "training/artifacts/student/sms_bytecnn_dense_int8.tflite"
Path("training/reports/metrics").mkdir(parents=True, exist_ok=True)
Path("training/reports/metrics/selected_model.json").write_text(
    json.dumps(
        {
            "kind": "dense_int8",
            "tflite": selected_tflite,
            "prune_ok": False,
            "note": "resume eval+export after quantize success",
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

# Compatible with older evaluate.py (no --stage/--error-samples/--keras).
run(
    "training/scripts/evaluate.py",
    "--mode",
    "tflite",
    "--tflite",
    selected_tflite,
    "--test",
    "training/data/processed/test.jsonl",
    "--output",
    "training/reports/metrics/evaluate.json",
    "--seed",
    "42",
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
# include quantize/verify reports if present
for name in ("quantize_dense.json", "verify_tflite.json"):
    src = metrics_dir / name
    if src.exists():
        (export_dir / "metrics").mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, export_dir / "metrics" / name)
shutil.make_archive("/content/colab_export_formal_v2", "zip", export_dir)
zip_size = Path("/content/colab_export_formal_v2.zip").stat().st_size
print("EXPORT_ZIP", zip_size, flush=True)
write_status("done", export_zip="/content/colab_export_formal_v2.zip", zip_size=zip_size)
print("RESUME_OK", flush=True)
