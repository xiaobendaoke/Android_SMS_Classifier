#!/usr/bin/env python3
"""Fine-tune multilingual BERT teacher (local cache preferred)."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import List, Optional

import numpy as np
import yaml

SEED = 42
SETUP_DOC = "docs/异机测试环境安装清单.md"

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "configs" / "teacher.yaml"

sys.path.insert(0, str(ROOT))
from src.metrics import summarize_metrics  # noqa: E402
from src.schema import LABEL_ORDER  # noqa: E402
from src.train_utils import load_labeled_records, set_seed, write_json  # noqa: E402


def check_deps() -> Optional[str]:
    try:
        import tensorflow  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        return (
            f"TensorFlow + transformers required for teacher fine-tuning. "
            f"Install per {SETUP_DOC} (see requirements-train.txt)."
        )
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fine-tune multilingual BERT teacher.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Teacher config YAML.")
    parser.add_argument(
        "--model-path",
        type=Path,
        default=None,
        help="Local pretrained model directory (preferred over hub download).",
    )
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed.")
    parser.add_argument(
        "--max-samples",
        type=int,
        default=0,
        help="Optional cap for quick smoke runs (0 = all).",
    )
    return parser


def sha256_dir_manifest(path: Path) -> str:
    if not path.exists():
        return ""
    h = hashlib.sha256()
    for file in sorted(path.rglob("*")):
        if file.is_file():
            h.update(file.relative_to(path).as_posix().encode())
            h.update(file.read_bytes())
    return h.hexdigest()


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.config.exists():
        print(f"Config missing: {args.config}", file=sys.stderr)
        return 1

    err = check_deps()
    if err:
        print(err, file=sys.stderr)
        return 2

    import tensorflow as tf
    from transformers import AutoTokenizer, TFAutoModelForSequenceClassification

    with args.config.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    set_seed(int(cfg.get("seed", args.seed)))

    model_name = cfg.get("model", {}).get("name", "bert-base-multilingual-cased")
    hub_id = cfg.get("model", {}).get("hub_id", model_name)
    max_length = int(cfg.get("model", {}).get("max_length", 128))
    train_path = ROOT / cfg.get("data", {}).get("train_manifest", "data/processed/train.jsonl")
    val_path = ROOT / cfg.get("data", {}).get("val_manifest", "data/processed/validation.jsonl")
    output_dir = ROOT / cfg.get("output", {}).get("checkpoint_dir", "artifacts/teacher")
    manifest_path = ROOT / cfg.get("output", {}).get("manifest", "data/manifests/teacher_manifest.json")

    if not train_path.exists():
        print(f"Training manifest missing: {train_path}", file=sys.stderr)
        return 1

    train_records = load_labeled_records(train_path)
    val_records = load_labeled_records(val_path) if val_path.exists() else []
    if args.max_samples > 0:
        train_records = train_records[: args.max_samples]
        val_records = val_records[: max(1, args.max_samples // 5)]

    if not train_records:
        print("No labeled training records.", file=sys.stderr)
        return 1

    pretrained = str(args.model_path) if args.model_path else hub_id
    if args.model_path and not args.model_path.exists():
        print(f"Local model path missing: {args.model_path}", file=sys.stderr)
        print("Provide --model-path to an offline cache, or allow hub access.", file=sys.stderr)
        return 1

    print(f"Teacher fine-tune: source={pretrained} seed={args.seed}")
    print(f"  train={len(train_records)} val={len(val_records)} max_length={max_length}")

    try:
        tokenizer = AutoTokenizer.from_pretrained(pretrained, local_files_only=bool(args.model_path))
        model = TFAutoModelForSequenceClassification.from_pretrained(
            pretrained,
            num_labels=len(LABEL_ORDER),
            local_files_only=bool(args.model_path),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to load pretrained teacher: {exc}", file=sys.stderr)
        print(
            "Use --model-path pointing to a local bert-base-multilingual-cased cache. "
            "Do not upload private SMS; prefer intranet mirrors.",
            file=sys.stderr,
        )
        return 1

    label_to_idx = {label: i for i, label in enumerate(LABEL_ORDER)}

    def encode_records(records):
        texts = [r.text for r in records]
        labels = [label_to_idx[r.label] for r in records]
        enc = tokenizer(
            texts,
            truncation=True,
            padding="max_length",
            max_length=max_length,
            return_tensors="tf",
        )
        return dict(enc), np.asarray(labels, dtype=np.int32)

    train_x, train_y = encode_records(train_records)
    batch_size = int(cfg.get("training", {}).get("batch_size", 8))
    epochs = int(cfg.get("training", {}).get("epochs", 2))
    lr = float(cfg.get("training", {}).get("learning_rate", 2e-5))

    optimizer = tf.keras.optimizers.Adam(learning_rate=lr)
    loss = tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True)
    model.compile(optimizer=optimizer, loss=loss, metrics=["accuracy"])

    fit_kwargs = {
        "epochs": epochs,
        "batch_size": batch_size,
    }
    if val_records:
        val_x, val_y = encode_records(val_records)
        fit_kwargs["validation_data"] = (val_x, val_y)

    history = model.fit(train_x, train_y, **fit_kwargs)

    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    metrics = {}
    if val_records:
        logits = model.predict(val_x, batch_size=batch_size).logits
        preds = np.argmax(logits, axis=-1)
        metrics = summarize_metrics(
            [LABEL_ORDER[i] for i in val_y.tolist()],
            [LABEL_ORDER[i] for i in preds.tolist()],
            LABEL_ORDER,
        )

    # Cache teacher logits for distillation on the training split.
    logits_path = output_dir / "teacher_logits_train.npz"
    train_logits = model.predict(train_x, batch_size=batch_size).logits
    np.savez_compressed(
        logits_path,
        ids=np.asarray([r.id for r in train_records]),
        logits=np.asarray(train_logits, dtype=np.float32),
    )

    logits_manifest = {
        "path": str(logits_path.relative_to(ROOT)),
        "count": len(train_records),
        "labels": LABEL_ORDER,
        "sha256": hashlib.sha256(logits_path.read_bytes()).hexdigest(),
    }
    write_json(ROOT / "data" / "manifests" / "teacher_logits_manifest.json", logits_manifest)

    manifest = {
        "seed": args.seed,
        "model_name": model_name,
        "pretrained_source": pretrained,
        "local_files_only": bool(args.model_path),
        "checkpoint_dir": str(output_dir.relative_to(ROOT)),
        "checkpoint_sha256": sha256_dir_manifest(output_dir),
        "train_count": len(train_records),
        "val_count": len(val_records),
        "history": {k: [float(x) for x in v] for k, v in history.history.items()},
        "val_metrics": metrics,
        "license_note": "bert-base-multilingual-cased is third-party; record hash and license.",
        "third_party": True,
    }
    write_json(manifest_path, manifest)
    write_json(ROOT / "reports" / "metrics" / "teacher.json", metrics or {"status": "trained_no_val"})
    print(f"Wrote teacher checkpoint to {output_dir}")
    print(f"Wrote logits cache to {logits_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
