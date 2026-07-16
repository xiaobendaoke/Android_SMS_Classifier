#!/usr/bin/env python3
"""Export model and rules to Android classifier-sdk assets."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import List, Optional

import yaml

SEED = 42

ROOT = Path(__file__).resolve().parent.parent
SDK_ASSETS = (
    ROOT.parent
    / "android"
    / "classifier-sdk"
    / "src"
    / "main"
    / "assets"
)
RULES_SRC = ROOT / "rules"
STUDENT_CONFIG = ROOT / "configs" / "student.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export TFLite model, rules, and metadata to classifier-sdk assets."
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=ROOT / "artifacts" / "student" / "sms_bytecnn_int8.tflite",
        help="Source TFLite model.",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=SDK_ASSETS,
        help="SDK assets root directory.",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=None,
        help="Optional model_metadata.json source.",
    )
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed.")
    return parser


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_metadata(model_path: Optional[Path]) -> dict:
    cfg = {}
    if STUDENT_CONFIG.exists():
        with STUDENT_CONFIG.open(encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
    input_cfg = cfg.get("input", {})
    model_sha = "REPLACE_DURING_BUILD"
    if model_path and model_path.exists():
        model_sha = sha256_bytes(model_path.read_bytes())
    quant_report = ROOT / "reports" / "metrics" / "quantize.json"
    quantization = "INT8"
    if quant_report.exists():
        try:
            q = json.loads(quant_report.read_text(encoding="utf-8"))
            if q.get("quantization") == "hybrid_fallback":
                quantization = "HYBRID"
            elif q.get("quantization") == "full_integer_int8":
                quantization = "INT8"
        except json.JSONDecodeError:
            pass
    return {
        "modelVersion": cfg.get("version", "1.0.0"),
        "architecture": cfg.get("architecture", "byte_textcnn"),
        "inputLength": int(input_cfg.get("max_bytes", 512)),
        "padId": int(input_cfg.get("pad_id", 0)),
        "byteOffset": int(input_cfg.get("byte_offset", 1)),
        "labels": ["TRANSACTION", "AD", "HARASS", "FRAUD"],
        "normalizationVersion": "1.0.0",
        "rulesVersion": "1.0.0",
        "quantization": quantization,
        "modelSha256": model_sha,
        "thresholds": {
            "default": {
                "TRANSACTION": 0.55,
                "AD": 0.70,
                "HARASS": 0.70,
                "FRAUD": 0.75,
            }
        },
    }


def copy_file_safe(src: Path, dest: Path) -> None:
    """Copy file contents without preserving xattrs (avoids permission issues)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(src.read_bytes())


def copy_tree_if_exists(src: Path, dest: Path) -> int:
    if not src.exists():
        return 0
    count = 0
    if src.is_dir():
        for item in src.rglob("*"):
            if item.is_file():
                rel = item.relative_to(src)
                out = dest / rel
                copy_file_safe(item, out)
                count += 1
    else:
        copy_file_safe(src, dest)
        count = 1
    return count


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.dest.exists():
        print(f"SDK assets dir missing: {args.dest}", file=sys.stderr)
        return 1

    copied = 0

    # Rules and normalize assets from training/rules if present, else SDK originals kept.
    rules_dest = args.dest / "rules"
    normalize_dest = args.dest / "normalize"
    if RULES_SRC.exists():
        copied += copy_tree_if_exists(RULES_SRC / "rules", rules_dest)
        copied += copy_tree_if_exists(RULES_SRC / "normalize", normalize_dest)
    else:
        print(
            f"No training/rules export bundle at {RULES_SRC}; keeping existing SDK rules.",
            file=sys.stderr,
        )

    # Model metadata
    meta_dest = args.dest / "model" / "model_metadata.json"
    meta_dest.parent.mkdir(parents=True, exist_ok=True)
    if args.metadata and args.metadata.exists():
        copy_file_safe(args.metadata, meta_dest)
        copied += 1
    else:
        meta = build_metadata(args.model if args.model.exists() else None)
        meta_dest.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        copied += 1
        print(f"Wrote generated metadata to {meta_dest}")

    # TFLite model (optional)
    if args.model.exists():
        dest_model = args.dest / "model" / "sms_bytecnn_int8.tflite"
        copy_file_safe(args.model, dest_model)
        copied += 1
        print(f"Exported model to {dest_model}")
    else:
        print(
            f"TFLite model not present — skipped copy from {args.model}",
            file=sys.stderr,
        )

    print(f"Export complete ({copied} file(s) updated). dest={args.dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
