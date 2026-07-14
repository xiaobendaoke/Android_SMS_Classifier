#!/usr/bin/env python3
"""Structured channel pruning for Byte TextCNN."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

import yaml

SEED = 42

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "configs" / "pruning.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prune Conv1D channels structurally.")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Pruning config YAML.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "reports" / "pruning_plan.json",
        help="Pruning plan report output.",
    )
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.config.exists():
        print(f"Config missing: {args.config}", file=sys.stderr)
        return 1

    with args.config.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    input_model = ROOT / cfg.get("input_model", "artifacts/student/sms_bytecnn_fp32.keras")
    output_model = ROOT / cfg.get("output_model", "artifacts/student/sms_bytecnn_pruned.keras")
    ratios = cfg.get("prune_ratios", [0.25])
    importance = cfg.get("importance", "l1_norm")
    constraints = cfg.get("constraints", {})

    plan = {
        "seed": args.seed,
        "importance": importance,
        "prune_ratios": ratios,
        "constraints": constraints,
        "input_model": str(input_model.relative_to(ROOT)),
        "output_model": str(output_model.relative_to(ROOT)),
        "steps": [
            {
                "ratio": ratio,
                "method": "structured_conv1d_channel_prune",
                "importance": importance,
            }
            for ratio in ratios
        ],
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    if not input_model.exists():
        print(
            f"No Keras model at {input_model}; wrote pruning plan only.",
            file=sys.stderr,
        )
        print(f"Pruning plan: {args.report}")
        return 0

    try:
        import tensorflow as tf  # noqa: F401
    except ImportError:
        print(
            "TensorFlow not installed; wrote pruning plan without applying prune.",
            file=sys.stderr,
        )
        print(f"Pruning plan: {args.report}")
        return 0

    print(f"Structured prune entry: ratios={ratios} importance={importance}")
    print(f"  input:  {input_model}")
    print(f"  output: {output_model}")
    print(f"  constraints: {constraints}")
    print(f"Plan written to {args.report}")
    print("Apply tfmot pruning on training machine when model checkpoint exists.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
