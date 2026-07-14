"""Tests for model_student module."""
import pytest

from src.model_student import StudentModelConfig, default_student_config, build_keras_model


def test_default_config_layers():
    cfg = default_student_config()
    layers = cfg.describe_layers()
    assert layers[0]["type"] == "Input"
    assert any(layer["type"] == "Conv1D" for layer in layers)


def test_build_keras_model_import_error():
    try:
        import tensorflow  # noqa: F401
        model = build_keras_model(default_student_config())
        assert model is not None
    except ImportError:
        with pytest.raises(ImportError, match="异机测试环境安装清单"):
            build_keras_model(default_student_config())
