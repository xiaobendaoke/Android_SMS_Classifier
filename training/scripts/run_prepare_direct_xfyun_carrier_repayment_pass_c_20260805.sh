#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/prepare_direct_xfyun_carrier_repayment_pass_c_20260805.py "$ROOT/training/scripts/prepare_direct_xfyun_carrier_repayment_pass_c_20260805.py"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/prepare_direct_xfyun_carrier_repayment_pass_c_20260805.py"
