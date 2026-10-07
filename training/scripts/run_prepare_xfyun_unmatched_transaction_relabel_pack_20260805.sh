#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/prepare_xfyun_unmatched_transaction_relabel_pack_20260805.py "$ROOT/training/scripts/prepare_xfyun_unmatched_transaction_relabel_pack_20260805.py"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/prepare_xfyun_unmatched_transaction_relabel_pack_20260805.py"
