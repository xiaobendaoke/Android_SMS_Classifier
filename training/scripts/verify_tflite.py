#!/usr/bin/env python3
"""Verify Keras vs TFLite agreement and inspect TFLite ops."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import yaml

SEED = 42
SETUP_DOC = "docs/异机测试环境安装清单.md"

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "configs" / "quantization.yaml"


def resolve_path(path: Path) -> Path:
    """Resolve CLI paths against CWD first, then training ROOT."""
    path = Path(path)
    if path.is_absolute():
        return path.resolve()
    cwd_candidate = (Path.cwd() / path).resolve()
    if cwd_candidate.exists():
        return cwd_candidate
    return (ROOT / path).resolve()


def display_path(path: Path) -> str:
    resolved = path.resolve() if path.is_absolute() else resolve_path(path)
    try:
        return str(resolved.relative_to(ROOT)).replace(chr(92), "/")
    except ValueError:
        return str(resolved).replace(chr(92), "/")


sys.path.insert(0, str(ROOT))
from src.metrics import summarize_metrics  # noqa: E402
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
    parser.add_argument(
        "--quant-report",
        type=Path,
        default=ROOT / "reports" / "metrics" / "quantize.json",
        help="Quantization provenance report (older artifacts without one remain verifiable).",
    )
    return parser


def inspect_tflite(tflite_path: Path) -> Tuple[Set[str], Dict[str, Any]]:
    import tensorflow as tf

    interp = tf.lite.Interpreter(model_content=tflite_path.read_bytes())
    interp.allocate_tensors()
    ops: Set[str] = set()
    try:
        ops = {str(item.get("op_name", "")) for item in interp._get_ops_details()}  # noqa: SLF001
    except Exception:
        pass
    details = interp.get_tensor_details()
    float_tensors = [
        str(d.get("name", ""))
        for d in details
        if np.dtype(d["dtype"]).kind == "f"
    ]
    input_detail = interp.get_input_details()[0]
    output_detail = interp.get_output_details()[0]
    metadata = {
        "input_dtype": np.dtype(input_detail["dtype"]).name,
        "output_dtype": np.dtype(output_detail["dtype"]).name,
        "float_tensor_count": len(float_tensors),
        "float_tensors_sample": float_tensors[:20],
    }
    return ops, metadata


def list_tflite_ops(tflite_path: Path) -> Set[str]:
    """Compatibility wrapper for callers that only need ops."""
    return inspect_tflite(tflite_path)[0]


def validate_quant_report(
    report_path: Path, tflite_path: Path
) -> Tuple[Optional[Dict[str, Any]], List[str], List[str]]:
    """Validate provenance while allowing legacy artifacts without a report."""
    if not report_path.exists():
        return None, [], ["quantization report missing (legacy compatibility mode)"]
    with report_path.open(encoding="utf-8") as fh:
        report = json.load(fh)
    errors: List[str] = []
    warnings: List[str] = []
    mode = report.get("quantization")
    if mode not in {"full_integer_int8", "hybrid_fallback"}:
        errors.append("quantization report has unknown/missing quantization mode")
    expected_sha = report.get("model_sha256") or report.get("sha256")
    actual_sha = hashlib.sha256(tflite_path.read_bytes()).hexdigest()
    if not expected_sha:
        errors.append("quantization report missing model SHA256")
    elif expected_sha != actual_sha:
        errors.append("quantization report model SHA256 does not match TFLite")
    representative = report.get("representative")
    if not isinstance(representative, dict):
        errors.append("quantization report missing representative metadata")
    else:
        for key in ("sha256", "samples", "distribution"):
            if key not in representative:
                errors.append(f"representative metadata missing {key}")
    if "acceptance_eligible" not in report:
        warnings.append("legacy report missing acceptance_eligible")
    if mode != "full_integer_int8" and report.get("acceptance_eligible"):
        errors.append("hybrid model cannot be acceptance_eligible")
    if report.get("status") == "FAIL" or report.get("output_written") is False:
        errors.append("quantization report marks this artifact as failed/not written")
    return report, errors, warnings


def _metric(metrics: Dict[str, Any], name: str) -> Optional[float]:
    locations = {
        "macro_f1": ("macro_f1", None, None),
        "harass_f1": ("per_class", "HARASS", "f1"),
        "fraud_recall": ("per_class", "FRAUD", "recall"),
        "transaction_recall": ("per_class", "TRANSACTION", "recall"),
    }
    root, label, field = locations[name]
    try:
        value = metrics[root] if label is None else metrics[root][label][field]
    except (KeyError, TypeError):
        return None
    return float(value)


def metric_gate_errors(
    baseline: Optional[Dict[str, Any]],
    candidate: Optional[Dict[str, Any]],
    verify_cfg: Dict[str, Any],
    drop_gates: Dict[str, Any],
) -> Tuple[List[str], Dict[str, Any]]:
    """Apply acceptance targets and quantization-drop gates."""
    errors: List[str] = []
    observed: Dict[str, Any] = {"candidate": {}, "drops": {}}
    targets = verify_cfg.get("acceptance_targets", {})
    recognized_drops = {
        "macro_f1_drop",
        "harass_f1_drop",
        "fraud_recall_drop",
        "transaction_recall_drop",
    }
    if not targets and not (recognized_drops & set(drop_gates)):
        return [], observed
    if baseline is None or candidate is None:
        return ["acceptance metric gates require Keras baseline and TFLite candidate metrics"], {}
    for name, required in targets.items():
        actual = _metric(candidate, name)
        observed["candidate"][name] = actual
        if actual is None:
            errors.append(f"missing candidate metric: {name}")
        elif actual < float(required):
            errors.append(f"{name} {actual:.6f} < {float(required):.6f}")

    gate_to_metric = {
        "macro_f1_drop": "macro_f1",
        "harass_f1_drop": "harass_f1",
        "fraud_recall_drop": "fraud_recall",
        "transaction_recall_drop": "transaction_recall",
    }
    for gate, name in gate_to_metric.items():
        if gate not in drop_gates:
            continue
        before = _metric(baseline, name)
        after = _metric(candidate, name)
        if before is None or after is None:
            errors.append(f"missing baseline/candidate metric for {gate}")
            continue
        drop = before - after
        observed["drops"][gate] = drop
        if drop > float(drop_gates[gate]):
            errors.append(f"{gate} {drop:.6f} > {float(drop_gates[gate]):.6f}")
    return errors, observed


def infer_max_bytes(model: Any) -> int:
    shape = model.input_shape
    if isinstance(shape, list):
        if len(shape) != 1:
            raise ValueError(f"Only single-input models are supported, got {shape!r}")
        shape = shape[0]
    if hasattr(shape, "as_list"):
        shape = shape.as_list()
    if not isinstance(shape, (tuple, list)) or len(shape) < 2 or shape[-1] is None:
        raise ValueError(f"Cannot infer encoded input length from input_shape={shape!r}")
    return int(shape[-1])


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
    tflite_path = resolve_path(
        args.tflite
        or (ROOT / cfg.get("output_tflite", "artifacts/student/sms_bytecnn_int8.tflite"))
    )
    keras_path = resolve_path(args.keras) if args.keras is not None else None
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

    ops, tensor_metadata = inspect_tflite(tflite_path)
    forbidden = sorted(
        op for op in ops if any(token.lower() in str(op).lower() for token in FORBIDDEN_OP_SUBSTRINGS)
    )

    quant_report_path = resolve_path(args.quant_report)
    test_path = resolve_path(args.test)
    quant_report, metadata_errors, metadata_warnings = validate_quant_report(
        quant_report_path, tflite_path
    )
    agreement = None
    baseline_summary = None
    summary = None
    evaluated_samples = 0
    min_agreement = float(cfg.get("verify", {}).get("min_agreement_rate", 0.99))
    min_samples = int(cfg.get("verify", {}).get("min_samples", 1000))
    if keras_path and keras_path.exists() and test_path.exists():
        records = load_labeled_records(test_path)
        labeled_evaluation_count = len(records)
        if len(records) < min_samples:
            # Top up from train if available (parity only — not for accuracy claims).
            train = ROOT / "data" / "processed" / "train.jsonl"
            if train.exists():
                extra = load_labeled_records(train)
                need = min_samples - len(records)
                records = list(records) + extra[:need]
        if records:
            model = tf.keras.models.load_model(keras_path)
            x, y = records_to_xy(records, max_bytes=infer_max_bytes(model))
            keras_pred = np.argmax(model.predict(x, verbose=0), axis=-1)
            tflite_out = run_tflite(tflite_path, x)
            if tflite_out.ndim == 1:
                tflite_pred = tflite_out.astype(int)
            else:
                tflite_pred = np.argmax(tflite_out, axis=-1)
            agreement = float(np.mean(keras_pred == tflite_pred))
            if labeled_evaluation_count:
                true_labels = [
                    LABEL_ORDER[int(i)] for i in y[:labeled_evaluation_count]
                ]
                predicted_labels = [
                    LABEL_ORDER[int(i)] for i in tflite_pred[:labeled_evaluation_count]
                ]
                baseline_labels = [
                    LABEL_ORDER[int(i)] for i in keras_pred[:labeled_evaluation_count]
                ]
                baseline_summary = summarize_metrics(
                    true_labels, baseline_labels, LABEL_ORDER
                )
                summary = summarize_metrics(true_labels, predicted_labels, LABEL_ORDER)
                evaluated_samples = labeled_evaluation_count
            print(
                f"Keras/TFLite agreement={agreement:.4f} on {len(records)} samples "
                f"(min_samples={min_samples})"
            )

    status = "PASS"
    if forbidden:
        status = "FAIL"
    if agreement is not None and agreement < min_agreement:
        status = "FAIL"
    if metadata_errors:
        status = "FAIL"

    threshold_errors, gate_metrics = metric_gate_errors(
        baseline_summary,
        summary,
        cfg.get("verify", {}),
        cfg.get("qat_triggers", {}),
    )
    if threshold_errors:
        status = "FAIL"

    reported_mode = quant_report.get("quantization") if quant_report else None
    inferred_full_int8 = (
        tensor_metadata["output_dtype"] == "int8"
        and tensor_metadata["float_tensor_count"] == 0
        and not forbidden
    )
    if reported_mode == "full_integer_int8" and not inferred_full_int8:
        metadata_errors.append("reported Full-INT8 conflicts with tensor/op inspection")
        status = "FAIL"
    acceptance_eligible = bool(
        status == "PASS"
        and quant_report
        and quant_report.get("acceptance_eligible")
        and reported_mode == "full_integer_int8"
        and inferred_full_int8
    )

    report = {
        "seed": args.seed,
        "tflite": display_path(tflite_path),
        "keras": display_path(keras_path) if keras_path and keras_path.exists() else None,
        "ops": sorted(str(o) for o in ops),
        "forbidden_ops": forbidden,
        "tensor_metadata": tensor_metadata,
        "quantization_mode": reported_mode,
        "inferred_full_integer_int8": inferred_full_int8,
        "quantization_metadata_errors": metadata_errors,
        "quantization_metadata_warnings": metadata_warnings,
        "agreement_rate": agreement,
        "min_agreement_rate": min_agreement,
        "evaluated_samples": evaluated_samples,
        "baseline_metrics": baseline_summary,
        "candidate_metrics": summary,
        "per_class": summary.get("per_class") if summary else None,
        "macro_f1": summary.get("macro_f1") if summary else None,
        "acceptance_targets": cfg.get("verify", {}).get("acceptance_targets", {}),
        "drop_gates": cfg.get("qat_triggers", {}),
        "gate_metrics": gate_metrics,
        "threshold_errors": threshold_errors,
        "acceptance_eligible": acceptance_eligible,
        "status": status,
        "bytes": tflite_path.stat().st_size,
    }
    write_json(ROOT / "reports" / "metrics" / "verify_tflite.json", report)
    print(f"TFLite verify: {tflite_path} ({tflite_path.stat().st_size} bytes) status={status}")
    if forbidden:
        print(f"Forbidden ops: {forbidden}", file=sys.stderr)
    for error in metadata_errors + threshold_errors:
        print(f"Verification error: {error}", file=sys.stderr)
    for warning in metadata_warnings:
        print(f"Verification warning: {warning}", file=sys.stderr)
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
