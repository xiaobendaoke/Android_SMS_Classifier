"""Tests for shared training utilities."""
import numpy as np

from src.schema import SmsRecord
from src.train_utils import (
    balanced_class_weights,
    filter_records_by_languages,
    student_predictions,
)


def test_balanced_class_weights_are_mean_one_and_support_multipliers():
    labels = np.asarray([0, 0, 0, 1, 1, 2, 3], dtype=np.int32)
    baseline = balanced_class_weights(labels, 4)
    boosted = balanced_class_weights(
        labels,
        4,
        multipliers={"TRANSACTION": 2.0},
    )
    assert np.isclose(float(baseline.mean()), 1.0)
    assert np.isclose(float(boosted.mean()), 1.0)
    assert boosted[0] > baseline[0]


def test_student_predictions_uses_auxiliary_transaction_head_without_polluting_argmax():
    logits = np.asarray(
        [
            [0.1, 3.0, 0.0, -1.0, 2.0],
            [0.1, 3.0, 0.0, -1.0, -2.0],
        ],
        dtype=np.float32,
    )
    primary = student_predictions(logits)
    protected = student_predictions(logits, transaction_threshold=0.5)
    assert primary.tolist() == [1, 1]
    assert protected.tolist() == [0, 1]


def test_filter_records_by_languages_limits_acceptance_scope():
    records = [
        SmsRecord(
            id="zh",
            text="短信",
            label="TRANSACTION",
            language="zh",
            source="test",
            source_license="test",
            sender_group="s1",
            template_group="t1",
            split="train",
        ),
        SmsRecord(
            id="en",
            text="message",
            label="AD",
            language="en",
            source="test",
            source_license="test",
            sender_group="s2",
            template_group="t2",
            split="train",
        ),
    ]
    assert [record.id for record in filter_records_by_languages(records, ["zh"])] == [
        "zh"
    ]
    assert len(filter_records_by_languages(records, [])) == 2
