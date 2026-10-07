#!/usr/bin/env bash
set -euo pipefail

ROOT="/mnt/c/dev/Android_SMS_Classifier"
VENV="/home/colab/projects/Android_SMS_Classifier/.venv"

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "WSL training environment missing: $VENV" >&2
  echo "Run tools/setup_wsl_training_env.sh first." >&2
  exit 1
fi

export PATH="$VENV/bin:$PATH"
export PYTHONPATH="$ROOT/training"
export TF_CPP_MIN_LOG_LEVEL="${TF_CPP_MIN_LOG_LEVEL:-2}"
export TOKENIZERS_PARALLELISM=false

cd "$ROOT"
exec "$VENV/bin/python" -u training/scripts/run_recall_v4.py \
  --skip-teacher \
  --seed 42
