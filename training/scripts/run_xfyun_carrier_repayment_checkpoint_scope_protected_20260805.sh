#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
host_root="/mnt/c/dev/Android_SMS_Classifier"
run_id="stage2_xfyun_carrier_repayment_checkpoint_scope_protected_20260805_r1"
template="$repo_root/training/scripts/run_xfyun_carrier_repayment_protection_loss_0p70_20260805.py"
dst="run_xfyun_carrier_repayment_checkpoint_scope_protected_20260805.py"
report_root="$host_root/training/reports/experiments"

cp "$host_root/training/scripts/run_xfyun_carrier_repayment_protection_loss_0p70_20260805.py" \
  "$repo_root/training/scripts/run_xfyun_carrier_repayment_protection_loss_0p70_20260805.py"

# Generate an isolated single-variable variant from the recorded baseline runner.
sed \
  -e "s/stage2_xfyun_carrier_repayment_protection_loss_0p70_20260805_r1/${run_id}/g" \
  -e 's/cfg\["transaction_protection"\]\["loss_weight"\] = 0.70/cfg["transaction_protection"]["checkpoint_scope"] = "protected"/' \
  -e 's/Increasing only the shared transaction-protection loss weight can/Using the protected-head validation checkpoint scope can/' \
  -e 's/reduce transaction misses without inference-time category overrides./select a better checkpoint for the deployable classifier without changing inference-time category overrides./' \
  -e 's/transaction_protection.loss_weight=0.70 (baseline=0.35)/transaction_protection.checkpoint_scope=protected (baseline=primary)/' \
  "$template" > "$repo_root/training/scripts/$dst"

cd "$repo_root"
PYTHONPATH=training "$repo_root/.venv/bin/python" "$repo_root/training/scripts/$dst" --report-root "$report_root"
