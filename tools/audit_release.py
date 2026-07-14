#!/usr/bin/env python3
"""Release audit: permissions, artifacts, and optional packaging."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_hashes() -> Dict[str, str]:
    candidates = [
        ROOT / "android" / "classifier-sdk" / "src" / "main" / "assets" / "model" / "model_metadata.json",
        ROOT / "android" / "classifier-sdk" / "src" / "main" / "assets" / "rules" / "otp_rules.json",
        ROOT / "training" / "data" / "manifests" / "sources.json",
    ]
    out: Dict[str, str] = {}
    for path in candidates:
        if path.exists():
            out[str(path.relative_to(ROOT))] = sha256_file(path)
    model = (
        ROOT
        / "android"
        / "classifier-sdk"
        / "src"
        / "main"
        / "assets"
        / "model"
        / "sms_bytecnn_int8.tflite"
    )
    if model.exists():
        out[str(model.relative_to(ROOT))] = sha256_file(model)
    return out


def scan_internet() -> List[str]:
    hits: List[str] = []
    for manifest in (ROOT / "android").rglob("AndroidManifest.xml"):
        text = manifest.read_text(encoding="utf-8")
        if "android.permission.INTERNET" in text:
            hits.append(str(manifest.relative_to(ROOT)))
    return hits


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit release artifacts and optionally package deliverables."
    )
    parser.add_argument(
        "--package",
        action="store_true",
        help="Package release bundle skeleton into reports/release/.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "reports" / "audit",
        help="Directory for audit JSON outputs.",
    )
    return parser


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    internet = scan_internet()
    hashes = collect_hashes()
    summary: Dict[str, Any] = {
        "release": "0.1.0-framework",
        "status": "FRAMEWORK_ONLY" if not internet else "FAIL",
        "p0": 1 if internet else 0,
        "p1": 0,
        "p2": 0,
        "checksPassed": 0 if internet else 2,
        "checksFailed": len(internet),
        "internetPermissionHits": internet,
        "artifactHashesFile": "artifact_hashes.json",
        "note": "Framework scaffold audit; full PASS requires remote-machine training and device tests.",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "reviewers": [],
    }

    (args.output_dir / "artifact_hashes.json").write_text(
        json.dumps(hashes, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "manifest_permissions.json").write_text(
        json.dumps({"internetHits": internet}, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "audit_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if args.package:
        release_dir = ROOT / "reports" / "release" / "release-0.1.0-framework"
        for sub in ("apk", "sdk", "model", "rules", "source", "reports", "licenses", "checksums"):
            (release_dir / sub).mkdir(parents=True, exist_ok=True)
        readme = release_dir / "README.md"
        readme.write_text(
            "# Framework release skeleton\n\n"
            "APK/AAR/TFLite placeholders. Build on a full Android+TF machine.\n"
            "See docs/异机测试环境安装清单.md\n",
            encoding="utf-8",
        )
        print(f"Packaged skeleton at {release_dir}")

    return 1 if internet else 0


if __name__ == "__main__":
    sys.exit(main())
