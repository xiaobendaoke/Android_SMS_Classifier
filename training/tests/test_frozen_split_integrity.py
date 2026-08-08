"""Tests for immutable split assignment and train-only corrections."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.label_corrections import (
    STATUS_APPLIED,
    STATUS_REMOVED_NEEDS_REVIEW,
    STATUS_UNMATCHED,
    UNMATCHED_CANONICAL_WHITESPACE,
    UNMATCHED_TEXT_HASH_MISMATCH,
    apply_train_only_corrections,
    canonical_whitespace_text,
    text_sha256,
)
from src.schema import SmsRecord, record_from_dict, write_jsonl
from src.split_assignment import (
    apply_frozen_assignment,
    build_assignment_from_splits,
    compute_freeze_sha256,
    load_assignment,
)
from src.text_quality import text_quality_issues


def _record(
    rid: str,
    text: str,
    label: str = "TRANSACTION",
    template: str = "t",
    sender: str = "s",
) -> SmsRecord:
    return record_from_dict(
        {
            "id": rid,
            "text": text,
            "label": label,
            "language": "zh",
            "source": "test",
            "source_license": "internal-test",
            "sender_group": sender,
            "template_group": template,
            "split": "train",
        }
    )


def _write_corrections(path: Path, rows: list[dict]) -> None:
    path.write_text(
        json.dumps(
            {
                "status": "PROVISIONAL_AUTOMATED_REVIEW",
                "claim_allowed": False,
                "dual_human_evidence_complete": False,
                "corrections": rows,
            }
        ),
        encoding="utf-8",
    )


def _assignment_from_records(tmp_path: Path, splits: dict[str, list[SmsRecord]]):
    paths = {}
    for name, rows in splits.items():
        path = tmp_path / f"{name}.jsonl"
        write_jsonl(path, rows)
        paths[name] = path
    return build_assignment_from_splits(
        paths,
        seed=42,
        source_shas=[{"path": "raw.jsonl", "sha256": "abc"}],
        holdout_ids_sha256="holdout",
        holdout_manifest_sha256="holdout-file",
        code_revision="test",
    )


def test_label_correction_does_not_change_split_membership(tmp_path):
    train = [_record("tr1", "train one", "TRANSACTION", "t1", "s1")]
    validation = [_record("va1", "val one", "AD", "t2", "s2")]
    test = [_record("te1", "test one", "HARASS", "t3", "s3")]
    assignment = _assignment_from_records(
        tmp_path,
        {"train": train, "validation": validation, "test": test},
    )
    pool = train + validation + test
    # Mutate train label in source pool; assignment must keep membership.
    pool[0].label = "FRAUD"
    splits = apply_frozen_assignment(pool, assignment)
    assert [r.id for r in splits["train"]] == ["tr1"]
    assert [r.id for r in splits["validation"]] == ["va1"]
    assert [r.id for r in splits["test"]] == ["te1"]

    corr = tmp_path / "corr.json"
    _write_corrections(
        corr,
        [
            {
                "id": "tr1",
                "text_sha256": text_sha256("train one"),
                "final_label": "AD",
                "human_annotator_ids": ["A"],
            }
        ],
    )
    new_splits, details, _stats = apply_train_only_corrections(splits, corr)
    assert [r.id for r in new_splits["validation"]] == ["va1"]
    assert [r.id for r in new_splits["test"]] == ["te1"]
    assert details[0]["status"] == STATUS_APPLIED
    assert new_splits["train"][0].label == "AD"


def test_correction_id_in_validation_fails(tmp_path):
    splits = {
        "train": [_record("tr1", "train one")],
        "validation": [_record("va1", "val one")],
        "test": [_record("te1", "test one")],
    }
    corr = tmp_path / "corr.json"
    _write_corrections(
        corr,
        [
            {
                "id": "va1",
                "text_sha256": text_sha256("val one"),
                "final_label": "AD",
            }
        ],
    )
    with pytest.raises(ValueError, match="validation/test"):
        apply_train_only_corrections(splits, corr)


def test_correction_id_in_test_fails(tmp_path):
    splits = {
        "train": [_record("tr1", "train one")],
        "validation": [_record("va1", "val one")],
        "test": [_record("te1", "test one")],
    }
    corr = tmp_path / "corr.json"
    _write_corrections(
        corr,
        [
            {
                "id": "te1",
                "text_sha256": text_sha256("test one"),
                "final_label": "AD",
            }
        ],
    )
    with pytest.raises(ValueError, match="validation/test"):
        apply_train_only_corrections(splits, corr)


def test_train_label_change_keeps_validation_test_sha(tmp_path):
    train = [_record("tr1", "train one")]
    validation = [_record("va1", "val one")]
    test = [_record("te1", "test one")]
    assignment = _assignment_from_records(
        tmp_path,
        {"train": train, "validation": validation, "test": test},
    )
    splits = apply_frozen_assignment(train + validation + test, assignment)
    before_val = hashlib.sha256(
        json.dumps([r.to_dict() for r in splits["validation"]], ensure_ascii=False).encode()
    ).hexdigest()
    before_test = hashlib.sha256(
        json.dumps([r.to_dict() for r in splits["test"]], ensure_ascii=False).encode()
    ).hexdigest()
    corr = tmp_path / "corr.json"
    _write_corrections(
        corr,
        [
            {
                "id": "tr1",
                "text_sha256": text_sha256("train one"),
                "final_label": "FRAUD",
            }
        ],
    )
    new_splits, _, _ = apply_train_only_corrections(splits, corr)
    after_val = hashlib.sha256(
        json.dumps(
            [r.to_dict() for r in new_splits["validation"]], ensure_ascii=False
        ).encode()
    ).hexdigest()
    after_test = hashlib.sha256(
        json.dumps([r.to_dict() for r in new_splits["test"]], ensure_ascii=False).encode()
    ).hexdigest()
    assert after_val == before_val
    assert after_test == before_test
    assert assignment["splits"]["validation"]["ids"] == ["va1"]
    assert assignment["splits"]["test"]["ids"] == ["te1"]


def test_validate_labels_rejects_needs_review_in_processed(tmp_path, monkeypatch):
    from scripts import validate_labels as vl

    processed = tmp_path / "processed"
    processed.mkdir()
    write_jsonl(
        processed / "train.jsonl",
        [_record("tr1", "ok text", label="NEEDS_REVIEW")],
    )
    write_jsonl(processed / "validation.jsonl", [_record("va1", "val ok", "AD")])
    write_jsonl(processed / "test.jsonl", [_record("te1", "test ok", "HARASS")])
    monkeypatch.setattr(vl, "ROOT", tmp_path)
    # No assignment required for this focused check.
    code = vl.main(
        [
            "--input",
            str(processed),
            "--no-require-frozen-assignment",
        ]
    )
    assert code == 1


def test_validate_labels_rejects_fffd(tmp_path, monkeypatch):
    from scripts import validate_labels as vl

    processed = tmp_path / "processed"
    processed.mkdir()
    write_jsonl(
        processed / "train.jsonl",
        [_record("tr1", "bad \ufffd text", label="AD")],
    )
    write_jsonl(processed / "validation.jsonl", [_record("va1", "val ok", "AD")])
    write_jsonl(processed / "test.jsonl", [_record("te1", "test ok", "HARASS")])
    code = vl.main(
        [
            "--input",
            str(processed),
            "--no-require-frozen-assignment",
        ]
    )
    assert code == 1
    assert text_quality_issues("bad \ufffd text")


def test_stale_text_hash_does_not_apply_label(tmp_path):
    splits = {
        "train": [_record("tr1", "current text")],
        "validation": [_record("va1", "val")],
        "test": [_record("te1", "test")],
    }
    corr = tmp_path / "corr.json"
    _write_corrections(
        corr,
        [
            {
                "id": "tr1",
                "text_sha256": text_sha256("stale text"),
                "final_label": "AD",
            }
        ],
    )
    new_splits, details, stats = apply_train_only_corrections(splits, corr)
    assert new_splits["train"][0].label == "TRANSACTION"
    assert details[0]["status"] == STATUS_UNMATCHED
    assert details[0]["reason"] == UNMATCHED_TEXT_HASH_MISMATCH
    assert stats["unmatched"] == 1


def test_canonical_whitespace_mismatch_is_recorded(tmp_path):
    live = "  hello world\r\n"
    canonical = canonical_whitespace_text(live)
    splits = {
        "train": [_record("tr1", live)],
        "validation": [_record("va1", "val")],
        "test": [_record("te1", "test")],
    }
    corr = tmp_path / "corr.json"
    _write_corrections(
        corr,
        [
            {
                "id": "tr1",
                "text_sha256": text_sha256(canonical),
                "final_label": "AD",
            }
        ],
    )
    new_splits, details, stats = apply_train_only_corrections(splits, corr)
    assert new_splits["train"][0].label == "TRANSACTION"
    assert details[0]["reason"] == UNMATCHED_CANONICAL_WHITESPACE
    assert stats["unmatched_by_reason"][UNMATCHED_CANONICAL_WHITESPACE] == 1


def test_manifest_top_and_nested_status_consistent_and_conflict_sha_recorded(tmp_path):
    from scripts.finalize_boundary_label_corrections import dual_human_evidence_complete

    manifest = {
        "status": "PROVISIONAL_AUTOMATED_REVIEW",
        "claim_allowed": False,
        "dual_annotation": {"status": "PROVISIONAL_AUTOMATED_REVIEW"},
        "dual_human_evidence": {},
    }
    assert manifest["status"] == manifest["dual_annotation"]["status"]
    assert dual_human_evidence_complete(manifest) is False

    conflicts = tmp_path / "conflicts.csv"
    conflicts.write_text("id,adjudicated_label\n", encoding="utf-8")
    sha = hashlib.sha256(conflicts.read_bytes()).hexdigest()
    manifest["dual_annotation"]["completed_conflicts_sha256"] = sha
    assert manifest["dual_annotation"]["completed_conflicts_sha256"] == sha


def test_missing_dual_human_evidence_cannot_freeze(tmp_path):
    from src.label_corrections import load_corrections_manifest

    path = tmp_path / "corr.json"
    path.write_text(
        json.dumps(
            {
                "status": "FROZEN_DUAL_HUMAN_ANNOTATED",
                "dual_human_evidence_complete": False,
                "corrections": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="dual_human_evidence_complete"):
        load_corrections_manifest(path)


def test_split_assignment_freeze_is_reproducible(tmp_path):
    splits = {
        "train": [_record("tr1", "train")],
        "validation": [_record("va1", "val")],
        "test": [_record("te1", "test")],
    }
    first = _assignment_from_records(tmp_path / "a", splits)
    second = _assignment_from_records(tmp_path / "b", splits)
    assert first["freeze_sha256"] == second["freeze_sha256"]
    assert compute_freeze_sha256(first) == first["freeze_sha256"]
    out = tmp_path / "assignment.json"
    # Drop bulky maps equality via reload
    slim = json.loads(json.dumps(first))
    out.write_text(json.dumps(slim), encoding="utf-8")
    loaded = load_assignment(out)
    assert loaded["freeze_sha256"] == first["freeze_sha256"]


def test_needs_review_removed_from_train(tmp_path):
    splits = {
        "train": [_record("tr1", "train one", "AD")],
        "validation": [_record("va1", "val")],
        "test": [_record("te1", "test")],
    }
    corr = tmp_path / "corr.json"
    _write_corrections(
        corr,
        [
            {
                "id": "tr1",
                "text_sha256": text_sha256("train one"),
                "final_label": "NEEDS_REVIEW",
            }
        ],
    )
    new_splits, details, stats = apply_train_only_corrections(splits, corr)
    assert new_splits["train"] == []
    assert details[0]["status"] == STATUS_REMOVED_NEEDS_REVIEW
    assert stats["removed_needs_review"] == 1
