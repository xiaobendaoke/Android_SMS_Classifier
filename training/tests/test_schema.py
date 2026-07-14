"""Tests for schema module."""
from src.schema import SmsRecord, record_from_dict, validate_records


def _sample_record(**overrides):
    base = {
        "id": "rec-001",
        "text": "Your code is 123456",
        "label": "TRANSACTION",
        "language": "en",
        "source": "test",
        "source_license": "CC-BY-4.0",
        "sender_group": "grp-1",
        "template_group": "tpl-1",
        "split": "train",
    }
    base.update(overrides)
    return record_from_dict(base)


def test_valid_record():
    record = _sample_record()
    assert record.is_valid()


def test_invalid_label():
    record = _sample_record(label="SPAM")
    assert not record.is_valid()
    assert any("invalid label" in e for e in record.validate())


def test_batch_validation_duplicate_id():
    records = [_sample_record(), _sample_record()]
    errors = validate_records(records)
    assert any("duplicate id" in e for e in errors)
