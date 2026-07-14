#!/usr/bin/env python3
"""Distill Byte TextCNN student from teacher logits."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

import yaml

SEED = 42
SETUP_DOC = "docs/异机测试环境安装清单.md"

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "configs" / "student.yaml"


def check_tensorflow() -> Optional[str]:
    try:
        import tensorflow  # noqa: F401
    except ImportError:
        return (
            f"TensorFlow is required for distillation. "
            f"Install per {SETUP_DOC} (see requirements-train.txt)."
        )
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Distill Byte TextCNN student model.")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Student/distillation config YAML.",
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

    distill = cfg.get("distillation", {})
    alpha = float(distill.get("alpha", 0.6))
    beta = float(distill.get("beta", 0.4))
    temperature = float(distill.get("temperature", 4.0))
    arch = cfg.get("architecture", "byte_textcnn")
    output_dir = ROOT / cfg.get("output", {}).get("checkpoint_dir", "artifacts/student")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Distillation entry: architecture={arch} seed={args.seed}")
    print(f"  alpha={alpha} beta={beta} temperature={temperature}")
    print(f"  loss = {alpha} * CE(hard) + {beta} * KL(teacher/T, student/T)")
    print(f"  output: {output_dir}")
    print("Execute on training machine with teacher logits manifest present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
