"""Tests for split leakage detection."""
from src.leakage import audit_leakage
from src.schema import record_from_dict


def _rec(rid, split, tpl="tpl-a", snd="snd-a", parent=None):
    return record_from_dict(
        {
            "id": rid,
            "text": f"text-{rid}",
            "label": "AD",
            "language": "en",
            "source": "test",
            "source_license": "CC0",
            "sender_group": snd,
            "template_group": tpl,
            "split": split,
            "parent_id": parent,
        }
    )


def test_no_leakage_pass():
    records = [
        _rec("a1", "train", "tpl-train", "snd-1"),
        _rec("a2", "validation", "tpl-val", "snd-2"),
        _rec("a3", "test", "tpl-test", "snd-3"),
    ]
    report = audit_leakage(records)
    assert report["status"] == "PASS"


def test_template_group_leak_detected():
    records = [
        _rec("a1", "train", "tpl-shared", "snd-1"),
        _rec("a2", "test", "tpl-shared", "snd-1"),
    ]
    report = audit_leakage(records)
    assert report["status"] == "FAIL"
    assert any(i["type"] == "template_sender_group_leak" for i in report["issues"])


def test_id_overlap_detected():
    records = [
        _rec("same", "train", "tpl-1", "snd-1"),
        _rec("same", "test", "tpl-2", "snd-2"),
    ]
    report = audit_leakage(records)
    assert report["status"] == "FAIL"
    assert any(i["type"] == "id_overlap" for i in report["issues"])
