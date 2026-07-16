#!/usr/bin/env python3
"""Release audit: permissions, artifacts, and optional packaging."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
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
        ROOT / "android" / "classifier-sdk" / "src" / "main" / "assets" / "model" / "sms_bytecnn_int8.tflite",
        ROOT / "training" / "artifacts" / "student" / "sms_bytecnn_int8.tflite",
        ROOT / "android" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk",
        ROOT / "android" / "classifier-sdk" / "build" / "outputs" / "aar" / "classifier-sdk-release.aar",
    ]
    out: Dict[str, str] = {}
    for path in candidates:
        if path.exists() and path.is_file():
            out[str(path.relative_to(ROOT)).replace("\\", "/")] = sha256_file(path)
    return out


def scan_internet() -> List[str]:
    hits: List[str] = []
    for manifest in (ROOT / "android").rglob("AndroidManifest.xml"):
        text = manifest.read_text(encoding="utf-8")
        if "android.permission.INTERNET" in text:
            hits.append(str(manifest.relative_to(ROOT)).replace("\\", "/"))
    return hits


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit release artifacts and optionally package deliverables."
    )
    parser.add_argument(
        "--package",
        action="store_true",
        help="Package release bundle into reports/release/.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "reports" / "audit",
        help="Directory for audit JSON outputs.",
    )
    return parser


def package_release(hashes: Dict[str, str]) -> Path:
    release_dir = ROOT / "reports" / "release" / "release-0.2.0-ml-pipeline"
    for sub in ("apk", "sdk", "model", "rules", "source", "reports", "licenses", "checksums"):
        (release_dir / sub).mkdir(parents=True, exist_ok=True)

    copies = [
        (
            ROOT / "android" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk",
            release_dir / "apk" / "app-debug.apk",
        ),
        (
            ROOT / "android" / "classifier-sdk" / "build" / "outputs" / "aar" / "classifier-sdk-release.aar",
            release_dir / "sdk" / "classifier-sdk-release.aar",
        ),
        (
            ROOT / "android" / "classifier-sdk" / "src" / "main" / "assets" / "model" / "sms_bytecnn_int8.tflite",
            release_dir / "model" / "sms_bytecnn_int8.tflite",
        ),
        (
            ROOT / "android" / "classifier-sdk" / "src" / "main" / "assets" / "model" / "model_metadata.json",
            release_dir / "model" / "model_metadata.json",
        ),
    ]
    rules_src = ROOT / "android" / "classifier-sdk" / "src" / "main" / "assets" / "rules"
    if rules_src.exists():
        for path in rules_src.glob("*.json"):
            shutil.copy2(path, release_dir / "rules" / path.name)

    for src, dst in copies:
        if src.exists():
            shutil.copy2(src, dst)

    for name in (
        "performance-report.md",
        "multilingual-report.md",
        "adversarial-report.md",
        "release-audit-report.md",
    ):
        doc = ROOT / "docs" / name
        if doc.exists():
            shutil.copy2(doc, release_dir / "reports" / name)

    (release_dir / "checksums" / "artifact_hashes.json").write_text(
        json.dumps(hashes, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (release_dir / "README.md").write_text(
        "# Release 0.2.0-ml-pipeline\n\n"
        "- Offline Demo APK + classifier-sdk AAR + INT8 TFLite\n"
        "- Synthetic training data only; transaction recall ≥98% NOT claimed\n"
        "- No INTERNET permission; no cloud classification\n"
        "- Device PSS/latency acceptance still requires 4GB/6GB handsets\n",
        encoding="utf-8",
    )
    return release_dir


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    internet = scan_internet()
    hashes = collect_hashes()
    has_model = any("sms_bytecnn_int8.tflite" in k for k in hashes)
    has_apk = any(k.endswith("app-debug.apk") for k in hashes)

    leakage_path = ROOT / "training" / "reports" / "metrics" / "dataset_leakage.json"
    leakage_status = "MISSING"
    if leakage_path.exists():
        try:
            leakage_status = json.loads(leakage_path.read_text(encoding="utf-8")).get(
                "status", "UNKNOWN"
            )
        except json.JSONDecodeError:
            leakage_status = "INVALID"

    status = "FAIL" if internet else ("PASS_ENGINEERING" if has_model else "FRAMEWORK_ONLY")
    if leakage_status == "FAIL":
        status = "FAIL_LEAKAGE"

    summary: Dict[str, Any] = {
        "release": "0.2.1-p0-fixes",
        "status": status,
        "p0": (1 if internet else 0) + (1 if leakage_status == "FAIL" else 0),
        "p1": 0 if has_model else 1,
        "p2": 0 if has_apk else 1,
        "checksPassed": (
            (0 if internet else 1)
            + (1 if has_model else 0)
            + (1 if has_apk else 0)
            + (1 if leakage_status == "PASS" else 0)
        ),
        "checksFailed": len(internet) + (1 if leakage_status == "FAIL" else 0),
        "internetPermissionHits": internet,
        "datasetLeakage": leakage_status,
        "artifactHashesFile": "artifact_hashes.json",
        "hasInt8Model": has_model,
        "hasDebugApk": has_apk,
        "note": (
            "Engineering closed-loop on synthetic data after P0 leakage fixes. "
            "Do NOT claim transaction recall >=98% without frozen real labeled test set + device reports."
        ),
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
        release_dir = package_release(hashes)
        print(f"Packaged at {release_dir}")

    return 1 if internet else 0


if __name__ == "__main__":
    sys.exit(main())
