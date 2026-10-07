#!/usr/bin/env bash
# Bootstrap a local WSL training venv (CPU/GPU) so Colab is optional.
# Intended to run inside WSL at /home/colab/projects/Android_SMS_Classifier
# via: tools/wsl_run.ps1 -RelPath tools\setup_wsl_training_env.sh
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$HOME/projects/Android_SMS_Classifier}"
WIN_ROOT="/mnt/c/dev/Android_SMS_Classifier"
VENV="$ROOT/.venv"
# Default to system python3 (3.10 on Ubuntu 22.04). Avoid uv-managed CPython
# downloads — they often hang behind broken WSL host proxies.
PY_VER="${WSL_TRAIN_PYTHON:-system}"
PIP_INDEX="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
TORCH_INDEX="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu124}"
LOG_DIR="$HOME/wsl_training_setup_logs"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="$LOG_DIR/setup_${STAMP}.log"
mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG") 2>&1

echo "=== WSL training env setup ==="
echo "ROOT=$ROOT"
echo "LOG=$LOG"
echo "PY_VER=$PY_VER"
echo "PIP_INDEX=$PIP_INDEX"

# Prefer TUNA/direct mirrors. Host proxy frequently breaks uv/python downloads in WSL.
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy || true
echo "PROXY=disabled_for_mirror_install"

export PATH="$HOME/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"

if [[ ! -d "$WIN_ROOT" ]]; then
  echo "ERROR: Windows ASCII junction missing at $WIN_ROOT" >&2
  exit 1
fi

echo "=== Sync project from Windows ASCII junction ==="
mkdir -p "$ROOT"
if ! command -v rsync >/dev/null 2>&1; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get update -y
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y rsync
fi
rsync -a --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '.pytest_cache/' \
  --exclude '**/__pycache__/' \
  --exclude '.gradle/' \
  --exclude '**/build/' \
  --exclude 'android/.gradle/' \
  --exclude 'training/data/raw/' \
  --exclude 'training/data/processed/' \
  --exclude 'training/data/interim/' \
  --exclude 'training/artifacts/' \
  --exclude '*.tflite' \
  --exclude '*.keras' \
  --exclude '*.h5' \
  --exclude '*.ckpt' \
  "$WIN_ROOT/" "$ROOT/"
echo "SYNC_OK"

cd "$ROOT"

echo "=== System packages ==="
sudo DEBIAN_FRONTEND=noninteractive apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  build-essential curl ca-certificates git \
  python3 python3-venv python3-pip python3-dev \
  libgomp1

if ! command -v uv >/dev/null 2>&1; then
  echo "=== Install uv ==="
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
uv --version

echo "=== Create venv (Python $PY_VER) ==="
if [[ "$PY_VER" == "system" ]]; then
  uv venv "$VENV" --python python3 --clear
elif uv python install "$PY_VER"; then
  uv venv "$VENV" --python "$PY_VER" --clear
else
  echo "WARN: uv python $PY_VER failed; falling back to system python3"
  uv venv "$VENV" --python python3 --clear
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -V
pip -V || true

echo "=== Upgrade pip tooling ==="
uv pip install --python "$VENV/bin/python" -i "$PIP_INDEX" -U pip setuptools wheel

echo "=== Install light lock deps ==="
uv pip install --python "$VENV/bin/python" -i "$PIP_INDEX" -r training/requirements.lock

echo "=== Install training deps (TF / transformers / sklearn) ==="
# Prefer CUDA torch for the laptop RTX GPU. Try official cu124, then TUNA
# pytorch-wheels mirror, then CPU torch from PyPI mirror.
TORCH_OK=0
# Pin an older cu124 build — newest cu130 wheels need a newer Windows driver
# than many WSL laptops currently expose (driver CUDA 12.9).
if uv pip install --python "$VENV/bin/python" \
  --index-url "$TORCH_INDEX" \
  --extra-index-url "$PIP_INDEX" \
  "torch==2.6.0"; then
  echo "TORCH_CUDA_WHEEL_OK"
  TORCH_OK=1
elif uv pip install --python "$VENV/bin/python" \
  --index-url "https://mirrors.tuna.tsinghua.edu.cn/pytorch-wheels/cu124" \
  --extra-index-url "$PIP_INDEX" \
  "torch==2.6.0"; then
  echo "TORCH_TUNA_CUDA_OK"
  TORCH_OK=1
fi
if [[ "$TORCH_OK" -ne 1 ]]; then
  echo "WARN: CUDA torch wheel failed; installing CPU torch from $PIP_INDEX"
  uv pip install --python "$VENV/bin/python" -i "$PIP_INDEX" "torch>=2.1.0"
fi

uv pip install --python "$VENV/bin/python" -i "$PIP_INDEX" \
  "transformers>=4.40.0" \
  "tensorflow[and-cuda]>=2.16.0,<2.20" \
  "tensorflow-model-optimization>=0.8.0" \
  "scikit-learn>=1.3.2" \
  "PyYAML>=6.0" \
  "numpy>=1.24.0"

echo "=== Verify imports / devices ==="
python - <<'PY'
import importlib
import json
import sys

report = {"python": sys.version, "ok": True, "packages": {}, "devices": {}}

for name in (
    "numpy",
    "yaml",
    "pytest",
    "sklearn",
    "torch",
    "transformers",
    "tensorflow",
    "tensorflow_model_optimization",
):
    try:
        mod = importlib.import_module(name)
        report["packages"][name] = getattr(mod, "__version__", "imported")
    except Exception as exc:  # noqa: BLE001
        report["packages"][name] = f"ERROR: {exc}"
        report["ok"] = False

try:
    import torch

    report["devices"]["torch_cuda"] = bool(torch.cuda.is_available())
    if torch.cuda.is_available():
        report["devices"]["torch_gpu"] = torch.cuda.get_device_name(0)
except Exception as exc:  # noqa: BLE001
    report["devices"]["torch"] = f"ERROR: {exc}"
    report["ok"] = False

try:
    import tensorflow as tf

    gpus = tf.config.list_physical_devices("GPU")
    report["devices"]["tf_gpu_count"] = len(gpus)
    report["devices"]["tf_gpus"] = [getattr(g, "name", str(g)) for g in gpus]
except Exception as exc:  # noqa: BLE001
    report["devices"]["tensorflow"] = f"ERROR: {exc}"
    report["ok"] = False

print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["ok"] else 2)
PY

echo "=== Light pytest (no TF-heavy suites required) ==="
export PYTHONPATH="$ROOT/training"
"$VENV/bin/python" -m pytest training/tests/test_byte_encoder.py -q || true

cat > "$HOME/.config/wsl-training.env" <<EOF
# Generated by tools/setup_wsl_training_env.sh
export SMS_CLASSIFIER_ROOT="$ROOT"
export PATH="$VENV/bin:\$HOME/.local/bin:\$PATH"
export VIRTUAL_ENV="$VENV"
export PYTHONPATH="$ROOT/training"
EOF

echo
echo "=== DONE ==="
echo "Activate later:"
echo "  source $HOME/.config/wsl-training.env"
echo "  # or: source $VENV/bin/activate && cd $ROOT && export PYTHONPATH=training"
echo "LOG=$LOG"
