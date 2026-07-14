#!/usr/bin/env python3
"""Audit training data sources and licenses."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SEED = 42

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCES = ROOT / "data" / "manifests" / "sources.json"
DEFAULT_OUTPUT = ROOT / "reports" / "sources_audit.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit data sources and licenses from manifests/sources.json."
    )
    parser.add_argument(
        "--sources",
        type=Path,
        default=DEFAULT_SOURCES,
        help="Path to sources manifest JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output audit report JSON path.",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print audit summary to stdout.",
    )
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed.")
    return parser


def audit_sources(manifest: Dict[str, Any], seed: int) -> Dict[str, Any]:
    """Build audit report from sources manifest."""
    sources: List[Dict[str, Any]] = list(manifest.get("sources", []))
    licenses = sorted({str(s.get("license", "UNKNOWN")) for s in sources})
    synthetic_count = sum(1 for s in sources if s.get("is_synthetic"))
    approved = [s for s in sources if s.get("approved_for_git")]
    issues: List[str] = []
    for src in sources:
        if not src.get("id"):
            issues.append("source missing id")
        if not src.get("license"):
            issues.append(f"source {src.get('id', '?')} missing license")

    status = "PASS" if not issues else "WARN"
    return {
        "seed": seed,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_version": manifest.get("version", "unknown"),
        "source_count": len(sources),
        "synthetic_source_count": synthetic_count,
        "approved_for_git_count": len(approved),
        "licenses": licenses,
        "sources": sources,
        "issues": issues,
        "status": status,
    }


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.sources.exists():
        print(f"Sources manifest not found: {args.sources}", file=sys.stderr)
        return 1
    try:
        manifest = json.loads(args.sources.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON in {args.sources}: {exc}", file=sys.stderr)
        return 1

    report = audit_sources(manifest, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.print:
        print(f"Audit status: {report['status']}")
        print(f"Sources: {report['source_count']} (synthetic: {report['synthetic_source_count']})")
        print(f"Licenses: {', '.join(report['licenses'])}")
        if report["issues"]:
            for issue in report["issues"]:
                print(f"  issue: {issue}", file=sys.stderr)

    print(f"Wrote audit report to {args.output}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
