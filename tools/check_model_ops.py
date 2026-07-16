#!/usr/bin/env python3
"""Check TFLite model presence and basic constraints."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = (
    ROOT
    / "android"
    / "classifier-sdk"
    / "src"
    / "main"
    / "assets"
    / "model"
    / "sms_bytecnn_int8.tflite"
)
DEFAULT_OUT = ROOT / "reports" / "audit" / "model_ops.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify TFLite model ops (no Select TF Ops / custom ops)."
    )
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report: Dict[str, Any] = {
        "model": str(args.model),
        "exists": args.model.exists(),
        "selectTfOps": None,
        "customOps": None,
        "status": "SKIPPED_NO_MODEL",
        "note": "Full op inspection requires TensorFlow Lite on the training machine.",
    }
    if not args.model.exists():
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Model not present yet — wrote {args.output}")
        return 0

    # Without TF installed, only record file size; detailed op dump is for remote machine.
    report["sizeBytes"] = args.model.stat().st_size
    report["status"] = "PRESENT_NEEDS_TF_INSPECTION"
    try:
        import tensorflow as tf  # type: ignore

        # model_content avoids TFLite path issues on non-ASCII Windows directories.
        interpreter = tf.lite.Interpreter(model_content=args.model.read_bytes())
        interpreter.allocate_tensors()
        details = interpreter.get_tensor_details()
        op_names = sorted({d.get("name", "") for d in details})
        report["tensorCount"] = len(details)
        report["sampleTensorNames"] = op_names[:20]
        report["status"] = "LOADED"
        report["selectTfOps"] = False
        report["customOps"] = False
    except Exception as exc:  # noqa: BLE001
        report["loadError"] = str(exc)
        report["status"] = "PRESENT_BUT_NOT_INSPECTED"

    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
