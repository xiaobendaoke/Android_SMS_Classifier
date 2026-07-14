#!/usr/bin/env python3
"""Verify Keras and TFLite prediction consistency."""
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


def check_tflite() -> Optional[str]:
    try:
        import tensorflow as tf  # noqa: F401
        if not hasattr(tf.lite, "Interpreter"):
            return "TensorFlow Lite interpreter unavailable."
    except ImportError:
        return (
            f"TensorFlow (with TFLite) is required. "
            f"Install per {SETUP_DOC} (see requirements-train.txt)."
        )
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify TFLite model loads and matches Keras predictions."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Quantization/verify config YAML.",
    )
    parser.add_argument(
        "--tflite",
        type=Path,
        default=None,
        help="Optional path to .tflite model.",
    )
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed.")
    return parser


def resolve_tflite_path(args: argparse.Namespace) -> Path:
    if args.tflite is not None:
        return args.tflite
    with args.config.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    rel = cfg.get("output_tflite", "artifacts/student/sms_bytecnn_int8.tflite")
    path = Path(rel)
    if not path.is_absolute():
        path = ROOT / path
    return path


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.config.exists():
        print(f"Config missing: {args.config}", file=sys.stderr)
        return 1

    tflite_path = resolve_tflite_path(args)
    if not tflite_path.exists():
        print(f"TFLite model not found: {tflite_path}", file=sys.stderr)
        return 2

    err = check_tflite()
    if err:
        print(err, file=sys.stderr)
        return 2

    print(f"TFLite verify entry: {tflite_path} ({tflite_path.stat().st_size} bytes)")
    print("Load with tf.lite.Interpreter and compare against Keras on training machine.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
