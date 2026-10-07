"""Tests for model_student module."""
from pathlib import Path

import pytest
import yaml

from src.model_student import (
    StudentModelConfig,
    build_keras_model,
    config_from_mapping,
    default_student_config,
)


def test_default_config_layers():
    cfg = default_student_config()
    layers = cfg.describe_layers()
    assert layers[0]["type"] == "Input"
    assert any(layer["type"] == "Conv1D" for layer in layers)


def test_dual_head_adds_one_output_without_changing_backbone():
    cfg = StudentModelConfig(transaction_protection_head=True)
    assert cfg.output_shape() == (5,)
    layers = cfg.describe_layers()
    assert any(
        layer.get("name") == "transaction_protection_logit"
        for layer in layers
    )


def test_build_keras_model_import_error():
    try:
        import tensorflow  # noqa: F401
        cfg = StudentModelConfig(transaction_protection_head=True)
        model = build_keras_model(cfg)
        assert model is not None
        assert model.output_shape[-1] == 5
    except ImportError:
        with pytest.raises(ImportError, match="异机测试环境安装清单"):
            build_keras_model(default_student_config())


def test_formal_config_stays_within_parameter_budget():
    try:
        import tensorflow  # noqa: F401
    except ImportError:
        pytest.skip("TensorFlow not installed")
    root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load(
        (root / "configs" / "student.yaml").read_text(encoding="utf-8")
    )
    model = build_keras_model(config_from_mapping(config))
    assert model.count_params() <= 85_000
