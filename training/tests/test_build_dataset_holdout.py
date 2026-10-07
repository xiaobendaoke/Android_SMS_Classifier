"""Tests for connected-component holdout exclusion."""
import hashlib
import json

from scripts.build_dataset import (
    apply_label_corrections,
    exclude_holdout_components,
)
from src.schema import record_from_dict


def _record(rid: str, template: str, sender: str):
    return record_from_dict(
        {
            "id": rid,
            "text": f"unique content {rid} {template}",
            "label": "TRANSACTION",
            "language": "zh",
            "source": "test",
            "source_license": "internal-test",
            "sender_group": sender,
            "template_group": template,
            "split": "train",
        }
    )


def test_holdout_excludes_entire_connected_component():
    records = [
        _record("reserved", "shared-template", "sender-a"),
        _record("related", "shared-template", "sender-b"),
        _record("kept", "independent-template", "sender-c"),
    ]
    kept, removed = exclude_holdout_components(records, {"reserved"})
    assert removed == 2
    assert [record.id for record in kept] == ["kept"]


def test_frozen_label_corrections_change_or_remove_train_rows(tmp_path):
    changed = _record("changed", "t1", "s1")
    removed = _record("removed", "t2", "s2")
    manifest = tmp_path / "corrections.json"
    manifest.write_text(
        json.dumps(
            {
                "status": "PROVISIONAL_AUTOMATED_REVIEW",
                "claim_allowed": False,
                "dual_human_evidence_complete": False,
                "corrections": [
                    {
                        "id": changed.id,
                        "text_sha256": hashlib.sha256(
                            changed.text.encode("utf-8")
                        ).hexdigest(),
                        "final_label": "AD",
                        "human_annotator_ids": ["A", "B"],
                    },
                    {
                        "id": removed.id,
                        "text_sha256": hashlib.sha256(
                            removed.text.encode("utf-8")
                        ).hexdigest(),
                        "final_label": "NEEDS_REVIEW",
                        "human_annotator_ids": ["A", "B", "C"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    kept, stats = apply_label_corrections([changed, removed], manifest)
    assert [record.id for record in kept] == ["changed"]
    assert kept[0].label == "AD"
    assert kept[0].annotator_ids == ["A", "B"]
    assert stats["changed_labels"] == 1
    assert stats["removed_needs_review"] == 1


def test_stale_text_correction_is_reported_without_relabeling(tmp_path):
    record = _record("stale", "t1", "s1")
    manifest = tmp_path / "corrections.json"
    manifest.write_text(
        json.dumps(
            {
                "status": "PROVISIONAL_AUTOMATED_REVIEW",
                "claim_allowed": False,
                "dual_human_evidence_complete": False,
                "corrections": [
                    {
                        "id": record.id,
                        "text_sha256": hashlib.sha256(
                            b"older text revision"
                        ).hexdigest(),
                        "final_label": "AD",
                        "human_annotator_ids": ["A", "B"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    kept, stats = apply_label_corrections([record], manifest)

    assert kept == [record]
    assert record.label == "TRANSACTION"
    assert stats["applied_ids"] == 0
    assert stats["unmatched_ids"] == ["stale"]
    assert stats["unmatched_count"] == 1
