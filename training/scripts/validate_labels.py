#!/usr/bin/env python3
"""Validate label consistency and freeze integrity in processed JSONL files."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml

SEED = 42

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT))
from src.label_corrections import load_corrections_manifest  # noqa: E402
from src.schema import LABELS, record_from_dict  # noqa: E402
from src.split_assignment import (  # noqa: E402
    collect_ids_from_jsonl,
    load_assignment,
    sha256_file,
)
from src.text_quality import text_quality_issues  # noqa: E402

FORMAL_SPLITS = ("train", "validation", "test")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate labels in JSONL manifests.")
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "data" / "processed",
        help="JSONL file or directory to validate (default: all processed splits).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "labels.yaml",
        help="Label config YAML for cross-check.",
    )
    parser.add_argument(
        "--split-assignment",
        type=Path,
        default=ROOT / "data" / "manifests" / "split_assignment_v1.json",
        help="Frozen split assignment used for membership/SHA gates.",
    )
    parser.add_argument(
        "--label-corrections",
        type=Path,
        default=ROOT / "data" / "manifests" / "boundary_label_corrections_v1.json",
        help="Correction overlay checked for validation/test leakage.",
    )
    parser.add_argument(
        "--require-frozen-assignment",
        action="store_true",
        default=True,
        help="Require split assignment checks for processed formal splits.",
    )
    parser.add_argument(
        "--no-require-frozen-assignment",
        action="store_false",
        dest="require_frozen_assignment",
    )
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed.")
    return parser


def collect_files(path: Path) -> List[Path]:
    if path.is_dir():
        return sorted(path.glob("*.jsonl"))
    return [path]


def split_name_for(path: Path) -> Optional[str]:
    stem = path.stem
    if stem in FORMAL_SPLITS:
        return stem
    return None


def default_assignment_for_input(input_path: Path) -> Path:
    resolved = input_path.resolve()
    if resolved == (ROOT / "data" / "processed_v2").resolve() or (
        resolved.parent.name == "processed_v2"
    ):
        return ROOT / "data" / "manifests" / "split_assignment_v2.json"
    return ROOT / "data" / "manifests" / "split_assignment_v1.json"


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    files = collect_files(args.input)
    if not files:
        print(f"No JSONL files found at: {args.input}", file=sys.stderr)
        return 1

    expected_labels = set(LABELS)
    if args.config.exists():
        with args.config.open(encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
        expected_labels = set(cfg.get("labels", list(LABELS)))

    # Prefer v2 assignment automatically when validating processed_v2.
    if args.split_assignment == (
        ROOT / "data" / "manifests" / "split_assignment_v1.json"
    ):
        args.split_assignment = default_assignment_for_input(args.input)

    assignment = None
    if args.split_assignment.exists():
        assignment = load_assignment(args.split_assignment)
    elif args.require_frozen_assignment and args.input.resolve() in {
        (ROOT / "data" / "processed").resolve(),
        (ROOT / "data" / "processed_v2").resolve(),
    }:
        print(
            f"Missing frozen split assignment: {args.split_assignment}",
            file=sys.stderr,
        )
        return 1

    errors: List[str] = []
    total = 0
    seen_ids_global: Dict[str, str] = {}
    id_to_text: Dict[str, str] = {}

    for file_path in files:
        if not file_path.exists():
            errors.append(f"missing file: {file_path}")
            continue
        split_name = split_name_for(file_path)
        formal = split_name in FORMAL_SPLITS
        records = []
        file_ids: List[str] = []
        for line_no, line in enumerate(
            file_path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{file_path}:{line_no}: invalid JSON: {exc}")
                continue
            record = record_from_dict(data)
            records.append(record)
            total += 1
            file_ids.append(record.id)

            for err in record.validate():
                # Formal splits tighten label rules below; still keep schema errors.
                if formal and err.startswith("invalid label") and record.label == "NEEDS_REVIEW":
                    continue
                errors.append(f"{file_path}:{line_no}: {err}")

            if formal:
                if record.label not in LABELS:
                    errors.append(
                        f"{file_path}:{line_no}: formal split forbids label "
                        f"{record.label!r} (NEEDS_REVIEW not allowed)"
                    )
                elif record.label not in expected_labels:
                    errors.append(
                        f"{file_path}:{line_no}: label {record.label} not in config"
                    )
                for issue in text_quality_issues(record.text, record_id=record.id):
                    errors.append(f"{file_path}:{line_no}: {issue}")
            else:
                if record.label not in (LABELS | {"NEEDS_REVIEW"}):
                    errors.append(
                        f"{file_path}:{line_no}: unknown label {record.label}"
                    )

            if record.id in seen_ids_global and seen_ids_global[record.id] != split_name:
                errors.append(
                    f"{file_path}:{line_no}: duplicate id across splits: {record.id}"
                )
            if record.id in id_to_text and id_to_text[record.id] != record.text:
                errors.append(
                    f"{file_path}:{line_no}: same id different text: {record.id}"
                )
            if record.id in seen_ids_global and seen_ids_global[record.id] == split_name:
                errors.append(f"{file_path}:{line_no}: duplicate id: {record.id}")
            seen_ids_global[record.id] = split_name or file_path.name
            id_to_text[record.id] = record.text

        if formal and assignment is not None:
            expected_ids = assignment["splits"][split_name]["ids"]
            # Train may drop quarantined rows; membership must be subset with
            # stable relative order of remaining ids. Validation/test must match
            # exactly and keep frozen SHA.
            if split_name in ("validation", "test"):
                actual_sha = sha256_file(file_path)
                expected_sha = assignment["splits"][split_name]["sha256"]
                if actual_sha != expected_sha:
                    errors.append(
                        f"{split_name}: frozen sha256 changed "
                        f"(expected={expected_sha}, actual={actual_sha})"
                    )
                if file_ids != expected_ids:
                    errors.append(
                        f"{split_name}: frozen id membership/order mismatch"
                    )
            else:
                expected_set = set(expected_ids)
                unknown = [rid for rid in file_ids if rid not in expected_set]
                if unknown:
                    errors.append(
                        f"train: ids not in frozen assignment: {unknown[:10]}"
                    )
                # Relative order of surviving train ids must follow assignment.
                surviving = [rid for rid in expected_ids if rid in set(file_ids)]
                if file_ids != surviving:
                    errors.append(
                        "train: surviving id order differs from frozen assignment"
                    )

    if args.label_corrections.exists() and assignment is not None:
        corrections = load_corrections_manifest(args.label_corrections)
        correction_ids = {
            str(item.get("id", ""))
            for item in corrections.get("corrections", [])
            if str(item.get("id", ""))
        }
        val_ids = set(assignment["splits"]["validation"]["ids"])
        test_ids = set(assignment["splits"]["test"]["ids"])
        leaked = sorted((correction_ids & val_ids) | (correction_ids & test_ids))
        if leaked:
            errors.append(
                "correction ids leak into frozen validation/test: "
                + ", ".join(leaked[:20])
            )

    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        print(f"FAILED: {len(errors)} issue(s) in {total} records", file=sys.stderr)
        return 1

    print(f"OK: validated {total} records across {len(files)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
