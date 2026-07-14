#!/usr/bin/env python3
"""Verify Android manifests do not declare INTERNET permission."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANDROID_DIR = ROOT / "android"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan AndroidManifest.xml files for INTERNET permission."
    )
    parser.add_argument(
        "--android-dir",
        type=Path,
        default=ANDROID_DIR,
        help="Android project root.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifests = list(args.android_dir.rglob("AndroidManifest.xml"))
    if not manifests:
        print("No AndroidManifest.xml found.", file=sys.stderr)
        return 1
    violations = []
    for manifest in manifests:
        text = manifest.read_text(encoding="utf-8")
        if "android.permission.INTERNET" in text:
            violations.append(str(manifest))
    if violations:
        for path in violations:
            print(f"INTERNET found: {path}", file=sys.stderr)
        return 1
    print(f"OK: no INTERNET in {len(manifests)} manifest(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
