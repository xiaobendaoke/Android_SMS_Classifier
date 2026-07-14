#!/usr/bin/env python3
"""INT8 post-training quantization for student model."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

import yaml

SEED = 42
SETUP_DOC = "docs/异机测试环境安装清单.md"

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "configs" / "quantization.yaml"


def check_tensorflow() -> Optional[str]:
    try:
        import tensorflow as tf  # noqa: F401
    except ImportError:
        return (
            f"TensorFlow is required for INT8 quantization. "
            f"Install per {SETUP_DOC} (see requirements-train.txt)."
        )
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Quantize model to INT8 TFLite.")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Quantization config YAML.",
    )
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.config.exists():
        print(f"Config missing: {args.config}", file=sys.stderr)
        return 1

    err = check_tensorflow()
    if err:
        print(err, file=sys.stderr)
        return 2

    with args.config.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    mode = cfg.get("mode", "ptq")
    input_model = ROOT / cfg.get("input_model", "artifacts/student/sms_bytecnn_pruned.keras")
    output_tflite = ROOT / cfg.get("output_tflite", "artifacts/student/sms_bytecnn_int8.tflite")
    rep_manifest = ROOT / cfg.get("representative", {}).get(
        "manifest", "data/processed/representative.jsonl"
    )

    if not input_model.exists():
        print(f"Input Keras model missing: {input_model}", file=sys.stderr)
        return 1

    output_tflite.parent.mkdir(parents=True, exist_ok=True)
    print(f"Quantization entry: mode={mode} seed={args.seed}")
    print(f"  input:  {input_model}")
    print(f"  output: {output_tflite}")
    print(f"  representative: {rep_manifest}")
    print("Run TFLiteConverter with INT8 representative dataset on training machine.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
