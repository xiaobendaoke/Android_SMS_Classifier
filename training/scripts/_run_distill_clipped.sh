#!/usr/bin/env bash
set -euo pipefail
ROOT="/mnt/c/dev/Android_SMS_Classifier/training"
PY="/home/colab/projects/Android_SMS_Classifier/.venv/bin/python"
export PYTHONPATH="$ROOT"
export TF_CPP_MIN_LOG_LEVEL=2

CFG_DIR="$ROOT/artifacts/experiments/student_v4_distill_clipped"
mkdir -p "$CFG_DIR"
"$PY" - <<'PY'
import copy, yaml
from pathlib import Path
root = Path("/mnt/c/dev/Android_SMS_Classifier/training")
base = yaml.safe_load((root / "configs/student.yaml").read_text(encoding="utf-8"))
cfg = copy.deepcopy(base)
cfg["training"]["class_weight_strategy"] = "balanced"
cfg["training"]["class_weight_clip"] = [0.75, 1.50]
cfg["training"]["class_weight_multipliers"] = {
    "TRANSACTION": 1.1, "AD": 1.0, "HARASS": 1.0, "FRAUD": 1.0
}
out = root / "artifacts/experiments/student_v4_distill_clipped"
cfg["output"]["checkpoint_dir"] = str(out.relative_to(root))
cfg["output"]["keras_path"] = str((out / "sms_bytecnn_fp32.keras").relative_to(root))
path = out / "config.yaml"
path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
print(path)
PY

exec "$PY" -u "$ROOT/scripts/distill_student.py" \
  --config "$CFG_DIR/config.yaml" \
  --seed 42
