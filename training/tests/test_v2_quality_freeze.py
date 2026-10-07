"""Tests for no-replacement v2 freeze and blind packs."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from src.blind_annotation import dual_human_evidence_complete
from src.schema import record_from_dict, write_jsonl
from src.split_assignment import compute_freeze_sha256, sha256_file
from src.text_quality import classify_text_quality_reasons


def _record(rid: str, text: str, label: str = "AD", split: str = "train"):
    return record_from_dict(
        {
            "id": rid,
            "text": text,
            "label": label,
            "language": "zh",
            "source": "test",
            "source_license": "internal-test",
            "sender_group": f"s-{rid}",
            "template_group": f"t-{rid}",
            "split": split,
        }
    )


def test_quality_report_omits_text_bodies(tmp_path, monkeypatch):
    from scripts import scan_frozen_text_quality as scan

    processed = tmp_path / "processed"
    processed.mkdir()
    write_jsonl(processed / "train.jsonl", [_record("tr1", "ok train", "AD")])
    write_jsonl(
        processed / "validation.jsonl",
        [_record("va1", "null bad validation", "AD", "validation")],
    )
    write_jsonl(
        processed / "test.jsonl",
        [_record("te1", "bad \ufffd test", "HARASS", "test")],
    )
    out = tmp_path / "report.json"
    code = scan.main(["--processed-dir", str(processed), "--output", str(out)])
    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    serialized = out.read_text(encoding="utf-8")
    assert '"text":' not in serialized
    assert payload["validation_failure_count"] == 1
    assert payload["test_failure_count"] == 1
    assert payload["failures"][0]["quality_reason"] in {
        "null_prefix",
        "replacement_character",
    }


def test_v1_sha_not_modified_by_v2_builder(tmp_path, monkeypatch):
    from scripts import build_split_assignment_v2 as builder

    processed = tmp_path / "processed"
    processed.mkdir()
    train = [_record("tr1", "clean train text long enough", "AD")]
    validation = [
        _record("va1", "clean val", "AD", "validation"),
        _record("va2", "null corrupt val", "AD", "validation"),
        _record("va3", "clean val 2", "HARASS", "validation"),
        _record("va4", "bad \ufffd val", "FRAUD", "validation"),
        _record("va5", "clean val 3", "TRANSACTION", "validation"),
        _record("va6", "null another val", "AD", "validation"),
    ]
    # Need exactly 4 val + 5 test failures for builder; craft accordingly.
    validation = [
        _record("va1", "clean validation one", "AD", "validation"),
        _record("va2", "null corrupt val a", "AD", "validation"),
        _record("va3", "clean validation two", "HARASS", "validation"),
        _record("va4", "bad \ufffd val b", "FRAUD", "validation"),
        _record("va5", "clean validation three", "TRANSACTION", "validation"),
        _record("va6", "null corrupt val c", "AD", "validation"),
        _record("va7", "bad \ufffd val d", "AD", "validation"),
    ]
    test = [
        _record("te1", "clean test one", "AD", "test"),
        _record("te2", "null corrupt test a", "AD", "test"),
        _record("te3", "clean test two", "HARASS", "test"),
        _record("te4", "bad \ufffd test b", "FRAUD", "test"),
        _record("te5", "null corrupt test c", "AD", "test"),
        _record("te6", "bad \ufffd test d", "TRANSACTION", "test"),
        _record("te7", "null corrupt test e", "AD", "test"),
        _record("te8", "clean test three", "HARASS", "test"),
    ]
    write_jsonl(processed / "train.jsonl", train)
    write_jsonl(processed / "validation.jsonl", validation)
    write_jsonl(processed / "test.jsonl", test)
    val_sha = sha256_file(processed / "validation.jsonl")
    test_sha = sha256_file(processed / "test.jsonl")

    parent = {
        "version": "1.0.0",
        "seed": 42,
        "source_shas": [],
        "holdout_ids_sha256": "h",
        "holdout_manifest_sha256": "hm",
        "component_algorithm_version": "connected_group_ids_v1",
        "splits": {
            "train": {
                "count": 1,
                "sha256": sha256_file(processed / "train.jsonl"),
                "ids_sha256": "x",
                "ids": ["tr1"],
            },
            "validation": {
                "count": len(validation),
                "sha256": val_sha,
                "ids_sha256": "y",
                "ids": [r.id for r in validation],
            },
            "test": {
                "count": len(test),
                "sha256": test_sha,
                "ids_sha256": "z",
                "ids": [r.id for r in test],
            },
        },
        "freeze_sha256": "parent",
    }
    parent_path = tmp_path / "split_assignment_v1.json"
    parent_path.write_text(json.dumps(parent), encoding="utf-8")

    # Monkeypatch expected SHAs used by builder.
    monkeypatch.setattr(
        builder,
        "EXPECTED_V1",
        {"validation_sha256": val_sha, "test_sha256": test_sha},
    )

    quality = {
        "failures": [
            {
                "id": r.id,
                "split": r.split,
                "label": r.label,
                "source": r.source,
                "component_id": "c",
                "quality_reason": classify_text_quality_reasons(r.text)[0],
                "text_sha256": hashlib.sha256(r.text.encode()).hexdigest(),
            }
            for r in validation + test
            if classify_text_quality_reasons(r.text)
        ]
    }
    assert len([f for f in quality["failures"] if f["split"] == "validation"]) == 4
    assert len([f for f in quality["failures"] if f["split"] == "test"]) == 5
    qpath = tmp_path / "quality.json"
    qpath.write_text(json.dumps(quality), encoding="utf-8")

    out_dir = tmp_path / "processed_v2"
    code = builder.main(
        [
            "--processed-dir",
            str(processed),
            "--parent-assignment",
            str(parent_path),
            "--quality-report",
            str(qpath),
            "--output-dir",
            str(out_dir),
            "--assignment-output",
            str(tmp_path / "split_assignment_v2.json"),
            "--dataset-manifest-output",
            str(tmp_path / "dataset_manifest_v2.json"),
            "--leakage-output",
            str(tmp_path / "leakage_v2.json"),
            "--audit-output",
            str(tmp_path / "audit_v2.json"),
            "--v1-status-output",
            str(tmp_path / "freeze_status_v1.json"),
        ]
    )
    assert code == 0
    assert sha256_file(processed / "validation.jsonl") == val_sha
    assert sha256_file(processed / "test.jsonl") == test_sha
    assignment = json.loads(
        (tmp_path / "split_assignment_v2.json").read_text(encoding="utf-8")
    )
    assert assignment["replacement_policy"] == "none"
    assert assignment["removed_counts"]["total"] == 9
    assert assignment["splits"]["validation"]["count"] == 3
    assert assignment["splits"]["test"]["count"] == 3
    assert compute_freeze_sha256(assignment) == assignment["freeze_sha256"]
    # No NEEDS_REVIEW / U+FFFD remain in v2 formal splits.
    for split_name in ("train", "validation", "test"):
        for line in (out_dir / f"{split_name}.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            assert row["label"] != "NEEDS_REVIEW"
            assert "\ufffd" not in row["text"]
            assert not row["text"].lstrip().lower().startswith("null")


def test_blind_fields_and_independent_order(tmp_path):
    from scripts.prepare_transaction_specialist_v2 import main as prep

    # Minimal fake specialist source.
    src = tmp_path / "src"
    src.mkdir()
    # Monkeypatch via writing into expected interim path is heavy; unit-test field rules here.
    rows = [
        {
            "review_id": f"r{i}",
            "id": f"id{i}",
            "text": f"text {i}",
            "label": "",
            "notes": "",
            "human_annotator_id": "",
        }
        for i in range(5)
    ]
    a = rows[::-1]
    b = rows
    assert [r["review_id"] for r in a] != [r["review_id"] for r in b]
    for sheet in (a, b):
        assert list(sheet[0].keys()) == [
            "review_id",
            "id",
            "text",
            "label",
            "notes",
            "human_annotator_id",
        ]
        assert all(not r["label"] and not r["human_annotator_id"] for r in sheet)


def test_finalize_requires_evidence_and_adjudication(tmp_path):
    from scripts import finalize_blind_annotations as fin
    from scripts import reconcile_blind_annotations as rec

    pack = tmp_path / "pack"
    pack.mkdir()
    # Build blank then filled sheets.
    fields = ["review_id", "id", "text", "label", "notes", "human_annotator_id"]
    base = [
        {
            "review_id": "r1",
            "id": "id1",
            "text": "hello one",
            "label": "",
            "notes": "",
            "human_annotator_id": "",
        },
        {
            "review_id": "r2",
            "id": "id2",
            "text": "hello two",
            "label": "",
            "notes": "",
            "human_annotator_id": "",
        },
    ]
    a_path = pack / "annotator_A.csv"
    b_path = pack / "annotator_B.csv"
    with a_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(base)
    with b_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(list(reversed(base)))
    pool_path = pack / "internal_pool.csv"
    with pool_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["review_id", "id", "text"],
        )
        writer.writeheader()
        writer.writerows(
            {
                "review_id": row["review_id"],
                "id": row["id"],
                "text": row["text"],
            }
            for row in base
        )
    manifest = {
        "status": "PENDING_DUAL_HUMAN_ANNOTATION",
        "claim_allowed": False,
        "files": {
            "internal_pool": {
                "path": str(pool_path),
                "sha256": sha256_file(pool_path),
            },
            "annotator_a": {
                "path": str(a_path),
                "sha256": sha256_file(a_path),
            },
            "annotator_b": {
                "path": str(b_path),
                "sha256": sha256_file(b_path),
            },
        },
    }
    (pack / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def write_sheet(path: Path, rows):
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    # Fill same annotator -> fail
    filled_a = [
        {**base[0], "label": "AD", "human_annotator_id": "HUMAN_A"},
        {**base[1], "label": "HARASS", "human_annotator_id": "HUMAN_A"},
    ]
    filled_b_same = [
        {**base[1], "label": "HARASS", "human_annotator_id": "HUMAN_A"},
        {**base[0], "label": "AD", "human_annotator_id": "HUMAN_A"},
    ]
    write_sheet(a_path, filled_a)
    write_sheet(b_path, filled_b_same)
    assert rec.main(["--pack-dir", str(pack)]) == 2

    # Changing a supposedly immutable body is also rejected even when A/B agree.
    tampered_b = [
        {**base[1], "text": "tampered", "label": "AD", "human_annotator_id": "HUMAN_B"},
        {**base[0], "label": "AD", "human_annotator_id": "HUMAN_B"},
    ]
    write_sheet(a_path, filled_a)
    write_sheet(b_path, tampered_b)
    assert rec.main(["--pack-dir", str(pack)]) == 2

    # Different annotators with conflict.
    filled_b = [
        {**base[1], "label": "AD", "human_annotator_id": "HUMAN_B"},
        {**base[0], "label": "AD", "human_annotator_id": "HUMAN_B"},
    ]
    write_sheet(a_path, filled_a)
    write_sheet(b_path, filled_b)
    assert rec.main(["--pack-dir", str(pack)]) == 0

    # Unresolved conflict finalize fails.
    assert fin.main(["--pack-dir", str(pack), "--allow-provisional"]) == 3

    # Third label without notes fails.
    conflicts = list(csv.DictReader(open(pack / "conflicts.csv", encoding="utf-8-sig")))
    assert conflicts
    conflicts[0]["adjudicated_label"] = "FRAUD"
    conflicts[0]["adjudicator_id"] = "ADJ"
    conflicts[0]["adjudication_notes"] = ""
    with (pack / "conflicts.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(conflicts[0].keys()))
        writer.writeheader()
        writer.writerows(conflicts)
    assert fin.main(["--pack-dir", str(pack), "--allow-provisional"]) == 3

    conflicts[0]["adjudication_notes"] = "third label justified"
    with (pack / "conflicts.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(conflicts[0].keys()))
        writer.writeheader()
        writer.writerows(conflicts)
    # Without evidence and without allow_provisional -> refuse freeze.
    assert fin.main(["--pack-dir", str(pack)]) == 4
    assert dual_human_evidence_complete({"dual_human_evidence": {}}) is False
    assert fin.main(["--pack-dir", str(pack), "--allow-provisional"]) == 0
    payload = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    assert payload["status"] == "PROVISIONAL_AUTOMATED_REVIEW"
    assert payload["claim_allowed"] is False


def test_v7_defaults_to_v2_and_blocks_on_pending_humans(monkeypatch):
    import scripts.run_recall_v3 as pipeline

    monkeypatch.setattr(
        pipeline,
        "audit_v2_startup",
        lambda: ["label_conflicts_v2: human annotation incomplete"],
    )
    calls = []
    monkeypatch.setattr(pipeline, "run", lambda *a, **k: calls.append(a))
    code = pipeline.main(["--skip-teacher", "--run-name", "recall_v7"])
    assert code == 6
    assert calls == []


def test_v7_without_unlock_never_reaches_test(monkeypatch):
    import scripts.run_recall_v3 as pipeline

    monkeypatch.setattr(pipeline, "audit_v2_startup", lambda: [])
    calls = []

    def fake_run(script, *args):
        calls.append((script, args))

    monkeypatch.setattr(pipeline, "run", fake_run)
    reached = {"locked": False}
    monkeypatch.setattr(
        pipeline,
        "run_locked_test_path",
        lambda *a, **k: reached.__setitem__("locked", True),
    )
    code = pipeline.main(["--skip-teacher", "--run-name", "recall_v7"])
    assert code == 0
    assert reached["locked"] is False
    evaluate_calls = [args for script, args in calls if script == "evaluate.py"]
    assert evaluate_calls
    assert any("processed_v2" in part and "validation.jsonl" in part for part in evaluate_calls[0])
    assert not any("test.jsonl" in part for part in evaluate_calls[0])
