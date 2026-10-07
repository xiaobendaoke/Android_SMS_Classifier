#!/usr/bin/env python3
"""Freeze immutable split assignment from a verified pre-boundary restore."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.split_assignment import build_assignment_from_splits, sha256_file  # noqa: E402

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


def git_revision() -> Optional[str]:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT.parent,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze split_assignment_v1.json")
    parser.add_argument(
        "--restore-dir",
        type=Path,
        default=ROOT / "data" / "interim" / "restore_pre_boundary_v1",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "manifests" / "split_assignment_v1.json",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--holdout-manifest",
        type=Path,
        default=ROOT / "data" / "manifests" / "transaction_specialist_holdout.json",
    )
    parser.add_argument(
        "--raw-file",
        type=Path,
        action="append",
        default=[],
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    restore_dir = args.restore_dir.resolve()
    holdout = args.holdout_manifest.resolve()
    raw_files = [
        path.resolve()
        for path in (
            args.raw_file
            or [
                ROOT / "data" / "raw" / "normal_2w_zh_relabel.jsonl",
                ROOT / "data" / "raw" / "annotated_homework_bootstrap.jsonl",
            ]
        )
    ]
    split_paths = {
        name: restore_dir / f"{name}.jsonl"
        for name in ("train", "validation", "test")
    }
    missing = [str(path) for path in split_paths.values() if not path.exists()]
    if missing:
        print("Missing restore splits:\n" + "\n".join(missing), file=sys.stderr)
        return 1

    # Silent integrity gates — never print SMS bodies.
    val_sha = sha256_file(split_paths["validation"])
    test_sha = sha256_file(split_paths["test"])
    train_count = sum(
        1
        for line in split_paths["train"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    val_count = sum(
        1
        for line in split_paths["validation"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    test_count = sum(
        1
        for line in split_paths["test"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    checks = {
        "train_count_match": train_count == EXPECTED["train_count"],
        "validation_count_match": val_count == EXPECTED["validation_count"],
        "test_count_match": test_count == EXPECTED["test_count"],
        "validation_sha_match": val_sha == EXPECTED["validation_sha256"],
        "test_sha_match": test_sha == EXPECTED["test_sha256"],
    }
    if not all(checks.values()):
        print(
            json.dumps(
                {"status": "FAIL", "checks": checks, "expected": EXPECTED},
                indent=2,
            ),
            file=sys.stderr,
        )
        return 3

    holdout_payload = json.loads(holdout.read_text(encoding="utf-8"))
    holdout_ids = holdout_payload.get("ids", [])
    holdout_ids_sha = hashlib.sha256(
        "\n".join(str(item) for item in holdout_ids).encode("utf-8")
    ).hexdigest()

    assignment = build_assignment_from_splits(
        split_paths,
        seed=args.seed,
        source_shas=[
            {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256_file(path),
            }
            for path in raw_files
        ],
        holdout_ids_sha256=holdout_ids_sha,
        holdout_manifest_sha256=sha256_file(holdout),
        code_revision=git_revision(),
    )
    assignment["expected_locked"] = EXPECTED
    assignment["restore_dir"] = str(restore_dir.relative_to(ROOT)).replace("\\", "/")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(assignment, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "FROZEN",
                "output": str(args.output.relative_to(ROOT)).replace("\\", "/"),
                "freeze_sha256": assignment["freeze_sha256"],
                "splits": {
                    name: {
                        "count": assignment["splits"][name]["count"],
                        "sha256": assignment["splits"][name]["sha256"],
                    }
                    for name in ("train", "validation", "test")
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
