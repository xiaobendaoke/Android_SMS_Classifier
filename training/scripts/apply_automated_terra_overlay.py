#!/usr/bin/env python3
"""Create a separate development-only processed dataset from an automated overlay.

The locked test JSONL is copied byte-for-byte and is never parsed or relabelled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.schema import load_jsonl, write_jsonl  # noqa: E402

STATUS = "PROVISIONAL_AUTOMATED_MULTI_PASS"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_text_sha(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip("\ufeff").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overlay", type=Path, default=ROOT / "data/manifests/automated_label_corrections_terra_v1.json")
    parser.add_argument("--source", type=Path, default=ROOT / "data/processed")
    parser.add_argument("--output", type=Path, default=ROOT / "data/processed_terra_v1")
    parser.add_argument("--quarantine", type=Path, default=ROOT / "data/interim/quarantine/train_quarantine_terra_v1.jsonl")
    args = parser.parse_args()
    payload = json.loads(args.overlay.read_text(encoding="utf-8"))
    if payload.get("status") != STATUS or any(payload.get(key) for key in ("claim_allowed", "human_verified", "formal_acceptance_allowed")):
        raise SystemExit("overlay is not a safe provisional automated overlay")
    corrections = {row["id"]: row for row in payload.get("corrections", [])}
    if len(corrections) != len(payload.get("corrections", [])):
        raise SystemExit("overlay correction IDs must be unique")
    args.output.mkdir(parents=True, exist_ok=False)
    source_train, source_val, source_test = (args.source / f"{name}.jsonl" for name in ("train", "validation", "test"))
    train, validation = load_jsonl(source_train), load_jsonl(source_val)
    source_ids = {record.id for record in train + validation}
    changed, quarantine, val_reference, unmatched = 0, [], [], []
    for split, records in (("train", train), ("validation", validation)):
        kept = []
        for record in records:
            correction = corrections.get(record.id)
            if not correction:
                kept.append(record); continue
            if correction.get("text_sha256") != hashlib.sha256(record.text.encode("utf-8")).hexdigest():
                if correction.get("text_sha256_canonical") != canonical_text_sha(record.text):
                    unmatched.append(record.id)
                    kept.append(record)
                    continue
            label = correction["final_label"]
            if split == "train" and label == "NEEDS_REVIEW":
                quarantine.append(record); continue
            if split == "validation":
                val_reference.append({"id": record.id, "final_label": label, "status": "PROVISIONAL_AUTOMATED_REFERENCE_LABEL"})
            if record.label != label:
                changed += 1
                record.label = label
            record.annotator_ids = list(dict.fromkeys([*record.annotator_ids, *correction.get("annotator_ids", [])]))
            kept.append(record)
        write_jsonl(args.output / f"{split}.jsonl", kept)
    for item in corrections:
        if item not in source_ids:
            unmatched.append(item)
    write_jsonl(args.quarantine, quarantine)
    shutil.copyfile(source_test, args.output / "test.jsonl")
    if sha(source_test) != sha(args.output / "test.jsonl"):
        raise SystemExit("locked test byte identity check failed")
    (args.output / "validation_provisional_reference_labels.json").write_text(json.dumps({"status": "PROVISIONAL_AUTOMATED_REFERENCE_LABELS", "labels": val_reference}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"status": STATUS, "claim_allowed": False, "human_verified": False, "formal_acceptance_allowed": False, "overlay_sha256": sha(args.overlay), "source_sha256": {name: sha(path) for name, path in (("train", source_train), ("validation", source_val), ("test", source_test))}, "output_sha256": {name: sha(args.output / f"{name}.jsonl") for name in ("train", "validation", "test")}, "split_membership_preserved": True, "locked_test_byte_identical": True, "changed_labels": changed, "quarantine_count": len(quarantine), "unmatched_annotation_ids": unmatched, "validation_reference_status": "PROVISIONAL_AUTOMATED_REFERENCE_LABELS"}
    (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
