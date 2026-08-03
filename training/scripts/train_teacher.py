#!/usr/bin/env python3
"""Fine-tune multilingual BERT teacher with PyTorch (transformers 5+ has no TF)."""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import yaml

SEED = 42
SETUP_DOC = "docs/异机测试环境安装清单.md"

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "configs" / "teacher.yaml"

sys.path.insert(0, str(ROOT))
from src.metrics import summarize_metrics  # noqa: E402
from src.normalize import normalize_text  # noqa: E402
from src.schema import LABEL_ORDER  # noqa: E402
from src.train_utils import (  # noqa: E402
    filter_records_by_languages,
    load_labeled_records,
    set_seed,
    write_json,
)


def check_deps() -> Optional[str]:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        return (
            f"PyTorch + transformers required for teacher fine-tuning. "
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
    parser.add_argument("--max-length", type=int, default=0, help="Override config max_length (0=config).")
    parser.add_argument("--batch-size", type=int, default=0, help="Override config batch_size (0=config).")
    parser.add_argument("--epochs", type=int, default=0, help="Override config epochs (0=config).")
    parser.add_argument(
        "--no-fp16",
        action="store_true",
        help="Disable FP16 even if config enables it.",
    )
    parser.add_argument(
        "--allow-cpu",
        action="store_true",
        help="Allow CPU training (default: require CUDA GPU).",
    )
    parser.add_argument(
        "--logits-manifest",
        type=Path,
        default=None,
        help="Optional isolated teacher-logits manifest path (default preserves legacy path).",
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


def encode_batch(
    tokenizer,
    texts: Sequence[str],
    max_length: int,
    device,
):
    enc = tokenizer(
        [normalize_text(text) for text in texts],
        truncation=True,
        padding="max_length",
        max_length=max_length,
        return_tensors="pt",
    )
    return {k: v.to(device) for k, v in enc.items()}


def predict_logits(model, tokenizer, texts: Sequence[str], max_length: int, batch_size: int, device):
    import torch

    model.eval()
    chunks: List[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, len(texts), batch_size):
            batch_texts = texts[start : start + batch_size]
            batch = encode_batch(tokenizer, batch_texts, max_length, device)
            out = model(**batch)
            chunks.append(out.logits.detach().cpu().numpy())
    if not chunks:
        return np.zeros((0, len(LABEL_ORDER)), dtype=np.float32)
    return np.concatenate(chunks, axis=0).astype(np.float32)


def train_epoch(
    model,
    tokenizer,
    records,
    label_to_idx,
    max_length,
    batch_size,
    optimizer,
    device,
    *,
    use_fp16: bool,
    scaler,
    class_weights,
    focal_gamma: float,
):
    import torch

    model.train()
    total_loss = 0.0
    n_batches = 0
    texts = [r.text for r in records]
    labels = np.asarray([label_to_idx[r.label] for r in records], dtype=np.int64)
    order = np.random.permutation(len(records))
    for start in range(0, len(order), batch_size):
        idx = order[start : start + batch_size]
        batch_texts = [texts[i] for i in idx]
        batch_y = torch.tensor(labels[idx], dtype=torch.long, device=device)
        batch = encode_batch(tokenizer, batch_texts, max_length, device)
        optimizer.zero_grad(set_to_none=True)
        if use_fp16 and device.type == "cuda":
            with torch.autocast(device_type="cuda", dtype=torch.float16):
                out = model(**batch)
                per_example = torch.nn.functional.cross_entropy(
                    out.logits,
                    batch_y,
                    weight=class_weights,
                    reduction="none",
                )
                true_probability = torch.softmax(out.logits, dim=-1).gather(
                    1, batch_y.unsqueeze(1)
                ).squeeze(1)
                loss = (
                    torch.pow(1.0 - true_probability, focal_gamma)
                    * per_example
                ).mean()
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
        else:
            out = model(**batch)
            per_example = torch.nn.functional.cross_entropy(
                out.logits,
                batch_y,
                weight=class_weights,
                reduction="none",
            )
            true_probability = torch.softmax(out.logits, dim=-1).gather(
                1, batch_y.unsqueeze(1)
            ).squeeze(1)
            loss = (
                torch.pow(1.0 - true_probability, focal_gamma)
                * per_example
            ).mean()
            loss.backward()
            optimizer.step()
        total_loss += float(loss.detach().item())
        n_batches += 1
        del batch, batch_y, out, loss, per_example, true_probability
    if device.type == "cuda":
        torch.cuda.empty_cache()
    return total_loss / max(1, n_batches)


def eval_accuracy(model, tokenizer, records, label_to_idx, max_length, batch_size, device) -> Tuple[float, np.ndarray, np.ndarray]:
    texts = [r.text for r in records]
    y_true = np.asarray([label_to_idx[r.label] for r in records], dtype=np.int64)
    logits = predict_logits(model, tokenizer, texts, max_length, batch_size, device)
    preds = np.argmax(logits, axis=-1)
    acc = float(np.mean(preds == y_true)) if len(y_true) else 0.0
    return acc, y_true, preds


def teacher_checkpoint_score(metrics: Dict[str, object], cfg: Dict[str, float]) -> Tuple[float, ...]:
    per_class = metrics.get("per_class", {})
    transaction_recall = float(per_class.get("TRANSACTION", {}).get("recall", 0.0))
    transaction_precision = float(per_class.get("TRANSACTION", {}).get("precision", 0.0))
    harass_f1 = float(per_class.get("HARASS", {}).get("f1", 0.0))
    fraud_recall = float(per_class.get("FRAUD", {}).get("recall", 0.0))
    macro_f1 = float(metrics.get("macro_f1", 0.0))
    gate_ratios = (
        transaction_recall / max(cfg["target_transaction_recall"], 1e-9),
        transaction_precision / max(cfg["min_transaction_precision"], 1e-9),
        macro_f1 / max(cfg["min_macro_f1"], 1e-9),
        harass_f1 / max(cfg["min_harass_f1"], 1e-9),
        fraud_recall / max(cfg["min_fraud_recall"], 1e-9),
    )
    all_gates_met = float(min(gate_ratios) >= 1.0)
    if all_gates_met:
        return (1.0, transaction_recall, macro_f1, min(gate_ratios), 1.0)
    capped_mean = float(np.mean([min(value, 1.0) for value in gate_ratios]))
    return (0.0, min(gate_ratios), capped_mean, macro_f1, transaction_recall)


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.config.exists():
        print(f"Config missing: {args.config}", file=sys.stderr)
        return 1

    err = check_deps()
    if err:
        print(err, file=sys.stderr)
        return 2

    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    with args.config.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    set_seed(int(cfg.get("seed", args.seed)))
    torch.manual_seed(int(cfg.get("seed", args.seed)))

    model_name = cfg.get("model", {}).get("name", "bert-base-multilingual-cased")
    hub_id = cfg.get("model", {}).get("hub_id", model_name)
    max_length = int(args.max_length or cfg.get("model", {}).get("max_length", 128))
    train_path = ROOT / cfg.get("data", {}).get("train_manifest", "data/processed/train.jsonl")
    val_path = ROOT / cfg.get("data", {}).get("val_manifest", "data/processed/validation.jsonl")
    output_dir = ROOT / cfg.get("output", {}).get("checkpoint_dir", "artifacts/teacher")
    manifest_path = ROOT / cfg.get("output", {}).get("manifest", "data/manifests/teacher_manifest.json")

    if not train_path.exists():
        print(f"Training manifest missing: {train_path}", file=sys.stderr)
        return 1

    accepted_languages = cfg.get("data", {}).get("accepted_languages", [])
    train_records = filter_records_by_languages(
        load_labeled_records(train_path),
        accepted_languages,
    )
    val_records = (
        filter_records_by_languages(
            load_labeled_records(val_path),
            accepted_languages,
        )
        if val_path.exists()
        else []
    )
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

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if not args.allow_cpu and device.type != "cuda":
        print(
            "ERROR: CUDA GPU required but not available.\n"
            "  - Colab: Runtime → Change runtime type → GPU (T4), then Restart session.\n"
            "  - Do not pip-install the default CPU torch wheel over Colab's CUDA build.\n"
            "  - Smoke on CPU only: pass --allow-cpu",
            file=sys.stderr,
        )
        return 3
    if device.type == "cuda":
        # Force visible device 0 when CUDA is present
        torch.cuda.set_device(0)
        print(f"Using GPU 0: {torch.cuda.get_device_name(0)}")
    print(f"Teacher fine-tune: source={pretrained} seed={args.seed} device={device}")
    print(f"  train={len(train_records)} val={len(val_records)} max_length={max_length}")

    try:
        tokenizer = AutoTokenizer.from_pretrained(
            pretrained,
            local_files_only=bool(args.model_path),
            fix_mistral_regex=True,
        )
        model = AutoModelForSequenceClassification.from_pretrained(
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

    model.to(device)
    if bool(cfg.get("training", {}).get("gradient_checkpointing", True)):
        if hasattr(model, "gradient_checkpointing_enable"):
            model.gradient_checkpointing_enable()
            print("gradient_checkpointing: enabled")

    label_to_idx = {label: i for i, label in enumerate(LABEL_ORDER)}
    training_cfg = cfg.get("training", {})
    batch_size = int(args.batch_size or training_cfg.get("batch_size", 8))
    epochs = int(args.epochs or training_cfg.get("epochs", 2))
    lr = float(training_cfg.get("learning_rate", 2e-5))
    use_fp16 = bool(training_cfg.get("fp16", True)) and not args.no_fp16 and device.type == "cuda"
    scaler = torch.cuda.amp.GradScaler(enabled=use_fp16)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=lr,
        weight_decay=float(training_cfg.get("weight_decay", 0.01)),
    )
    train_labels = np.asarray([label_to_idx[r.label] for r in train_records], dtype=np.int64)
    counts = np.bincount(train_labels, minlength=len(LABEL_ORDER)).astype(np.float32)
    counts = np.maximum(counts, 1.0)
    weight_strategy = str(training_cfg.get("class_weight_strategy", "balanced"))
    if weight_strategy == "uniform":
        class_weights_np = np.ones(len(LABEL_ORDER), dtype=np.float32)
    elif weight_strategy == "balanced":
        class_weights_np = counts.sum() / (len(LABEL_ORDER) * counts)
        for idx, label in enumerate(LABEL_ORDER):
            class_weights_np[idx] *= float(
                training_cfg.get("class_weight_multipliers", {}).get(label, 1.0)
            )
        class_weights_np *= len(LABEL_ORDER) / float(class_weights_np.sum())
        clip_cfg = training_cfg.get("class_weight_clip")
        if clip_cfg is not None:
            if not isinstance(clip_cfg, list) or len(clip_cfg) != 2:
                raise ValueError("training.class_weight_clip must be [minimum, maximum]")
            class_weights_np = np.clip(
                class_weights_np,
                float(clip_cfg[0]),
                float(clip_cfg[1]),
            )
            class_weights_np *= len(LABEL_ORDER) / float(class_weights_np.sum())
    else:
        raise ValueError(
            "training.class_weight_strategy must be 'balanced' or 'uniform'"
        )
    class_weights = torch.tensor(class_weights_np, dtype=torch.float32, device=device)
    targets = {
        "target_transaction_recall": float(
            training_cfg.get("target_transaction_recall", 0.985)
        ),
        "min_transaction_precision": float(
            training_cfg.get("min_transaction_precision", 0.92)
        ),
        "min_macro_f1": float(training_cfg.get("min_macro_f1", 0.86)),
        "min_harass_f1": float(training_cfg.get("min_harass_f1", 0.80)),
        "min_fraud_recall": float(training_cfg.get("min_fraud_recall", 0.80)),
    }
    patience = int(training_cfg.get("early_stopping_patience", 3))
    min_epochs = int(training_cfg.get("min_epochs", 3))
    focal_gamma = float(training_cfg.get("focal_gamma", 0.0))
    print(
        f"  batch_size={batch_size} epochs={epochs} fp16={use_fp16} "
        f"class_weight_strategy={weight_strategy} "
        f"focal_gamma={focal_gamma} "
        f"class_weights={dict(zip(LABEL_ORDER, class_weights_np.tolist()))}"
    )

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    best_dir = Path(tempfile.mkdtemp(prefix="teacher_best_", dir=output_dir.parent))
    best_score: Optional[Tuple[float, ...]] = None
    best_epoch = 0
    stale_epochs = 0
    history: Dict[str, List] = {"loss": [], "val_accuracy": [], "val_metrics": []}
    for epoch in range(epochs):
        train_loss = train_epoch(
            model,
            tokenizer,
            train_records,
            label_to_idx,
            max_length,
            batch_size,
            optimizer,
            device,
            use_fp16=use_fp16,
            scaler=scaler,
            class_weights=class_weights,
            focal_gamma=focal_gamma,
        )
        history["loss"].append(train_loss)
        if val_records:
            val_acc, val_y, val_preds = eval_accuracy(
                model, tokenizer, val_records, label_to_idx, max_length, batch_size, device
            )
            epoch_metrics = summarize_metrics(
                [LABEL_ORDER[i] for i in val_y.tolist()],
                [LABEL_ORDER[i] for i in val_preds.tolist()],
                LABEL_ORDER,
            )
            history["val_accuracy"].append(val_acc)
            history["val_metrics"].append(epoch_metrics)
            score = teacher_checkpoint_score(epoch_metrics, targets)
            if best_score is None or score > best_score:
                best_score = score
                best_epoch = epoch + 1
                stale_epochs = 0
                model.save_pretrained(best_dir)
                tokenizer.save_pretrained(best_dir)
            else:
                stale_epochs += 1
            print(
                f"epoch {epoch + 1}/{epochs} loss={train_loss:.4f} "
                f"val_acc={val_acc:.4f} val_macro_f1={epoch_metrics['macro_f1']:.4f} "
                f"val_txn_recall="
                f"{epoch_metrics['per_class']['TRANSACTION']['recall']:.4f}"
            )
        else:
            print(f"epoch {epoch + 1}/{epochs} loss={train_loss:.4f}")
        if val_records and epoch + 1 >= min_epochs and stale_epochs >= patience:
            print(f"early stopping: no checkpoint improvement for {patience} epochs")
            break

    output_dir.mkdir(parents=True, exist_ok=True)
    if best_epoch:
        del optimizer, model
        if device.type == "cuda":
            torch.cuda.empty_cache()
        model = AutoModelForSequenceClassification.from_pretrained(
            best_dir,
            local_files_only=True,
        ).to(device)
        print(f"restored best validation checkpoint from epoch {best_epoch}")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    shutil.rmtree(best_dir, ignore_errors=True)

    metrics = {}
    if val_records:
        _, val_y, val_preds = eval_accuracy(
            model, tokenizer, val_records, label_to_idx, max_length, batch_size, device
        )
        metrics = summarize_metrics(
            [LABEL_ORDER[i] for i in val_y.tolist()],
            [LABEL_ORDER[i] for i in val_preds.tolist()],
            LABEL_ORDER,
        )

    logits_path = output_dir / "teacher_logits_train.npz"
    train_texts = [r.text for r in train_records]
    train_logits = predict_logits(
        model, tokenizer, train_texts, max_length, batch_size, device
    )
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
    logits_manifest_path = args.logits_manifest or (ROOT / "data" / "manifests" / "teacher_logits_manifest.json")
    write_json(logits_manifest_path, logits_manifest)

    manifest = {
        "seed": args.seed,
        "model_name": model_name,
        "pretrained_source": pretrained,
        "backend": "pytorch",
        "device": str(device),
        "local_files_only": bool(args.model_path),
        "checkpoint_dir": str(output_dir.relative_to(ROOT)),
        "checkpoint_sha256": sha256_dir_manifest(output_dir),
        "train_count": len(train_records),
        "val_count": len(val_records),
        "history": history,
        "val_metrics": metrics,
        "best_epoch": best_epoch,
        "class_weights": dict(zip(LABEL_ORDER, class_weights_np.tolist())),
        "focal_gamma": focal_gamma,
        "normalization": "normalize_text",
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
