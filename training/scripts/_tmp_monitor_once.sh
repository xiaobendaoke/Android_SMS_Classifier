#!/usr/bin/env bash
set -eu
export PATH="/home/colab/.local/bin:/usr/bin:/bin"
if [[ -f "$HOME/.config/wsl-proxy.env" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/.config/wsl-proxy.env"
fi
export NO_PROXY="localhost,127.0.0.1,::1,.prod.colab.dev"
export no_proxy="$NO_PROXY"
echo "==== $(date -Is) ===="
colab exec -s sms_formal_v2 --timeout 90 -f "/mnt/c/Users/woshinibaba/Documents/oppo的项目/Android_SMS_Classifier/training/scripts/_tmp_remote_status.py" || echo "REMOTE_STATUS_FAIL"
echo "==== LOCAL ===="
LOG=$(ls -t "$HOME"/formal_v2_continue_*.log 2>/dev/null | head -1 || true)
echo "LOG=${LOG:-none}"
if [[ -n "${LOG:-}" ]]; then
  grep -E 'POLL_STATE|COPIED_TO|FATAL|DETACHED|UPLOAD|=== ' "$LOG" | tail -n 30 || true
fi
ZIP="/mnt/c/Users/woshinibaba/Documents/oppo的项目/Android_SMS_Classifier/training/reports/colab_export_formal_v2.zip"
if [[ -f "$ZIP" ]]; then
  ls -lh "$ZIP"
  echo "ZIP_READY"
else
  echo "ZIP_MISSING"
fi
