#!/usr/bin/env python3
"""Mechanically scan frozen splits for text-quality failures.

Never prints or stores SMS bodies / fragments for any split, including test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.schema import load_jsonl  # noqa: E402
from src.split_assignment import sha256_file  # noqa: E402
from src.split_groups import connected_group_ids  # noqa: E402
from src.text_quality import SCANNER_VERSION, classify_text_quality_reasons  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan frozen splits for text quality.")
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=ROOT / "data" / "processed",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "metrics" / "frozen_text_quality_v1.json",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    failures = []
    source_split_shas = {}
    for split_name in ("train", "validation", "test"):
        path = args.processed_dir / f"{split_name}.jsonl"
        if not path.exists():
            print(f"Missing split: {path}", file=sys.stderr)
            return 1
        source_split_shas[split_name] = sha256_file(path)
        records = load_jsonl(path)
        components = connected_group_ids(records)
        for idx, record in enumerate(records):
            reasons = classify_text_quality_reasons(record.text)
            if not reasons:
                continue
            failures.append(
                {
                    "id": record.id,
                    "split": split_name,
                    "label": record.label,
                    "language": record.language,
                    "source": record.source,
                    "component_id": components[idx],
                    "quality_reason": reasons[0],
                    "quality_reasons": reasons,
                    "text_sha256": hashlib.sha256(
                        record.text.encode("utf-8")
                    ).hexdigest(),
                }
            )

    report = {
        "scanner_version": SCANNER_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_split_shas": source_split_shas,
        "total_failures": len(failures),
        "validation_failure_count": sum(
            1 for row in failures if row["split"] == "validation"
        ),
        "test_failure_count": sum(1 for row in failures if row["split"] == "test"),
        "train_failure_count": sum(1 for row in failures if row["split"] == "train"),
        "failures": failures,
        "note": (
            "No SMS bodies or fragments are included. Test integrity uses "
            "id/component/text_sha256 only."
        ),
    }
    # Hard guard: reject accidental body leakage keys.
    serialized = json.dumps(report, ensure_ascii=False)
    if '"text":' in serialized or "\ufffd" in serialized and "replacement_character" not in serialized:
        # Allow reason strings only; bodies must never appear.
        for row in failures:
            if "text" in row:
                print("Refusing to write report containing text bodies.", file=sys.stderr)
                return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        output_display = str(args.output.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        output_display = str(args.output)
    print(
        json.dumps(
            {
                "output": output_display,
                "total_failures": report["total_failures"],
                "validation_failure_count": report["validation_failure_count"],
                "test_failure_count": report["test_failure_count"],
                "train_failure_count": report["train_failure_count"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
