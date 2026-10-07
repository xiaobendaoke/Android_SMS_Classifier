#!/usr/bin/env python3
"""Strict Full-INT8 conversion with explicit, auditable QAT/hybrid policy."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import yaml

SEED = 42
SETUP_DOC = "docs/异机测试环境安装清单.md"

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "configs" / "quantization.yaml"
DEFAULT_REPORT = ROOT / "reports" / "metrics" / "quantize.json"

sys.path.insert(0, str(ROOT))
from src.byte_encoder import encode_text  # noqa: E402
from src.normalize import normalize_text  # noqa: E402
from src.metrics import summarize_metrics  # noqa: E402
from src.schema import LABEL_ORDER, SmsRecord, load_jsonl  # noqa: E402
from src.train_utils import set_seed, student_predictions, write_json  # noqa: E402


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
        "--profile",
        choices=["formal", "development"],
        default="formal",
        help="formal is acceptance-oriented and fails closed (default).",
    )
    parser.add_argument(
        "--allow-hybrid",
        action="store_true",
        help="Explicitly permit a hybrid fallback; the report remains acceptance-ineligible.",
    )
    parser.add_argument("--baseline-metrics", type=Path, help="Optional baseline metrics JSON.")
    parser.add_argument("--candidate-metrics", type=Path, help="Optional PTQ/candidate metrics JSON.")
    parser.add_argument(
        "--input-model",
        type=Path,
        help="Override input_model from config (for example, quantize the dense student directly).",
    )
    parser.add_argument(
        "--output-tflite",
        type=Path,
        help="Override output_tflite from config (for example, keep Dense and Pruned artifacts).",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
        help="Quantization report JSON path.",
    )
    parser.add_argument(
        "--mode",
        choices=["ptq", "qat"],
        default=None,
        help="Override config mode.",
    )
    return parser


def _nested_metric(metrics: Mapping[str, Any], label: str, metric: str) -> Optional[float]:
    value = metrics.get("per_class", {}).get(label, {}).get(metric)
    if value is None:
        value = metrics.get(f"{label.lower()}_{metric}")
    return float(value) if value is not None else None


def qat_trigger_reasons(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    triggers: Mapping[str, Any],
) -> List[str]:
    """Return deterministic reasons why candidate degradation requires QAT."""
    checks: Sequence[Tuple[str, Optional[float], Optional[float], str]] = (
        (
            "transaction_recall_drop",
            _nested_metric(baseline, "TRANSACTION", "recall"),
            _nested_metric(candidate, "TRANSACTION", "recall"),
            "TRANSACTION recall",
        ),
        (
            "macro_f1_drop",
            float(baseline["macro_f1"]) if "macro_f1" in baseline else None,
            float(candidate["macro_f1"]) if "macro_f1" in candidate else None,
            "macro F1",
        ),
        (
            "fraud_recall_drop",
            _nested_metric(baseline, "FRAUD", "recall"),
            _nested_metric(candidate, "FRAUD", "recall"),
            "FRAUD recall",
        ),
        (
            "harass_f1_drop",
            _nested_metric(baseline, "HARASS", "f1"),
            _nested_metric(candidate, "HARASS", "f1"),
            "HARASS F1",
        ),
    )
    reasons = []
    for key, before, after, display in checks:
        if key in triggers and before is not None and after is not None:
            drop = before - after
            if drop > float(triggers[key]):
                reasons.append(f"{display} drop {drop:.6f} > {float(triggers[key]):.6f}")
    mismatch = candidate.get("keras_tflite_mismatch_rate")
    if mismatch is not None and "keras_tflite_mismatch_rate" in triggers:
        if float(mismatch) > float(triggers["keras_tflite_mismatch_rate"]):
            reasons.append(
                "Keras/TFLite mismatch "
                f"{float(mismatch):.6f} > {float(triggers['keras_tflite_mismatch_rate']):.6f}"
            )
    return reasons


def formal_post_qat_failed(profile: str, qat_applied: bool, reasons: Sequence[str]) -> bool:
    """Formal conversion fails closed when QAT cannot clear its trigger gates."""
    return profile == "formal" and qat_applied and bool(reasons)


def strict_failure_action(qat_applied: bool, allow_hybrid: bool) -> str:
    """Choose the next action after a strict conversion failure."""
    if not qat_applied:
        return "qat"
    return "hybrid" if allow_hybrid else "fail"


def load_metrics(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if path is None:
        return None
    with path.open(encoding="utf-8") as fh:
        value = json.load(fh)
    if not isinstance(value, dict):
        raise ValueError(f"Metrics must be a JSON object: {path}")
    return value


def display_path(path: Path) -> str:
    try:
        path = path.relative_to(ROOT)
    except ValueError:
        pass
    return str(path).replace("\\", "/")


def representative_metadata(manifest: Path, records: Sequence[SmsRecord]) -> Dict[str, Any]:
    raw = manifest.read_bytes()
    lengths = Counter(
        "short" if len(r.text.encode("utf-8")) <= 80 else
        "medium" if len(r.text.encode("utf-8")) <= 200 else "long"
        for r in records
    )
    return {
        "manifest": display_path(manifest),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "samples": len(records),
        "distribution": {
            "label": dict(sorted(Counter(r.label for r in records).items())),
            "source": dict(sorted(Counter(r.source for r in records).items())),
            "length_bucket": dict(sorted(lengths.items())),
        },
    }


def representative_dataset(
    records: Sequence[SmsRecord],
    max_bytes: int = 512,
) -> Iterator[List[np.ndarray]]:
    for record in records:
        ids = encode_text(normalize_text(record.text), length=max_bytes)
        yield [np.asarray([ids], dtype=np.int32)]


def convert_model(tf: Any, model: Any, records: Sequence[SmsRecord], max_bytes: int, strict: bool) -> bytes:
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = lambda: representative_dataset(records, max_bytes=max_bytes)
    if strict:
        converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
        # TF>=2.20 rejects declaring int32 as inference_input_type for INT8 models.
        # Embedding graphs still expose int32 inputs at runtime (Android IntArray OK).
        converter.inference_input_type = tf.float32
        converter.inference_output_type = tf.int8
    return converter.convert()


def convert_with_policy(
    tf: Any,
    model: Any,
    records: Sequence[SmsRecord],
    max_bytes: int,
    allow_hybrid: bool,
) -> Tuple[bytes, str]:
    try:
        return convert_model(tf, model, records, max_bytes, strict=True), "full_integer_int8"
    except Exception as exc:
        if not allow_hybrid:
            raise RuntimeError(f"Strict Full-INT8 conversion failed: {exc}") from exc
        print(
            f"Strict Full-INT8 failed ({exc}); --allow-hybrid permits non-acceptance fallback.",
            file=sys.stderr,
        )
        return convert_model(tf, model, records, max_bytes, strict=False), "hybrid_fallback"


def metrics_from_predictions(
    y: np.ndarray,
    reference_pred: np.ndarray,
    tflite_pred: np.ndarray,
    candidate_keras_pred: Optional[np.ndarray] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    labels = [LABEL_ORDER[int(i)] for i in y]
    keras_labels = [LABEL_ORDER[int(i)] for i in reference_pred]
    tflite_labels = [LABEL_ORDER[int(i)] for i in tflite_pred]
    baseline = summarize_metrics(labels, keras_labels, LABEL_ORDER)
    candidate = summarize_metrics(labels, tflite_labels, LABEL_ORDER)
    agreement_reference = (
        np.asarray(candidate_keras_pred)
        if candidate_keras_pred is not None
        else np.asarray(reference_pred)
    )
    mismatch = float(np.mean(agreement_reference != np.asarray(tflite_pred)))
    candidate["keras_tflite_mismatch_rate"] = mismatch
    candidate["candidate_keras_tflite_agreement_rate"] = 1.0 - mismatch
    return baseline, candidate


def validation_metrics(
    tf: Any,
    reference_model: Any,
    candidate_model: Any,
    tflite_model: bytes,
    records: Sequence[SmsRecord],
    max_bytes: int,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    from src.train_utils import records_to_xy

    x, y = records_to_xy(records, max_bytes=max_bytes)
    reference_logits = reference_model.predict(x, verbose=0)
    reference_pred = student_predictions(
        reference_logits,
        transaction_threshold=(
            0.5 if reference_logits.shape[-1] > len(LABEL_ORDER) else None
        ),
    )
    candidate_keras_pred = (
        reference_pred
        if candidate_model is reference_model
        else student_predictions(
            candidate_model.predict(x, verbose=0),
            transaction_threshold=(
                0.5
                if int(candidate_model.output_shape[-1]) > len(LABEL_ORDER)
                else None
            ),
        )
    )
    interp = tf.lite.Interpreter(model_content=tflite_model)
    interp.allocate_tensors()
    inp = interp.get_input_details()[0]
    out = interp.get_output_details()[0]
    tflite_pred = []
    for row in x:
        interp.set_tensor(inp["index"], np.asarray([row], dtype=inp["dtype"]))
        interp.invoke()
        result = interp.get_tensor(out["index"])[0]
        if np.dtype(out["dtype"]).kind not in {"f", "c"}:
            scale, zero_point = out.get("quantization", (0.0, 0))
            if scale:
                result = (result.astype(np.float32) - float(zero_point)) * float(scale)
        predicted = student_predictions(
            np.asarray([result]),
            transaction_threshold=(
                0.5 if np.asarray(result).shape[-1] > len(LABEL_ORDER) else None
            ),
        )[0]
        tflite_pred.append(int(predicted))
    return metrics_from_predictions(
        y,
        reference_pred,
        np.asarray(tflite_pred),
        candidate_keras_pred=candidate_keras_pred,
    )


def infer_max_bytes(model: Any) -> int:
    """Infer the fixed encoded input length from the actual loaded Keras model."""
    shape = model.input_shape
    if isinstance(shape, list):
        if len(shape) != 1:
            raise ValueError(f"Only single-input models are supported, got {shape!r}")
        shape = shape[0]
    if hasattr(shape, "as_list"):
        shape = shape.as_list()
    if not isinstance(shape, (tuple, list)) or len(shape) < 2:
        raise ValueError(f"Cannot infer encoded input length from input_shape={shape!r}")
    length = shape[-1]
    if length is None or int(length) <= 0:
        raise ValueError(f"Model requires a fixed final input dimension, got {shape!r}")
    return int(length)


def _tfmot_keras() -> Any:
    """Keras namespace that TFMOT's isinstance checks recognize (tf_keras / compat)."""
    try:
        from tensorflow_model_optimization.python.core.keras.compat import (  # type: ignore
            keras as mot_keras,
        )

        return mot_keras
    except Exception:  # noqa: BLE001
        import tf_keras as mot_keras  # type: ignore

        return mot_keras


def clone_bytecnn_for_tfmot(source_model: Any, max_bytes: int) -> Any:
    """
    Rebuild Byte TextCNN as a TFMOT-compatible Functional model and copy weights.

    Keras 3 standalone models fail TFMOT's Sequential/Functional isinstance check
    even when they are Functional; cloning through TFMOT's keras compat fixes QAT.
    """
    mot_keras = _tfmot_keras()
    layers = mot_keras.layers

    emb = source_model.get_layer("byte_embedding")
    emb_cfg = emb.get_config()
    vocab_size = int(emb_cfg.get("input_dim") or emb_cfg.get("vocabulary_size"))
    embedding_dim = int(emb_cfg["output_dim"])

    conv_layers = [
        layer
        for layer in source_model.layers
        if layer.name.startswith("conv1d_k")
    ]
    if not conv_layers:
        raise ValueError("Cannot clone Byte TextCNN for QAT: no conv1d_k* layers found")

    inputs = mot_keras.Input(shape=(max_bytes,), dtype="int32", name="byte_input")
    x = layers.Embedding(
        input_dim=vocab_size,
        output_dim=embedding_dim,
        name="byte_embedding",
    )(inputs)
    branch_outputs = []
    for layer in conv_layers:
        cfg = layer.get_config()
        kernel_size = int(cfg["kernel_size"][0] if isinstance(cfg["kernel_size"], (list, tuple)) else cfg["kernel_size"])
        filters = int(cfg["filters"])
        branch = layers.Conv1D(
            filters=filters,
            kernel_size=kernel_size,
            activation=cfg.get("activation", "relu"),
            padding=cfg.get("padding", "same"),
            name=layer.name,
        )(x)
        # model_student.py naming: conv1d_k{k}_{idx} -> gmp_k{k}_{idx}
        suffix = layer.name[len("conv1d_") :]
        branch_outputs.append(layers.GlobalMaxPooling1D(name=f"gmp_{suffix}")(branch))

    if len(branch_outputs) > 1:
        x = layers.Concatenate(name="concat_branches")(branch_outputs)
    else:
        x = branch_outputs[0]

    pooled = x
    dense_cfg = source_model.get_layer("dense_hidden").get_config()
    drop_cfg = source_model.get_layer("dropout").get_config()
    x = layers.Dense(
        int(dense_cfg["units"]),
        activation=dense_cfg.get("activation", "relu"),
        name="dense_hidden",
    )(x)
    x = layers.Dropout(float(drop_cfg.get("rate", 0.2)), name="dropout")(x)
    dual_head = int(source_model.output_shape[-1]) > len(LABEL_ORDER)
    if dual_head:
        class_cfg = source_model.get_layer("class_logits").get_config()
        protection_cfg = source_model.get_layer(
            "transaction_protection_logit"
        ).get_config()
        class_logits = layers.Dense(
            int(class_cfg["units"]),
            activation=class_cfg.get("activation", "linear"),
            name="class_logits",
        )(x)
        protection_features = pooled
        try:
            protection_hidden_cfg = source_model.get_layer(
                "transaction_protection_hidden"
            ).get_config()
            protection_features = layers.Dense(
                int(protection_hidden_cfg["units"]),
                activation=protection_hidden_cfg.get("activation", "relu"),
                name="transaction_protection_hidden",
            )(protection_features)
        except ValueError:
            pass
        protection_logit = layers.Dense(
            int(protection_cfg["units"]),
            activation=protection_cfg.get("activation", "linear"),
            name="transaction_protection_logit",
        )(protection_features)
        outputs = layers.Concatenate(name="logits")(
            [class_logits, protection_logit]
        )
    else:
        logits_cfg = source_model.get_layer("logits").get_config()
        outputs = layers.Dense(
            int(logits_cfg["units"]),
            activation=logits_cfg.get("activation", "linear"),
            name="logits",
        )(x)
    cloned = mot_keras.Model(inputs=inputs, outputs=outputs, name="byte_textcnn_tfmot")

    # Copy weights by layer name (skip Input).
    for layer in cloned.layers:
        try:
            src = source_model.get_layer(layer.name)
        except ValueError:
            continue
        src_weights = src.get_weights()
        if not src_weights:
            continue
        layer.set_weights(src_weights)
    return cloned


def apply_qat(tf: Any, model: Any, train_path: Path, max_bytes: int, cfg: Mapping[str, Any]) -> Any:
    import tensorflow_model_optimization as tfmot
    from src.train_utils import balanced_class_weights, load_labeled_records, records_to_xy

    if not train_path.exists():
        raise FileNotFoundError(f"QAT train set missing: {train_path}")
    # Keras 3 models need a TFMOT-compat Functional clone before quantize_apply.
    try:
        qat_base = clone_bytecnn_for_tfmot(model, max_bytes)
        print("QAT base: cloned Functional model for TFMOT/Keras3 compatibility")
    except Exception as clone_exc:  # noqa: BLE001
        print(f"QAT clone fallback to source model ({clone_exc})")
        qat_base = model
    # quantize_model() wraps int32 Input with FakeQuant and crashes. Annotate only
    # float-weight layers so byte IDs stay unquantized indices into Embedding.
    annotate = tfmot.quantization.keras.quantize_annotate_layer
    mot_keras = _tfmot_keras()

    def _annotate(layer: Any) -> Any:
        if isinstance(
            layer,
            (
                mot_keras.layers.Conv1D,
                mot_keras.layers.Dense,
                mot_keras.layers.Embedding,
            ),
        ):
            return annotate(layer)
        return layer

    annotated = mot_keras.models.clone_model(qat_base, clone_function=_annotate)
    with tfmot.quantization.keras.quantize_scope():
        q_aware = tfmot.quantization.keras.quantize_apply(annotated)
    dual_head = int(q_aware.output_shape[-1]) > len(LABEL_ORDER)

    def dual_head_loss(y_true: Any, y_pred: Any) -> Any:
        labels = tf.cast(tf.reshape(y_true, [-1]), tf.int32)
        class_loss = tf.keras.losses.sparse_categorical_crossentropy(
            labels,
            y_pred[:, : len(LABEL_ORDER)],
            from_logits=True,
        )
        transaction_targets = tf.cast(
            tf.equal(labels, LABEL_ORDER.index("TRANSACTION")),
            tf.float32,
        )
        protection_loss = tf.nn.weighted_cross_entropy_with_logits(
            labels=transaction_targets,
            logits=y_pred[:, len(LABEL_ORDER)],
            pos_weight=1.5,
        )
        return class_loss + 0.35 * protection_loss

    q_aware.compile(
        optimizer="adam",
        loss=(
            dual_head_loss
            if dual_head
            else tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True)
        ),
        metrics=["accuracy"],
    )
    x, y = records_to_xy(load_labeled_records(train_path), max_bytes=max_bytes)
    weights = balanced_class_weights(y, len(LABEL_ORDER))
    class_weight = {idx: float(weight) for idx, weight in enumerate(weights)}
    qat_cfg = cfg.get("qat", {})
    q_aware.fit(
        x,
        y,
        epochs=int(qat_cfg.get("epochs", 2)),
        batch_size=int(qat_cfg.get("batch_size", 64)),
        verbose=1,
        class_weight=class_weight,
    )
    return q_aware


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.config.exists():
        print(f"Config missing: {args.config}", file=sys.stderr)
        return 1

    with args.config.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    set_seed(int(cfg.get("seed", args.seed)))
    mode = args.mode or cfg.get("mode", "ptq")
    input_model = args.input_model or (
        ROOT / cfg.get("input_model", "artifacts/student/sms_bytecnn_pruned.keras")
    )
    # Allow FP32 student if prune skipped.
    if args.input_model is None and not input_model.exists():
        alt = ROOT / "artifacts" / "student" / "sms_bytecnn_fp32.keras"
        if alt.exists():
            input_model = alt
            print(f"Pruned model missing; using {alt}")
    output_tflite = args.output_tflite or (
        ROOT / cfg.get("output_tflite", "artifacts/student/sms_bytecnn_int8.tflite")
    )
    rep_manifest = ROOT / cfg.get("representative", {}).get(
        "manifest", "data/processed/representative.jsonl"
    )
    num_samples = int(cfg.get("representative", {}).get("num_samples", 500))

    if not input_model.exists():
        print(f"Input Keras model missing: {input_model}", file=sys.stderr)
        return 1
    if not rep_manifest.exists():
        if args.profile == "formal":
            print(
                f"Formal quantization requires representative manifest: {rep_manifest}. "
                "Generate it with generate_representative_manifest.py.",
                file=sys.stderr,
            )
            return 1
        train_fallback = ROOT / "data" / "processed" / "train.jsonl"
        if not train_fallback.exists():
            print(f"Representative manifest missing: {rep_manifest}", file=sys.stderr)
            return 1
        print(f"Development-only representative fallback: {train_fallback}", file=sys.stderr)
        rep_manifest = train_fallback

    loaded_representative = load_jsonl(rep_manifest)
    if args.profile == "formal":
        if any(r.split != "train" for r in loaded_representative):
            print("Formal representative manifest must contain train records only.", file=sys.stderr)
            return 1
        if any(r.label not in LABEL_ORDER for r in loaded_representative):
            print("Formal representative manifest contains a non-model label.", file=sys.stderr)
            return 1
    rep_records = [r for r in loaded_representative if r.label in LABEL_ORDER][:num_samples]
    if not rep_records:
        print(f"Representative manifest has no usable records: {rep_manifest}", file=sys.stderr)
        return 1
    rep_info = representative_metadata(rep_manifest, rep_records)

    err = check_tensorflow()
    if err:
        print(err, file=sys.stderr)
        return 2

    import tensorflow as tf

    reference_model = tf.keras.models.load_model(input_model)
    try:
        max_bytes = infer_max_bytes(reference_model)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    validation_path = ROOT / cfg.get("validation", {}).get(
        "manifest", "data/processed/validation.jsonl"
    )
    validation_records = (
        [r for r in load_jsonl(validation_path) if r.label in LABEL_ORDER]
        if validation_path.exists()
        else []
    )
    qat_reasons: List[str] = []
    baseline = load_metrics(args.baseline_metrics)
    supplied_candidate = load_metrics(args.candidate_metrics)
    if baseline is not None and supplied_candidate is not None:
        qat_reasons = qat_trigger_reasons(
            baseline, supplied_candidate, cfg.get("qat_triggers", {})
        )
    initial_qat_reasons = list(qat_reasons)
    pre_qat_baseline = baseline
    pre_qat_candidate = supplied_candidate
    post_qat_baseline: Optional[Dict[str, Any]] = None
    post_qat_candidate: Optional[Dict[str, Any]] = None
    model = reference_model
    qat_applied = mode == "qat" or bool(qat_reasons)
    if qat_applied:
        try:
            model = apply_qat(
                tf,
                reference_model,
                ROOT / "data" / "processed" / "train.jsonl",
                max_bytes,
                cfg,
            )
            mode = "qat"
            print("QAT applied.")
        except Exception as exc:  # noqa: BLE001
            print(f"QAT failed; PTQ fallback is forbidden: {exc}", file=sys.stderr)
            return 1

    if qat_applied:
        try:
            tflite_model, quant_mode = convert_with_policy(
                tf, model, rep_records, max_bytes, args.allow_hybrid
            )
        except Exception as exc:  # noqa: BLE001
            print(f"QAT strict conversion failed: {exc}", file=sys.stderr)
            return 1
    else:
        try:
            tflite_model = convert_model(
                tf, reference_model, rep_records, max_bytes, strict=True
            )
            quant_mode = "full_integer_int8"
        except Exception as exc:  # noqa: BLE001
            conversion_reason = f"Strict Full-INT8 conversion failed: {exc}"
            initial_qat_reasons.append(conversion_reason)
            print(conversion_reason, file=sys.stderr)
            if strict_failure_action(qat_applied=False, allow_hybrid=args.allow_hybrid) != "qat":
                return 1
            try:
                model = apply_qat(
                    tf,
                    reference_model,
                    ROOT / "data" / "processed" / "train.jsonl",
                    max_bytes,
                    cfg,
                )
                mode = "qat"
                qat_applied = True
                print("Strict PTQ conversion failed; QAT applied.")
                tflite_model, quant_mode = convert_with_policy(
                    tf, model, rep_records, max_bytes, args.allow_hybrid
                )
            except Exception as qat_exc:  # noqa: BLE001
                print(
                    f"Strict PTQ conversion triggered QAT, but QAT failed: {qat_exc}",
                    file=sys.stderr,
                )
                return 1

    if validation_records:
        auto_baseline, auto_candidate = validation_metrics(
            tf,
            reference_model,
            model,
            tflite_model,
            validation_records,
            max_bytes,
        )
        if qat_applied:
            post_qat_baseline, post_qat_candidate = auto_baseline, auto_candidate
        else:
            pre_qat_baseline, pre_qat_candidate = auto_baseline, auto_candidate
        qat_reasons = qat_trigger_reasons(
            auto_baseline, auto_candidate, cfg.get("qat_triggers", {})
        )
        if not qat_applied:
            initial_qat_reasons = list(qat_reasons)

    if qat_reasons and not qat_applied:
        try:
            model = apply_qat(
                tf,
                reference_model,
                ROOT / "data" / "processed" / "train.jsonl",
                max_bytes,
                cfg,
            )
            mode = "qat"
            qat_applied = True
            tflite_model, quant_mode = convert_with_policy(
                tf, model, rep_records, max_bytes, args.allow_hybrid
            )
            if not validation_records:
                raise RuntimeError("Triggered QAT requires validation records for post-QAT verification")
            post_qat_baseline, post_qat_candidate = validation_metrics(
                tf,
                reference_model,
                model,
                tflite_model,
                validation_records,
                max_bytes,
            )
            qat_reasons = qat_trigger_reasons(
                post_qat_baseline,
                post_qat_candidate,
                cfg.get("qat_triggers", {}),
            )
        except Exception as exc:  # noqa: BLE001
            print(f"Triggered QAT failed; PTQ fallback is forbidden: {exc}", file=sys.stderr)
            return 1

    formal_failure_reasons: List[str] = []
    if formal_post_qat_failed(args.profile, qat_applied, qat_reasons):
        formal_failure_reasons.append(
            "Post-QAT validation still exceeds quantization gates: "
            + "; ".join(qat_reasons)
        )
    if args.profile == "formal" and qat_applied and (
        post_qat_baseline is None or post_qat_candidate is None
    ):
        formal_failure_reasons.append(
            "Formal QAT requires fresh post-QAT metrics from the validation manifest."
        )

    final_baseline = post_qat_baseline or pre_qat_baseline
    final_candidate = post_qat_candidate or pre_qat_candidate
    if args.profile == "formal" and (final_baseline is None or final_candidate is None):
        formal_failure_reasons.append(
            "Formal quantization requires baseline and candidate metrics, either supplied "
            "or computed from the validation manifest."
        )

    output_written = not formal_failure_reasons
    if output_written:
        output_tflite.parent.mkdir(parents=True, exist_ok=True)
        output_tflite.write_bytes(tflite_model)

    digest = hashlib.sha256(tflite_model).hexdigest()
    acceptance_eligible = (
        quant_mode == "full_integer_int8"
        and args.profile == "formal"
        and not qat_reasons
        and final_baseline is not None
        and final_candidate is not None
        and output_written
    )
    write_json(
        args.report,
        {
            "seed": args.seed,
            "mode": mode,
            "quantization": quant_mode,
            "profile": args.profile,
            "status": "PASS" if output_written else "FAIL",
            "failure_reasons": formal_failure_reasons,
            "acceptance_eligible": acceptance_eligible,
            "representative": rep_info,
            "input_model": display_path(input_model),
            "input_model_sha256": hashlib.sha256(input_model.read_bytes()).hexdigest(),
            "output_tflite": display_path(output_tflite),
            "output_written": output_written,
            "bytes": len(tflite_model),
            "model_sha256": digest,
            "sha256": digest,
            "qat_applied": qat_applied,
            "qat_triggered": bool(initial_qat_reasons),
            "qat_trigger_reasons": initial_qat_reasons,
            "post_qat_trigger_reasons": qat_reasons if qat_applied else None,
            "qat_triggers": cfg.get("qat_triggers", {}),
            "baseline_metrics": final_baseline,
            "candidate_metrics": final_candidate,
            "baseline_semantics": "original_input_keras",
            "candidate_semantics": "final_tflite",
            "candidate_keras_tflite_agreement_rate": (
                final_candidate.get("candidate_keras_tflite_agreement_rate")
                if final_candidate
                else None
            ),
            "pre_qat_baseline_metrics": pre_qat_baseline,
            "pre_qat_candidate_metrics": pre_qat_candidate,
            "post_qat_baseline_metrics": post_qat_baseline,
            "post_qat_candidate_metrics": post_qat_candidate,
            "note": (
                "hybrid_fallback is not the acceptance baseline; "
                "metadata must not claim full INT8 unless quantization=full_integer_int8."
            ),
        },
    )
    for reason in formal_failure_reasons:
        print(reason, file=sys.stderr)
    if formal_failure_reasons:
        return 1
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
