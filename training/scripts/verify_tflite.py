#!/usr/bin/env python3
"""Verify Keras vs TFLite agreement and inspect TFLite ops."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional, Set

import numpy as np
import yaml

SEED = 42
SETUP_DOC = "docs/异机测试环境安装清单.md"

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "configs" / "quantization.yaml"

sys.path.insert(0, str(ROOT))
from src.schema import LABEL_ORDER  # noqa: E402
from src.train_utils import load_labeled_records, records_to_xy, set_seed, write_json  # noqa: E402

# Ops that must not appear for the acceptance baseline.
FORBIDDEN_OP_SUBSTRINGS = ("Flex", "SELECT_TF", "CUSTOM")


def check_tensorflow() -> Optional[str]:
    try:
        import tensorflow as tf  # noqa: F401
    except ImportError:
        return (
            f"TensorFlow is required to verify TFLite. "
            f"Install per {SETUP_DOC} (see requirements-train.txt)."
        )
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify Keras/TFLite consistency.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Quantization config YAML.")
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed.")
    parser.add_argument(
        "--keras",
        type=Path,
        default=None,
        help="Optional Keras model path (defaults to pruned/fp32 student).",
    )
    parser.add_argument(
        "--tflite",
        type=Path,
        default=None,
        help="Optional TFLite path.",
    )
    parser.add_argument(
        "--test",
        type=Path,
        default=ROOT / "data" / "processed" / "validation.jsonl",
        help="JSONL used for agreement check.",
    )
    return parser


def list_tflite_ops(tflite_path: Path) -> Set[str]:
    import tensorflow as tf

    interp = tf.lite.Interpreter(model_content=tflite_path.read_bytes())
    interp.allocate_tensors()
    # Prefer flatbuffer introspection when available.
    try:
        from tensorflow.lite.python import schema_py_generated as schema_fb

        model = schema_fb.Model.GetRootAsModel(tflite_path.read_bytes(), 0)
        ops: Set[str] = set()
        for i in range(model.OperatorCodesLength()):
            code = model.OperatorCodes(i)
            builtin = code.BuiltinCode()
            custom = code.CustomCode()
            if custom:
                ops.add(custom.decode("utf-8") if isinstance(custom, bytes) else str(custom))
            else:
                ops.add(str(builtin))
        return ops
    except Exception:
        details = interp.get_tensor_details()
        return {d.get("name", "") for d in details}


def run_tflite(tflite_path: Path, x: np.ndarray) -> np.ndarray:
    import tensorflow as tf

    interp = tf.lite.Interpreter(model_content=tflite_path.read_bytes())
    interp.allocate_tensors()
    input_details = interp.get_input_details()[0]
    output_details = interp.get_output_details()[0]
    outs = []
    for row in x:
        inp = np.asarray([row], dtype=input_details["dtype"])
        interp.set_tensor(input_details["index"], inp)
        interp.invoke()
        outs.append(interp.get_tensor(output_details["index"])[0])
    return np.asarray(outs)


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
    tflite_path = args.tflite or (ROOT / cfg.get("output_tflite", "artifacts/student/sms_bytecnn_int8.tflite"))
    keras_path = args.keras
    if keras_path is None:
        for candidate in (
            ROOT / "artifacts" / "student" / "sms_bytecnn_pruned.keras",
            ROOT / "artifacts" / "student" / "sms_bytecnn_fp32.keras",
            ROOT / cfg.get("input_model", "artifacts/student/sms_bytecnn_pruned.keras"),
        ):
            if candidate.exists():
                keras_path = candidate
                break

    if not tflite_path.exists():
        print(f"TFLite model not found: {tflite_path}", file=sys.stderr)
        return 1

    ops = list_tflite_ops(tflite_path)
    forbidden = sorted(
        op for op in ops if any(token.lower() in str(op).lower() for token in FORBIDDEN_OP_SUBSTRINGS)
    )

    agreement = None
    min_agreement = float(cfg.get("verify", {}).get("min_agreement_rate", 0.99))
    min_samples = int(cfg.get("verify", {}).get("min_samples", 1000))
    if keras_path and keras_path.exists() and args.test.exists():
        records = load_labeled_records(args.test)
        if len(records) < min_samples:
            # Top up from train if available (parity only — not for accuracy claims).
            train = ROOT / "data" / "processed" / "train.jsonl"
            if train.exists():
                extra = load_labeled_records(train)
                need = min_samples - len(records)
                records = list(records) + extra[:need]
        if records:
            model = tf.keras.models.load_model(keras_path)
            x, _ = records_to_xy(records)
            keras_pred = np.argmax(model.predict(x, verbose=0), axis=-1)
            tflite_out = run_tflite(tflite_path, x)
            if tflite_out.ndim == 1:
                tflite_pred = tflite_out.astype(int)
            else:
                tflite_pred = np.argmax(tflite_out, axis=-1)
            agreement = float(np.mean(keras_pred == tflite_pred))
            print(
                f"Keras/TFLite agreement={agreement:.4f} on {len(records)} samples "
                f"(min_samples={min_samples})"
            )

    status = "PASS"
    if forbidden:
        status = "FAIL"
    if agreement is not None and agreement < min_agreement:
        status = "FAIL"

    report = {
        "seed": args.seed,
        "tflite": str(tflite_path.relative_to(ROOT)),
        "keras": str(keras_path.relative_to(ROOT)) if keras_path and keras_path.exists() else None,
        "ops_sample": sorted(str(o) for o in list(ops)[:50]),
        "forbidden_ops": forbidden,
        "agreement_rate": agreement,
        "min_agreement_rate": min_agreement,
        "status": status,
        "bytes": tflite_path.stat().st_size,
    }
    write_json(ROOT / "reports" / "metrics" / "verify_tflite.json", report)
    print(f"TFLite verify: {tflite_path} ({tflite_path.stat().st_size} bytes) status={status}")
    if forbidden:
        print(f"Forbidden ops: {forbidden}", file=sys.stderr)
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
