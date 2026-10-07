#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
VENV="${VENV:-$ROOT/.venv}"
MODEL_DIR="${MODEL_DIR:-/home/colab/hf_cache/bert-base-chinese}"

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "WSL training environment missing: $VENV" >&2
  exit 1
fi
if [[ ! -s "$MODEL_DIR/config.json" ]]; then
  echo "Chinese teacher model missing: $MODEL_DIR" >&2
  echo "Run run_recall_v5_local.sh once to download it." >&2
  exit 2
fi
if [[ ! -s "$MODEL_DIR/model.safetensors" && ! -s "$MODEL_DIR/pytorch_model.bin" ]]; then
  echo "Chinese teacher weights missing: $MODEL_DIR" >&2
  exit 2
fi

export PATH="$VENV/bin:$PATH"
export PYTHONPATH="$ROOT/training"
export TF_CPP_MIN_LOG_LEVEL="${TF_CPP_MIN_LOG_LEVEL:-2}"
export TOKENIZERS_PARALLELISM=false
export HF_HUB_DISABLE_XET=1

UNLOCK_ARGS=()
for arg in "$@"; do
  if [[ "$arg" == "--unlock-locked-test" ]]; then
    UNLOCK_ARGS+=(--unlock-locked-test)
  fi
done

cd "$ROOT"
# Default is validation-only. Locked test / quantize / Android export require
# an explicit --unlock-locked-test after audits pass.
exec "$VENV/bin/python" -u training/scripts/run_recall_v4.py \
  --teacher-model-path "$MODEL_DIR" \
  --run-name recall_v7 \
  --seed 42 \
  "${UNLOCK_ARGS[@]}"
