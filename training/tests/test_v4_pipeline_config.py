"""Configuration and output-layout tests for Recall v4."""
import numpy as np

from scripts.evaluate import _decode_student_outputs
from scripts.export_android_assets import build_metadata


def test_decode_student_outputs_keeps_auxiliary_head_out_of_class_argmax():
    labels, protects = _decode_student_outputs(
        np.asarray(
            [
                [0.1, 2.0, 0.0, -1.0, 3.0],
                [0.1, 2.0, 0.0, -1.0, -3.0],
            ],
            dtype=np.float32,
        )
    )
    assert labels == ["AD", "AD"]
    assert protects == [True, False]


def test_generated_metadata_declares_five_logit_layout():
    metadata = build_metadata(None)
    assert metadata["architecture"] == "byte_textcnn_dual_head"
    assert metadata["modelOutputSize"] == 5
    assert metadata["transactionProtectionIndex"] == 4
    assert metadata["rulesVersion"] == "1.1.0"
