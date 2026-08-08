#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
HOST="/mnt/c/dev/Android_SMS_Classifier"
RUN="stage2_xfyun_carrier_repayment_focal_gamma_0_20260805_r1"
SRC="run_xfyun_carrier_repayment_protection_loss_0p70_20260805.py"
DST="run_xfyun_carrier_repayment_focal_gamma_0_20260805.py"
cp "$HOST/training/scripts/$SRC" "$ROOT/training/scripts/$DST"
sed -i "s/stage2_xfyun_carrier_repayment_protection_loss_0p70_20260805_r1/$RUN/g" "$ROOT/training/scripts/$DST"
sed -i 's/cfg\["transaction_protection"\]\["loss_weight"\] = 0.70/cfg["distillation"]["primary_focal_gamma"] = 0.0/' "$ROOT/training/scripts/$DST"
sed -i 's/transaction_protection.loss_weight=0.70 (baseline=0.35)/distillation.primary_focal_gamma=0.0 (baseline=0.50)/' "$ROOT/training/scripts/$DST"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/$DST" --report-root "$HOST/training/reports/experiments"
