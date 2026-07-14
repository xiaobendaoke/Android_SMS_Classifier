#!/usr/bin/env python3
"""Validate label consistency in processed JSONL files."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

import yaml

SEED = 42

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT))
from src.schema import LABELS, VALID_LABELS, record_from_dict, validate_records  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate labels in JSONL manifests.")
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "data" / "processed" / "train.jsonl",
        help="JSONL file or directory to validate.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "labels.yaml",
        help="Label config YAML for cross-check.",
    )
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed.")
    return parser


def collect_files(path: Path) -> List[Path]:
    if path.is_dir():
        return sorted(path.glob("*.jsonl"))
    return [path]


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

    errors: List[str] = []
    total = 0
    for file_path in files:
        if not file_path.exists():
            errors.append(f"missing file: {file_path}")
            continue
        records = []
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
            for err in record.validate():
                errors.append(f"{file_path}:{line_no}: {err}")
            if record.label in expected_labels:
                continue
            if record.label not in VALID_LABELS:
                errors.append(f"{file_path}:{line_no}: unknown label {record.label}")

        errors.extend(validate_records(records))

    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        print(f"FAILED: {len(errors)} issue(s) in {total} records", file=sys.stderr)
        return 1

    print(f"OK: validated {total} records across {len(files)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
