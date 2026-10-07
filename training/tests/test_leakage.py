"""Tests for split leakage detection."""
from src.leakage import audit_leakage
from src.schema import record_from_dict
from src.split_groups import split_groups


def _rec(rid, split, tpl="tpl-a", snd="snd-a", parent=None):
    return record_from_dict(
        {
            "id": rid,
            "text": f"message {rid} from {tpl} via {snd}",
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
        _rec("a2", "test", "tpl-shared", "snd-2"),
    ]
    report = audit_leakage(records)
    assert report["status"] == "FAIL"
    assert any(i["type"] == "template_group_leak" for i in report["issues"])


def test_sender_group_leak_detected_across_templates():
    records = [
        _rec("a1", "train", "tpl-1", "snd-shared"),
        _rec("a2", "validation", "tpl-2", "snd-shared"),
    ]
    report = audit_leakage(records)
    assert report["status"] == "FAIL"
    assert any(i["type"] == "sender_group_leak" for i in report["issues"])


def test_template_fingerprint_leak_detected():
    first = _rec("a1", "train", "tpl-1", "snd-1")
    second = _rec("a2", "test", "tpl-2", "snd-2")
    first.text = "您的验证码为 123456，5 分钟内有效"
    second.text = "您的验证码为 654321，5 分钟内有效"
    report = audit_leakage([first, second])
    assert report["status"] == "FAIL"
    assert any(i["type"] == "template_fingerprint_leak" for i in report["issues"])


def test_connected_split_keeps_transitive_groups_together():
    records = [
        _rec("a1", "train", "tpl-a", "snd-1"),
        _rec("a2", "train", "tpl-a", "snd-2"),
        _rec("a3", "train", "tpl-b", "snd-2"),
        _rec("a4", "train", "tpl-c", "snd-3"),
        _rec("a5", "train", "tpl-d", "snd-4"),
    ]
    splits = split_groups(records, ratios=(0.6, 0.2, 0.2), seed=7)
    assigned = {
        record.id: split_name
        for split_name, split_records in splits.items()
        for record in split_records
    }
    assert assigned["a1"] == assigned["a2"] == assigned["a3"]
    assert audit_leakage(
        [record for split_records in splits.values() for record in split_records]
    )["status"] == "PASS"


def test_id_overlap_detected():
    records = [
        _rec("same", "train", "tpl-1", "snd-1"),
        _rec("same", "test", "tpl-2", "snd-2"),
    ]
    report = audit_leakage(records)
    assert report["status"] == "FAIL"
    assert any(i["type"] == "id_overlap" for i in report["issues"])
