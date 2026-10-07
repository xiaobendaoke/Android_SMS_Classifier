#!/usr/bin/env python3
"""Run validation-only student weight experiments without touching the test split."""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent

EXPERIMENTS = {
    "balanced_txn2": {
        "class_weight_strategy": "balanced",
        "class_weight_multipliers": {
            "TRANSACTION": 2.0,
            "AD": 1.0,
            "HARASS": 1.0,
            "FRAUD": 1.0,
        },
    },
    "balanced_txn1": {
        "class_weight_strategy": "balanced",
        "class_weight_multipliers": {
            "TRANSACTION": 1.0,
            "AD": 1.0,
            "HARASS": 1.0,
            "FRAUD": 1.0,
        },
    },
    "clipped_txn1_1": {
        "class_weight_strategy": "balanced",
        "class_weight_clip": [0.75, 1.50],
        "class_weight_multipliers": {
            "TRANSACTION": 1.1,
            "AD": 1.0,
            "HARASS": 1.0,
            "FRAUD": 1.0,
        },
    },
    "uniform": {
        "class_weight_strategy": "uniform",
        "class_weight_multipliers": {},
    },
}


def metric(metrics: dict, label: str, field: str) -> float:
    return float(metrics.get("per_class", {}).get(label, {}).get(field, 0.0))


def main() -> int:
    base_path = ROOT / "configs" / "student.yaml"
    base = yaml.safe_load(base_path.read_text(encoding="utf-8"))
    experiment_root = ROOT / "artifacts" / "experiments" / "student_v4"
    experiment_root.mkdir(parents=True, exist_ok=True)
    results = []

    for name, overrides in EXPERIMENTS.items():
        run_dir = experiment_root / name
        run_dir.mkdir(parents=True, exist_ok=True)
        cfg = copy.deepcopy(base)
        cfg["training"].update(overrides)
        cfg["training"]["epochs"] = 15
        cfg["training"]["min_epochs"] = 5
        cfg["training"]["early_stopping_patience"] = 4
        cfg["output"]["checkpoint_dir"] = str(run_dir.relative_to(ROOT))
        cfg["output"]["keras_path"] = str(
            (run_dir / "sms_bytecnn_fp32.keras").relative_to(ROOT)
        )
        config_path = run_dir / "config.yaml"
        config_path.write_text(
            yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        command = [
            sys.executable,
            str(ROOT / "scripts" / "distill_student.py"),
            "--config",
            str(config_path),
            "--seed",
            "42",
            "--hard-only",
        ]
        print(f"\n=== {name} ===", flush=True)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT)
        completed = subprocess.run(command, cwd=REPO, env=env)
        manifest_path = run_dir / "distill_manifest.json"
        if not manifest_path.exists():
            results.append({"name": name, "returncode": completed.returncode})
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        metrics = manifest.get("val_metrics", {})
        results.append(
            {
                "name": name,
                "returncode": completed.returncode,
                "best_epoch": manifest.get("best_epoch"),
                "macro_f1": float(metrics.get("macro_f1", 0.0)),
                "transaction_recall": metric(metrics, "TRANSACTION", "recall"),
                "transaction_precision": metric(metrics, "TRANSACTION", "precision"),
                "harass_f1": metric(metrics, "HARASS", "f1"),
                "fraud_recall": metric(metrics, "FRAUD", "recall"),
                "class_weights": manifest.get("class_weights", {}),
            }
        )

    summary_path = ROOT / "reports" / "metrics" / "student_v4_weight_sweep.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps({"locked_test_read": False, "results": results}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(results, indent=2), flush=True)
    print(f"Wrote {summary_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
