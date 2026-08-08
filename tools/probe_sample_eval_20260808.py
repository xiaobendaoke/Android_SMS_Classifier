#!/usr/bin/env python3
"""Probe the delivered INT8 TFLite model against the app's bundled eval samples."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import tensorflow as tf


MODEL = Path("/mnt/c/dev/Android_SMS_Classifier/training/artifacts/final_delivery_20260808/sms_bytecnn_int8.tflite")
SAMPLE = Path("/mnt/c/dev/Android_SMS_Classifier/android/app/src/main/assets/eval/sample_eval.json")
LABELS = ["TRANSACTION", "AD", "HARASS", "FRAUD"]


def encode(text: str, max_bytes: int = 512, head: int = 384, tail: int = 128) -> np.ndarray:
    raw = text.encode("utf-8")
    if len(raw) > max_bytes:
        raw = raw[:head] + raw[-tail:]
    ids = np.zeros(max_bytes, dtype=np.int32)
    limit = min(len(raw), max_bytes)
    for i in range(limit):
        ids[i] = raw[i] + 1
    return ids


def softmax(values):
    values = np.asarray(values, dtype=np.float64)
    shifted = values - values.max()
    exp = np.exp(shifted)
    return exp / exp.sum()


def sigmoid(value):
    return 1.0 / (1.0 + math.exp(-float(value)))


def main() -> int:
    interp = tf.lite.Interpreter(model_path=str(MODEL))
    interp.allocate_tensors()
    details = interp.get_input_details()[0]
    output_details = interp.get_output_details()[0]
    print(
        json.dumps(
            {
                "input_shape": [int(v) for v in details["shape"]],
                "input_dtype": str(details["dtype"]),
                "input_quantization": [float(v) for v in details["quantization"]],
                "output_shape": [int(v) for v in output_details["shape"]],
                "output_dtype": str(output_details["dtype"]),
                "output_quantization": [float(v) for v in output_details["quantization"]],
            },
            ensure_ascii=False,
        )
    )
    samples = json.loads(SAMPLE.read_text(encoding="utf-8"))["samples"]
    rows = []
    for sample in samples:
        ids = encode(str(sample.get("body", "")))
        row = {
            "id": sample.get("id"),
            "expected": sample.get("expectedCategory"),
            "predicted": None,
            "probabilities": None,
            "protection": None,
            "error": None,
            "feed_dtype": None,
        }
        for feed_dtype, array in (
            ("int32", ids.astype(np.int32).reshape(1, -1)),
            ("int8", (ids.astype(np.int8)).reshape(1, -1)),
            ("float32", ids.astype(np.float32).reshape(1, -1)),
        ):
            try:
                interp.set_tensor(details["index"], array)
                interp.invoke()
                raw = interp.get_tensor(output_details["index"])[0]
                if output_details["dtype"] == np.int8:
                    scale, zero = output_details["quantization"]
                    raw = (raw.astype(np.float64) - zero) * scale
                probs = softmax(raw[:4])
                row["feed_dtype"] = feed_dtype
                row["predicted"] = LABELS[int(np.argmax(probs))]
                row["probabilities"] = {
                    label: round(float(prob), 4) for label, prob in zip(LABELS, probs)
                }
                row["protection"] = round(float(sigmoid(raw[4])), 4) if len(raw) > 4 else None
                break
            except Exception as exc:  # pragma: no cover - report the first failure per dtype
                row["error"] = f"{feed_dtype}: {type(exc).__name__}"
        rows.append(row)
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
