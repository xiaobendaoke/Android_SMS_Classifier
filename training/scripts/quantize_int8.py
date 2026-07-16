#!/usr/bin/env python3
"""INT8 post-training quantization for student model (QAT fallback supported)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterator, List, Optional

import numpy as np
import yaml

SEED = 42
SETUP_DOC = "docs/异机测试环境安装清单.md"

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "configs" / "quantization.yaml"
STUDENT_CONFIG = ROOT / "configs" / "student.yaml"

sys.path.insert(0, str(ROOT))
from src.byte_encoder import encode_text  # noqa: E402
from src.normalize import normalize_text  # noqa: E402
from src.schema import load_jsonl  # noqa: E402
from src.train_utils import set_seed, write_json  # noqa: E402


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
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Quantization config YAML.")
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed.")
    parser.add_argument(
        "--mode",
        choices=["ptq", "qat"],
        default=None,
        help="Override config mode.",
    )
    return parser


def representative_dataset(
    manifest: Path,
    num_samples: int,
    max_bytes: int = 512,
) -> Iterator[List[np.ndarray]]:
    records = []
    if manifest.exists():
        records = load_jsonl(manifest)
    else:
        # Fallback to train split.
        train = ROOT / "data" / "processed" / "train.jsonl"
        if train.exists():
            records = load_jsonl(train)
    for i, record in enumerate(records):
        if i >= num_samples:
            break
        ids = encode_text(normalize_text(record.text), length=max_bytes)
        yield [np.asarray([ids], dtype=np.int32)]


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.config.exists():
        print(f"Config missing: {args.config}", file=sys.stderr)
        return 1

    err = check_tensorflow()
    if err:
        print(err, file=sys.stderr)
        return 2

    import tensorflow as tf

    with args.config.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    set_seed(int(cfg.get("seed", args.seed)))
    mode = args.mode or cfg.get("mode", "ptq")
    input_model = ROOT / cfg.get("input_model", "artifacts/student/sms_bytecnn_pruned.keras")
    # Allow FP32 student if prune skipped.
    if not input_model.exists():
        alt = ROOT / "artifacts" / "student" / "sms_bytecnn_fp32.keras"
        if alt.exists():
            input_model = alt
            print(f"Pruned model missing; using {alt}")
    output_tflite = ROOT / cfg.get("output_tflite", "artifacts/student/sms_bytecnn_int8.tflite")
    rep_manifest = ROOT / cfg.get("representative", {}).get(
        "manifest", "data/processed/representative.jsonl"
    )
    num_samples = int(cfg.get("representative", {}).get("num_samples", 500))

    if not input_model.exists():
        print(f"Input Keras model missing: {input_model}", file=sys.stderr)
        return 1

    max_bytes = 512
    if STUDENT_CONFIG.exists():
        with STUDENT_CONFIG.open(encoding="utf-8") as fh:
            student_yaml = yaml.safe_load(fh) or {}
        max_bytes = int(student_yaml.get("input", {}).get("max_bytes", 512))

    model = tf.keras.models.load_model(input_model)

    if mode == "qat":
        try:
            import tensorflow_model_optimization as tfmot

            quantize_model = tfmot.quantization.keras.quantize_model
            q_aware = quantize_model(model)
            q_aware.compile(
                optimizer="adam",
                loss=tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True),
                metrics=["accuracy"],
            )
            train_path = ROOT / "data" / "processed" / "train.jsonl"
            if train_path.exists():
                from src.train_utils import load_labeled_records, records_to_xy

                records = load_labeled_records(train_path)
                x, y = records_to_xy(records, max_bytes=max_bytes)
                q_aware.fit(x, y, epochs=2, batch_size=64, verbose=1)
            model = q_aware
            print("QAT applied.")
        except Exception as exc:  # noqa: BLE001
            print(f"QAT unavailable ({exc}); falling back to PTQ.", file=sys.stderr)
            mode = "ptq"

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = lambda: representative_dataset(
        rep_manifest, num_samples=num_samples, max_bytes=max_bytes
    )
    # Full integer for weights; keep int32 inputs for byte IDs.
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int32
    converter.inference_output_type = tf.int8

    try:
        tflite_model = converter.convert()
        quant_mode = "full_integer_int8"
    except Exception as exc:  # noqa: BLE001
        print(f"Strict INT8 convert failed ({exc}); retrying hybrid PTQ.", file=sys.stderr)
        converter = tf.lite.TFLiteConverter.from_keras_model(model)
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        converter.representative_dataset = lambda: representative_dataset(
            rep_manifest, num_samples=num_samples, max_bytes=max_bytes
        )
        tflite_model = converter.convert()
        quant_mode = "hybrid_fallback"

    output_tflite.parent.mkdir(parents=True, exist_ok=True)
    output_tflite.write_bytes(tflite_model)

    import hashlib

    digest = hashlib.sha256(tflite_model).hexdigest()
    write_json(
        ROOT / "reports" / "metrics" / "quantize.json",
        {
            "seed": args.seed,
            "mode": mode,
            "quantization": quant_mode,
            "input_model": str(input_model.relative_to(ROOT)).replace("\\", "/"),
            "output_tflite": str(output_tflite.relative_to(ROOT)).replace("\\", "/"),
            "bytes": len(tflite_model),
            "sha256": digest,
            "note": (
                "hybrid_fallback is not the acceptance baseline; "
                "metadata must not claim full INT8 unless quantization=full_integer_int8."
            ),
        },
    )
    print(f"Wrote TFLite to {output_tflite} ({len(tflite_model)} bytes) mode={quant_mode}")
    print(f"sha256={digest}")
    if quant_mode != "full_integer_int8":
        print(
            "WARNING: hybrid quantization — do not label metadata as full INT8.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
