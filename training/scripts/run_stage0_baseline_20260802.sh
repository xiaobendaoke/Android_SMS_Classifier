#!/usr/bin/env bash
set -u -o pipefail

RUN_ID="stage0_baseline_20260802"
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
VENV="${VENV:-$ROOT/.venv}"
OUT="$ROOT/training/reports/experiments/$RUN_ID"
mkdir -p "$OUT/logs"

export PATH="$VENV/bin:$PATH"
export PYTHONPATH="$ROOT/training"
export TF_CPP_MIN_LOG_LEVEL=2
export TOKENIZERS_PARALLELISM=false

record() {
  local name="$1"
  shift
  (
    printf 'command='
    printf ' %q' "$@"
    printf '\nstarted_at='
    date -u +%Y-%m-%dT%H:%M:%SZ
    "$@"
    rc=$?
    printf 'ended_at='
    date -u +%Y-%m-%dT%H:%M:%SZ
    printf 'exit_code=%s\n' "$rc"
    exit "$rc"
  ) >"$OUT/logs/$name.log" 2>&1
  rc=$?
  printf '%s %s\n' "$name" "$rc" >>"$OUT/command_exit_codes.txt"
  return 0
}

: >"$OUT/command_exit_codes.txt"
{
  printf 'run_id=%s\n' "$RUN_ID"
  printf 'started_at='
  date -u +%Y-%m-%dT%H:%M:%SZ
  printf 'root=%s\n' "$ROOT"
  git -C "$ROOT" rev-parse HEAD
  git -C "$ROOT" status --short
  uname -a
  nvidia-smi
  "$VENV/bin/python" --version
  "$VENV/bin/python" -m pip freeze
  "$VENV/bin/python" -c 'import tensorflow as tf, torch; print("tensorflow=" + tf.__version__); print("torch=" + torch.__version__); print("gpus=" + str(tf.config.list_physical_devices("GPU")))'
  sha256sum "$ROOT/training/data/manifests/dataset_manifest_v2.json" "$ROOT/training/data/manifests/split_assignment_v2.json" "$ROOT/training/configs/student.yaml" "$ROOT/training/configs/teacher.yaml" "$ROOT/training/configs/quantization.yaml" "$ROOT/training/artifacts/student/sms_bytecnn_fp32.keras" "$ROOT/training/artifacts/student/sms_bytecnn_int8.tflite" "$ROOT/android/classifier-sdk/src/main/assets/model/sms_bytecnn_int8.tflite"
} >"$OUT/environment.txt" 2>&1

record pytest "$VENV/bin/python" -m pytest "$ROOT/training/tests" -q
record validate_labels "$VENV/bin/python" "$ROOT/training/scripts/validate_labels.py" --input "$ROOT/training/data/processed_v2" --split-assignment "$ROOT/training/data/manifests/split_assignment_v2.json"
record split_leakage "$VENV/bin/python" "$ROOT/training/scripts/check_split_leakage.py" --input "$ROOT/training/data/processed_v2" --output "$OUT/dataset_leakage_v2.json"
record no_network "$VENV/bin/python" "$ROOT/tools/check_no_network_permission.py"
record sensitive_logs "$VENV/bin/python" "$ROOT/tools/check_no_sensitive_logs.py"
record release_audit "$VENV/bin/python" "$ROOT/tools/audit_release.py"
record validation_pipeline "$VENV/bin/python" "$ROOT/training/scripts/evaluate.py" --mode pipeline --keras "$ROOT/training/artifacts/student/sms_bytecnn_fp32.keras" --test "$ROOT/training/data/processed_v2/validation.jsonl" --stage "$RUN_ID" --output "$OUT/current_validation_pipeline.json" --targets-config "$ROOT/training/configs/student.yaml" --seed 42
record v4_startup_gate "$VENV/bin/python" "$ROOT/training/scripts/run_recall_v4.py" --skip-teacher --run-name recall_v7 --seed 42

printf 'ended_at=' >>"$OUT/environment.txt"
date -u +%Y-%m-%dT%H:%M:%SZ >>"$OUT/environment.txt"
exit 0
