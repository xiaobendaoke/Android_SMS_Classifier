#!/usr/bin/env python3
"""Scan source for sensitive log patterns (SMS body, OTP, etc.)."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SENSITIVE_PATTERNS = [
    re.compile(r"Log\.[deiw]\([^)]*body", re.IGNORECASE),
    re.compile(r"println\([^)]*body", re.IGNORECASE),
    re.compile(r"Timber\.[deiw]\([^)]*body", re.IGNORECASE),
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Heuristic scan for logging of SMS body or OTP content."
    )
    parser.add_argument(
        "--scan-dir",
        type=Path,
        default=ROOT / "android",
        help="Directory to scan (default: android/).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.scan_dir.exists():
        print(f"Scan dir missing: {args.scan_dir}", file=sys.stderr)
        return 1
    hits: list[str] = []
    for path in args.scan_dir.rglob("*"):
        if path.suffix not in {".kt", ".java", ".xml"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for pattern in SENSITIVE_PATTERNS:
            if pattern.search(text):
                hits.append(str(path))
                break
    if hits:
        for hit in hits:
            print(f"Possible sensitive log: {hit}", file=sys.stderr)
        return 1
    print("OK: no obvious sensitive log patterns (Phase 0 heuristic)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
