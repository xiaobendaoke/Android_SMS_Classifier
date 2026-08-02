#!/usr/bin/env bash
# Align torch/TF CUDA wheels with the Windows NVIDIA driver exposed to WSL.
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$HOME/projects/Android_SMS_Classifier}"
VENV="$ROOT/.venv"
PIP_INDEX="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
# Driver reported CUDA 12.9 → prefer cu124/cu126 wheels, not cu130.
TORCH_INDEX="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu124}"

unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy || true
export PATH="$HOME/.local/bin:$PATH"

cd "$ROOT"
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "=== nvidia-smi ==="
nvidia-smi || true

echo "=== Reinstall torch cu124 ==="
uv pip uninstall --python "$VENV/bin/python" torch triton || true
uv pip install --python "$VENV/bin/python" \
  --index-url "$TORCH_INDEX" \
  --extra-index-url "$PIP_INDEX" \
  "torch==2.6.0"

echo "=== Reinstall TensorFlow with CUDA extras ==="
uv pip uninstall --python "$VENV/bin/python" tensorflow tensorflow-cpu || true
# TF 2.16+ ships CUDA via pip extras on Linux.
uv pip install --python "$VENV/bin/python" -i "$PIP_INDEX" \
  "tensorflow[and-cuda]>=2.16.0,<2.20" \
  "tensorflow-model-optimization>=0.8.0"

echo "=== Verify GPU ==="
python - <<'PY'
import json
report = {}
import torch
report["torch"] = torch.__version__
report["torch_cuda"] = torch.cuda.is_available()
if torch.cuda.is_available():
    report["torch_gpu"] = torch.cuda.get_device_name(0)
    x = torch.randn(2, 3, device="cuda")
    report["torch_matmul_ok"] = bool((x @ x.T).shape == (2, 2))

import tensorflow as tf
report["tensorflow"] = tf.__version__
gpus = tf.config.list_physical_devices("GPU")
report["tf_gpu_count"] = len(gpus)
report["tf_gpus"] = [g.name for g in gpus]
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report.get("torch_cuda") or report.get("tf_gpu_count", 0) > 0 else 3)
PY

echo "GPU_FIX_DONE"
