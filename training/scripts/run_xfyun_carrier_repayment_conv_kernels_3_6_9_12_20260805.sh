#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
host_root="/mnt/c/dev/Android_SMS_Classifier"
run_id="stage2_xfyun_carrier_repayment_conv_kernels_3_6_9_12_20260805_r1"
template="$repo_root/training/scripts/run_xfyun_carrier_repayment_protection_loss_0p70_20260805.py"
dst="run_xfyun_carrier_repayment_conv_kernels_3_6_9_12_20260805.py"
report_root="$host_root/training/reports/experiments"

cp "$host_root/training/scripts/run_xfyun_carrier_repayment_protection_loss_0p70_20260805.py" \
  "$repo_root/training/scripts/run_xfyun_carrier_repayment_protection_loss_0p70_20260805.py"

# Generate an isolated single-variable variant from the recorded baseline runner.
sed \
  -e "s/stage2_xfyun_carrier_repayment_protection_loss_0p70_20260805_r1/${run_id}/g" \
  -e 's/cfg\["transaction_protection"\]\["loss_weight"\] = 0.70/cfg["model"]["conv_kernels"] = [3, 6, 9, 12]/' \
  -e 's/Increasing only the shared transaction-protection loss weight can/Adding only a 12-byte convolution kernel can/' \
  -e 's/reduce transaction misses without inference-time category overrides./capture longer Chinese transaction and HARASS phrases without changing data, labels, or inference-time category overrides./' \
  -e 's/transaction_protection.loss_weight=0.70 (baseline=0.35)/model.conv_kernels=[3,6,9,12] (baseline=[3,6,9])/' \
  "$template" > "$repo_root/training/scripts/$dst"

cd "$repo_root"
PYTHONPATH=training "$repo_root/.venv/bin/python" "$repo_root/training/scripts/$dst" --report-root "$report_root"
