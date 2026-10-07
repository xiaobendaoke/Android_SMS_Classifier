#!/usr/bin/env python3
"""Restore the direct pre-boundary frozen split into a temporary directory.

Does not write processed/. Does not apply boundary corrections.
Test integrity is verified by silent ID counts and SHA-256 only;
this script never prints or exports test SMS bodies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.build_dataset import (  # noqa: E402
    exclude_holdout_components,
    load_holdout_ids,
    load_raw_records,
    sha256_file,
)
from src.deduplicate import deduplicate_exact, deduplicate_normalized  # noqa: E402
from src.leakage import audit_leakage  # noqa: E402
from src.schema import SmsRecord, write_jsonl  # noqa: E402
from src.split_groups import connected_group_ids, split_groups  # noqa: E402
from src.train_utils import set_seed  # noqa: E402

EXPECTED = {
    "train_count": 11221,
    "validation_count": 1402,
    "test_count": 1402,
    "validation_sha256": (
        "4487924f07ca074e6ff4d345b2c79e1e9ea8719decc8cd4e5518ac4346ae9632"
    ),
    "test_sha256": (
        "fa98aa85fdb3047d8e90fe3ab98dd923f9490cd160cc60c90926eef937c79781"
    ),
}

DEFAULT_RAW = [
    ROOT / "data" / "raw" / "normal_2w_zh_relabel.jsonl",
    ROOT / "data" / "raw" / "annotated_homework_bootstrap.jsonl",
]
DEFAULT_HOLDOUT = (
    ROOT / "data" / "manifests" / "transaction_specialist_holdout.json"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Restore pre-boundary split into a temporary directory."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "interim" / "restore_pre_boundary_v1",
        help="Temporary output directory (never the live processed/ tree).",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--holdout-manifest",
        type=Path,
        default=DEFAULT_HOLDOUT,
    )
    parser.add_argument(
        "--raw-file",
        type=Path,
        action="append",
        default=[],
    )
    return parser


def collect_ids(path: Path) -> List[str]:
    """Collect IDs only; never load text into reports."""
    ids: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        ids.append(str(payload.get("id", "")))
    return ids


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    raw_files = [path.resolve() for path in (args.raw_file or DEFAULT_RAW)]
    holdout = args.holdout_manifest.resolve()
    output_dir = args.output_dir.resolve()
    if output_dir == (ROOT / "data" / "processed").resolve():
        print("Refusing to write restore output into live processed/.", file=sys.stderr)
        return 2

    for path in raw_files:
        if not path.exists():
            print(f"Missing raw source: {path}", file=sys.stderr)
            return 1
    if not holdout.exists():
        print(f"Missing holdout manifest: {holdout}", file=sys.stderr)
        return 1

    set_seed(args.seed)
    records = load_raw_records(ROOT / "data" / "raw", raw_files)
    # Intentionally skip label corrections — this is the direct pre-state.
    records, removed_exact = deduplicate_exact(records)
    records, removed_norm = deduplicate_normalized(records)
    holdout_ids = load_holdout_ids(holdout)
    records, removed_holdout = exclude_holdout_components(records, holdout_ids)
    splits = split_groups(records, seed=args.seed)

    flat: List[SmsRecord] = []
    for split_name in ("train", "validation", "test"):
        for record in splits.get(split_name, []):
            record.split = split_name
            flat.append(record)
    leakage = audit_leakage(flat)
    if leakage["status"] != "PASS":
        print(json.dumps(leakage, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    split_meta = {}
    for split_name in ("train", "validation", "test"):
        out_path = output_dir / f"{split_name}.jsonl"
        write_jsonl(out_path, splits.get(split_name, []))
        ids = collect_ids(out_path)
        component_ids = connected_group_ids(splits.get(split_name, []))
        split_meta[split_name] = {
            "path": str(out_path.relative_to(ROOT)).replace("\\", "/"),
            "count": len(ids),
            "sha256": sha256_file(out_path),
            "ids_sha256": hashlib.sha256(
                "\n".join(ids).encode("utf-8")
            ).hexdigest(),
            "component_count": len(set(component_ids.values())),
        }

    report = {
        "status": "UNKNOWN",
        "seed": args.seed,
        "source_files": [
            {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256_file(path),
            }
            for path in raw_files
        ],
        "holdout_manifest_sha256": sha256_file(holdout),
        "dedupe": {
            "removed_exact": removed_exact,
            "removed_normalized": removed_norm,
            "excluded_connected_records": removed_holdout,
        },
        "splits": {
            name: {
                "count": meta["count"],
                "sha256": meta["sha256"],
                "ids_sha256": meta["ids_sha256"],
                "component_count": meta["component_count"],
                "path": meta["path"],
            }
            for name, meta in split_meta.items()
        },
        "expected": EXPECTED,
        "checks": {
            "train_count_match": split_meta["train"]["count"]
            == EXPECTED["train_count"],
            "validation_count_match": split_meta["validation"]["count"]
            == EXPECTED["validation_count"],
            "test_count_match": split_meta["test"]["count"]
            == EXPECTED["test_count"],
            "validation_sha_match": split_meta["validation"]["sha256"]
            == EXPECTED["validation_sha256"],
            "test_sha_match": split_meta["test"]["sha256"]
            == EXPECTED["test_sha256"],
        },
        "leakage": {"status": leakage["status"], "issue_count": leakage["issue_count"]},
        "note": (
            "Test body content is intentionally omitted from this report. "
            "Only silent ID/SHA integrity checks were performed."
        ),
    }
    all_ok = all(report["checks"].values())
    report["status"] = "PASS" if all_ok else "FAIL"
    report_path = output_dir / "restore_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if all_ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
