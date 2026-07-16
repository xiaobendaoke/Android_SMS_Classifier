#!/usr/bin/env python3
"""Generate a minimal dependency SBOM for release audit (Windows-friendly)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "reports" / "audit" / "dependency_sbom.json"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate dependency SBOM JSON.")
    p.add_argument("--output", type=Path, default=OUTPUT)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    components = [
        {
            "name": "org.tensorflow:tensorflow-lite",
            "version": "2.14.0",
            "type": "library",
            "license": "Apache-2.0",
            "scope": "android/classifier-sdk",
        },
        {
            "name": "androidx.compose.ui",
            "version": "BOM",
            "type": "library",
            "license": "Apache-2.0",
            "scope": "android/app",
        },
        {
            "name": "androidx.room",
            "version": "2.x",
            "type": "library",
            "license": "Apache-2.0",
            "scope": "android/app",
        },
        {
            "name": "tensorflow (training)",
            "version": ">=2.16",
            "type": "library",
            "license": "Apache-2.0",
            "scope": "training",
            "note": "Training-only; not shipped in APK",
        },
        {
            "name": "bert-base-multilingual-cased",
            "version": "third-party",
            "type": "model",
            "license": "Apache-2.0",
            "scope": "training/teacher",
            "third_party": True,
            "note": "Optional teacher; local cache preferred. Not shipped on-device.",
        },
    ]
    payload = {
        "bomFormat": "SMSClassifier-SBOM",
        "specVersion": "0.2",
        "version": "0.2.0-ml-pipeline",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": components,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
