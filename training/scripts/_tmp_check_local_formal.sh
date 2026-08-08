#!/usr/bin/env bash
set -eu
export PATH="/home/colab/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
if [[ -f "$HOME/.config/wsl-proxy.env" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/.config/wsl-proxy.env"
fi
echo "PROXY=${http_proxy:-none}"
ROOT="$HOME/projects/Android_SMS_Classifier"
WIN_ROOT="/mnt/c/Users/woshinibaba/Documents/oppo的项目/Android_SMS_Classifier"
cd "$ROOT"
echo "BRANCH=$(git branch --show-current)"
git log -3 --oneline
echo "=== WSL quantize/verify markers ==="
grep -n "inference_input_type\|clone_bytecnn\|resolve_path\|quantize_annotate" \
  training/scripts/quantize_int8.py training/scripts/verify_tflite.py | head -40 || true
echo "=== WIN quantize/verify markers ==="
grep -n "inference_input_type\|clone_bytecnn\|resolve_path\|quantize_annotate" \
  "$WIN_ROOT/training/scripts/quantize_int8.py" "$WIN_ROOT/training/scripts/verify_tflite.py" | head -40 || true
echo "=== scripts ==="
ls -la training/scripts/_colab_distill_e10_run.sh training/scripts/_colab_formal_run.sh
wc -l training/scripts/_colab_distill_e10_run.sh
grep -n "SESSION=\|formal_v2\|sms_formal\|EXPORT\|colab_export" training/scripts/_colab_distill_e10_run.sh | head -40
echo "=== colab ==="
colab sessions || true
colab whoami | head -20 || true
