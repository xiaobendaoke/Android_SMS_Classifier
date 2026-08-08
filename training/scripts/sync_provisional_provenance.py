#!/usr/bin/env python3
"""Downgrade boundary provenance to provisional when dual-human evidence is absent."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT.parent / "docs" / "labeling-guide.md"
ANNOTATION = ROOT / "data" / "manifests" / "boundary_annotation_v1.json"
CORRECTIONS = ROOT / "data" / "manifests" / "boundary_label_corrections_v1.json"
CONFLICTS = (
    ROOT / "data" / "interim" / "annotation" / "boundary_v1" / "boundary_conflicts.csv"
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    guide_sha = sha256_file(GUIDE) if GUIDE.exists() else None
    completed_sha = sha256_file(CONFLICTS) if CONFLICTS.exists() else None

    manifest = json.loads(ANNOTATION.read_text(encoding="utf-8"))
    manifest["status"] = "PROVISIONAL_AUTOMATED_REVIEW"
    manifest["claim_allowed"] = False
    manifest["dual_human_evidence_complete"] = False
    manifest["annotation_guide_sha256"] = guide_sha
    dual = manifest.get("dual_annotation", {})
    if "blank_conflicts_sha256" not in dual:
        dual["blank_conflicts_sha256"] = dual.get("conflicts_sha256")
    dual["status"] = "PROVISIONAL_AUTOMATED_REVIEW"
    dual["completed_conflicts_sha256"] = completed_sha
    if completed_sha:
        dual["conflicts_sha256"] = completed_sha
    manifest["dual_annotation"] = dual
    if "corrections" in manifest:
        manifest["corrections"]["status"] = "PROVISIONAL_AUTOMATED_REVIEW"
        manifest["corrections"]["claim_allowed"] = False
        if CORRECTIONS.exists():
            manifest["corrections"]["sha256"] = sha256_file(CORRECTIONS)
    ANNOTATION.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    corrections = json.loads(CORRECTIONS.read_text(encoding="utf-8"))
    corrections["status"] = "PROVISIONAL_AUTOMATED_REVIEW"
    corrections["claim_allowed"] = False
    corrections["dual_human_evidence_complete"] = False
    corrections["annotation_guide_sha256"] = guide_sha
    corrections["completed_conflicts_sha256"] = completed_sha
    CORRECTIONS.write_text(
        json.dumps(corrections, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "annotation_status": manifest["status"],
                "dual_status": dual["status"],
                "claim_allowed": False,
                "completed_conflicts_sha256": completed_sha,
                "annotation_guide_sha256": guide_sha,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
