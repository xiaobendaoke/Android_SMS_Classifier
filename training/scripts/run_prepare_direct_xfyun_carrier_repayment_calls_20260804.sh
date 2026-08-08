#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/prepare_direct_xfyun_carrier_repayment_calls_20260804.py "$ROOT/training/scripts/prepare_direct_xfyun_carrier_repayment_calls_20260804.py"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/prepare_direct_xfyun_carrier_repayment_calls_20260804.py"
