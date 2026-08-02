"""Train-only label correction application with auditable statuses."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from .schema import LABELS, SmsRecord
from .text_quality import text_quality_issues

STATUS_APPLIED = "APPLIED"
STATUS_REMOVED_NEEDS_REVIEW = "REMOVED_NEEDS_REVIEW"
STATUS_UNMATCHED = "UNMATCHED"
STATUS_QUARANTINED = "QUARANTINED"

UNMATCHED_MISSING_ID = "missing_id"
UNMATCHED_TEXT_HASH_MISMATCH = "text_hash_mismatch"
UNMATCHED_CANONICAL_WHITESPACE = "canonical_whitespace_only"

ALLOWED_CORRECTION_STATUSES = {
    "FROZEN_DUAL_HUMAN_ANNOTATED",
    "PROVISIONAL_AUTOMATED_REVIEW",
    "PROVISIONAL_AUTOMATED_MULTI_PASS",
}


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_whitespace_text(text: str) -> str:
    """Only BOM / leading-trailing whitespace / newline canonicalization."""
    return text.replace("\r\n", "\n").replace("\r", "\n").strip("\ufeff").strip()


def load_corrections_manifest(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    status = payload.get("status")
    if status not in ALLOWED_CORRECTION_STATUSES:
        raise ValueError(f"Unsupported corrections status {status!r} in {path}")
    if status == "FROZEN_DUAL_HUMAN_ANNOTATED" and not payload.get(
        "dual_human_evidence_complete", False
    ):
        raise ValueError(
            "FROZEN_DUAL_HUMAN_ANNOTATED requires dual_human_evidence_complete=true"
        )
    corrections = payload.get("corrections", [])
    if not isinstance(corrections, list):
        raise ValueError(f"Invalid corrections list: {path}")
    return payload


def apply_train_only_corrections(
    splits: Mapping[str, Sequence[SmsRecord]],
    corrections_path: Path,
    *,
    forced_quarantine_ids: Optional[Set[str]] = None,
    quarantine_text_failures: bool = True,
) -> Tuple[Dict[str, List[SmsRecord]], List[Dict[str, Any]], Dict[str, Any]]:
    """Apply corrections only to frozen train membership.

    Returns (new_splits, correction_details, stats).
    Validation/test membership and bodies are preserved unchanged.
    """
    forced_quarantine_ids = set(forced_quarantine_ids or ())
    payload = load_corrections_manifest(corrections_path)
    corrections = payload.get("corrections", [])
    by_id = {str(item.get("id", "")): item for item in corrections}
    if "" in by_id or len(by_id) != len(corrections):
        raise ValueError(f"Correction ids must be non-empty and unique: {corrections_path}")

    val_ids = {record.id for record in splits["validation"]}
    test_ids = {record.id for record in splits["test"]}
    illegal = sorted((set(by_id) & val_ids) | (set(by_id) & test_ids))
    if illegal:
        raise ValueError(
            "label corrections target frozen validation/test ids: "
            + ", ".join(illegal[:20])
        )

    train_by_id = {record.id: record for record in splits["train"]}
    details: List[Dict[str, Any]] = []
    kept_train: List[SmsRecord] = []
    quarantined: List[SmsRecord] = []
    changed_labels = 0
    consumed: Set[str] = set()

    for record in splits["train"]:
        correction = by_id.get(record.id)
        force_q = record.id in forced_quarantine_ids
        quality_errors = (
            text_quality_issues(record.text, record_id=record.id)
            if quarantine_text_failures
            else []
        )

        if correction is None:
            if force_q or quality_errors or record.label == "NEEDS_REVIEW":
                reason = (
                    "forced_quarantine"
                    if force_q
                    else ("text_quality" if quality_errors else "needs_review_in_train")
                )
                quarantined.append(record)
                details.append(
                    {
                        "id": record.id,
                        "status": STATUS_QUARANTINED,
                        "reason": reason,
                        "quality_errors": quality_errors,
                        "final_label": "NEEDS_REVIEW",
                    }
                )
            else:
                kept_train.append(record)
            continue

        consumed.add(record.id)
        expected_sha = str(correction.get("text_sha256", ""))
        actual_sha = text_sha256(record.text)
        canonical_sha = text_sha256(canonical_whitespace_text(record.text))
        expected_canonical = str(correction.get("text_sha256_canonical", ""))
        allow_canonical = bool(correction.get("allow_canonical_whitespace"))

        hash_ok = (not expected_sha) or actual_sha == expected_sha
        canonical_only = False
        if not hash_ok:
            if expected_sha == canonical_sha or (
                expected_canonical and expected_canonical == canonical_sha
            ):
                canonical_only = True
                if allow_canonical:
                    hash_ok = True
                else:
                    details.append(
                        {
                            "id": record.id,
                            "status": STATUS_UNMATCHED,
                            "reason": UNMATCHED_CANONICAL_WHITESPACE,
                            "expected_text_sha256": expected_sha,
                            "actual_text_sha256": actual_sha,
                            "canonical_text_sha256": canonical_sha,
                        }
                    )
                    kept_train.append(record)
                    continue
            else:
                details.append(
                    {
                        "id": record.id,
                        "status": STATUS_UNMATCHED,
                        "reason": UNMATCHED_TEXT_HASH_MISMATCH,
                        "expected_text_sha256": expected_sha,
                        "actual_text_sha256": actual_sha,
                    }
                )
                kept_train.append(record)
                continue

        final_label = str(correction.get("final_label", ""))
        if force_q:
            final_label = "NEEDS_REVIEW"

        if final_label == "NEEDS_REVIEW" or quality_errors:
            status = (
                STATUS_REMOVED_NEEDS_REVIEW
                if final_label == "NEEDS_REVIEW" and not quality_errors
                else STATUS_QUARANTINED
            )
            quarantined.append(record)
            details.append(
                {
                    "id": record.id,
                    "status": status,
                    "reason": (
                        "final_label_needs_review"
                        if final_label == "NEEDS_REVIEW"
                        else "text_quality"
                    ),
                    "prior_label": record.label,
                    "final_label": "NEEDS_REVIEW",
                    "quality_errors": quality_errors,
                    "canonical_whitespace_only": canonical_only,
                    "annotator_ids": list(
                        correction.get(
                            "annotator_ids",
                            correction.get("human_annotator_ids", []),
                        )
                    ),
                }
            )
            continue

        if final_label not in LABELS:
            raise ValueError(f"Invalid corrected label for {record.id}: {final_label!r}")

        prior_label = record.label
        if prior_label != final_label:
            changed_labels += 1
        record.label = final_label
        record.annotator_ids = list(
            dict.fromkeys(
                [
                    *record.annotator_ids,
                    *[
                        str(value)
                        for value in correction.get(
                            "annotator_ids",
                            correction.get("human_annotator_ids", []),
                        )
                        if str(value)
                    ],
                ]
            )
        )
        kept_train.append(record)
        details.append(
            {
                "id": record.id,
                "status": STATUS_APPLIED,
                "prior_label": prior_label,
                "final_label": final_label,
                "canonical_whitespace_only": canonical_only,
                "annotator_ids": list(
                    correction.get(
                        "annotator_ids",
                        correction.get("human_annotator_ids", []),
                    )
                ),
            }
        )

    for correction_id, correction in by_id.items():
        if correction_id in consumed:
            continue
        if correction_id in train_by_id:
            record = train_by_id[correction_id]
            details.append(
                {
                    "id": correction_id,
                    "status": STATUS_UNMATCHED,
                    "reason": UNMATCHED_TEXT_HASH_MISMATCH,
                    "expected_text_sha256": correction.get("text_sha256"),
                    "actual_text_sha256": text_sha256(record.text),
                }
            )
        else:
            details.append(
                {
                    "id": correction_id,
                    "status": STATUS_UNMATCHED,
                    "reason": UNMATCHED_MISSING_ID,
                    "expected_text_sha256": correction.get("text_sha256"),
                }
            )

    new_splits = {
        "train": kept_train,
        "validation": list(splits["validation"]),
        "test": list(splits["test"]),
        "quarantine": quarantined,
    }
    unmatched_by_reason: Dict[str, int] = {}
    for row in details:
        if row["status"] == STATUS_UNMATCHED:
            reason = str(row.get("reason", "unknown"))
            unmatched_by_reason[reason] = unmatched_by_reason.get(reason, 0) + 1
    stats = {
        "manifest": str(corrections_path).replace("\\", "/"),
        "manifest_status": payload.get("status"),
        "claim_allowed": bool(payload.get("claim_allowed", False)),
        "applied": sum(1 for row in details if row["status"] == STATUS_APPLIED),
        "removed_needs_review": sum(
            1 for row in details if row["status"] == STATUS_REMOVED_NEEDS_REVIEW
        ),
        "unmatched": sum(1 for row in details if row["status"] == STATUS_UNMATCHED),
        "quarantined": sum(1 for row in details if row["status"] == STATUS_QUARANTINED),
        "changed_labels": changed_labels,
        "unmatched_by_reason": unmatched_by_reason,
    }
    return new_splits, details, stats
