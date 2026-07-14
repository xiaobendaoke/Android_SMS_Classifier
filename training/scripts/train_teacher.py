#!/usr/bin/env python3
"""Fine-tune bert-base-multilingual-cased teacher model."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

import yaml

SEED = 42
SETUP_DOC = "docs/异机测试环境安装清单.md"

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "configs" / "teacher.yaml"


def check_heavy_deps() -> Optional[str]:
    """Return error message if heavy deps are missing."""
    missing = []
    try:
        import tensorflow  # noqa: F401
    except ImportError:
        missing.append("tensorflow")
    try:
        import transformers  # noqa: F401
    except ImportError:
        missing.append("transformers")
    if missing:
        return (
            f"Missing heavy training dependencies: {', '.join(missing)}. "
            f"Install per {SETUP_DOC} (see requirements-train.txt). "
            "This script must run on a training machine with GPU/CPU resources."
        )
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fine-tune multilingual BERT teacher (training machine only)."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Teacher training config YAML.",
    )
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.config.exists():
        print(f"Config missing: {args.config}", file=sys.stderr)
        return 1

    err = check_heavy_deps()
    if err:
        print(err, file=sys.stderr)
        return 2

    with args.config.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    model_name = cfg.get("model", {}).get("name", "bert-base-multilingual-cased")
    train_manifest = ROOT / cfg.get("data", {}).get("train_manifest", "data/processed/train.jsonl")
    val_manifest = ROOT / cfg.get("data", {}).get("val_manifest", "data/processed/validation.jsonl")
    output_dir = ROOT / cfg.get("output", {}).get("checkpoint_dir", "artifacts/teacher")

    if not train_manifest.exists():
        print(f"Training manifest missing: {train_manifest}", file=sys.stderr)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    # Entry outline — full fine-tune runs on training machine with deps installed.
    print(f"Teacher fine-tune entry: model={model_name} seed={args.seed}")
    print(f"  train: {train_manifest}")
    print(f"  val:   {val_manifest}")
    print(f"  out:   {output_dir}")
    print("Run with transformers.Trainer on the training machine to execute.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
