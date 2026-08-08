#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
RUN="stage2_xfyun_carrier_repayment_lr_5e4_no_protection_head_20260806_r1"
TARGET="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments/$RUN"
METRICS="$TARGET/post_training_keras_metrics.json"
DECISION="$TARGET/decision.json"

set +e
"$ROOT/.venv/bin/python" "$ROOT/training/scripts/evaluate.py" \
  --test "$ROOT/training/data/processed_xfyun_carrier_repayment_relabel_20260804_r1/validation.jsonl" \
  --mode keras \
  --keras "$ROOT/training/artifacts/experiments/$RUN/sms_bytecnn_fp32.keras" \
  --output "$METRICS" \
  --seed 42 \
  --stage "$RUN" \
  --error-samples 0 \
  --require-acceptance \
  --targets-config "$ROOT/training/configs/student.yaml"
eval_rc=$?
set -e

"$ROOT/.venv/bin/python" - "$RUN" "$METRICS" "$DECISION" <<'PY'
import json
import sys
from pathlib import Path

run, metrics_path, decision_path = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
scope = metrics["acceptance_scope"]["metrics"]
per_class = scope["per_class"]
failed = list(metrics.get("gate_errors", []))
targets = metrics.get("acceptance_targets", {})
payload = {
    "run_id": run,
    "decision": "accepted_for_human_review_preparation" if not failed else "rejected",
    "decision_reason": (
        "The same independently evaluated Keras zh validation run satisfied all five acceptance gates."
        if not failed
        else "The same independently evaluated Keras zh validation run did not satisfy all five acceptance gates."
    ),
    "annotation_status": "PROVISIONAL_AUTOMATED_MULTI_PASS",
    "claim_allowed": False,
    "human_verified": False,
    "formal_acceptance_allowed": False,
    "locked_test_read": False,
    "automated_gates_passed": not failed,
    "independent_evaluation": "post_training_keras_metrics.json",
    "acceptance_scope": ["zh"],
    "metrics": {
        "transaction_recall": per_class["TRANSACTION"]["recall"],
        "transaction_precision": per_class["TRANSACTION"]["precision"],
        "macro_f1": scope["macro_f1"],
        "harass_f1": per_class["HARASS"]["f1"],
        "fraud_recall": per_class["FRAUD"]["recall"],
    },
    "acceptance_targets": targets,
    "failed_gates": failed,
    "passed_gates": [name for name in targets if not any(item.startswith(name + "=") for item in failed)],
    "nan_observed": False,
    "locked_test_evaluated": False,
    "human_review_package_allowed": not failed,
}
decision_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"run_id": run, "decision": payload["decision"], "failed_gates": failed}, ensure_ascii=False))
PY

exit "$eval_rc"
