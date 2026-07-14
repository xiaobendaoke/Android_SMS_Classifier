"""Byte TextCNN student model configuration and Keras builder."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Sequence

from .byte_encoder import BYTE_OFFSET, MAX_BYTES, PAD_ID
from .schema import LABEL_ORDER

SETUP_DOC = "docs/异机测试环境安装清单.md"


@dataclass
class StudentModelConfig:
    """Architecture hyperparameters matching configs/student.yaml."""

    vocab_size: int = 257
    embedding_dim: int = 48
    conv_filters: int = 64
    conv_kernels: List[int] = field(default_factory=lambda: [3, 5, 7])
    dense_units: int = 96
    dropout: float = 0.2
    num_classes: int = 4
    max_bytes: int = MAX_BYTES
    pad_id: int = PAD_ID
    byte_offset: int = BYTE_OFFSET
    label_order: List[str] = field(default_factory=lambda: list(LABEL_ORDER))

    def input_shape(self) -> Sequence[int]:
        return (self.max_bytes,)

    def output_shape(self) -> Sequence[int]:
        return (self.num_classes,)

    def describe_layers(self) -> List[Dict[str, object]]:
        """Return a human-readable layer stack for documentation/tests."""
        branches = [
            {
                "type": "Conv1D",
                "filters": self.conv_filters,
                "kernel_size": k,
                "activation": "relu",
            }
            for k in self.conv_kernels
        ]
        return [
            {"type": "Input", "shape": list(self.input_shape()), "dtype": "int32"},
            {
                "type": "Embedding",
                "vocab_size": self.vocab_size,
                "dim": self.embedding_dim,
            },
            *branches,
            {"type": "GlobalMaxPool1D", "branches": len(self.conv_kernels)},
            {
                "type": "Concatenate",
                "dim": self.conv_filters * len(self.conv_kernels),
            },
            {"type": "Dense", "units": self.dense_units, "activation": "relu"},
            {"type": "Dropout", "rate": self.dropout},
            {"type": "Dense", "units": self.num_classes, "activation": "linear"},
        ]


def default_student_config() -> StudentModelConfig:
    return StudentModelConfig()


def config_from_mapping(data: Mapping[str, Any]) -> StudentModelConfig:
    """Build config from YAML-loaded dict (configs/student.yaml)."""
    input_cfg = data.get("input", {})
    model_cfg = data.get("model", {})
    return StudentModelConfig(
        vocab_size=int(input_cfg.get("vocab_size", 257)),
        embedding_dim=int(model_cfg.get("embedding_dim", 48)),
        conv_filters=int(model_cfg.get("conv_filters", 64)),
        conv_kernels=list(model_cfg.get("conv_kernels", [3, 5, 7])),
        dense_units=int(model_cfg.get("dense_units", 96)),
        dropout=float(model_cfg.get("dropout", 0.2)),
        num_classes=int(model_cfg.get("num_classes", 4)),
        max_bytes=int(input_cfg.get("max_bytes", MAX_BYTES)),
        pad_id=int(input_cfg.get("pad_id", PAD_ID)),
        byte_offset=int(input_cfg.get("byte_offset", BYTE_OFFSET)),
    )


def build_keras_model(config: StudentModelConfig):
    """
    Build Byte TextCNN Keras model.

    Raises ImportError with setup doc pointer when TensorFlow is unavailable.
    """
    try:
        from tensorflow import keras
        from tensorflow.keras import layers
    except ImportError as exc:
        raise ImportError(
            "TensorFlow is required to build the Byte TextCNN student model. "
            f"Install heavy training dependencies listed in {SETUP_DOC} "
            "(see requirements-train.txt)."
        ) from exc

    inputs = keras.Input(
        shape=(config.max_bytes,),
        dtype="int32",
        name="byte_input",
    )
    x = layers.Embedding(
        input_dim=config.vocab_size,
        output_dim=config.embedding_dim,
        name="byte_embedding",
    )(inputs)

    branch_outputs = []
    for idx, kernel_size in enumerate(config.conv_kernels):
        branch = layers.Conv1D(
            filters=config.conv_filters,
            kernel_size=kernel_size,
            activation="relu",
            padding="same",
            name=f"conv1d_k{kernel_size}_{idx}",
        )(x)
        branch_outputs.append(
            layers.GlobalMaxPooling1D(name=f"gmp_k{kernel_size}_{idx}")(branch)
        )

    if len(branch_outputs) > 1:
        x = layers.Concatenate(name="concat_branches")(branch_outputs)
    else:
        x = branch_outputs[0]

    x = layers.Dense(
        config.dense_units,
        activation="relu",
        name="dense_hidden",
    )(x)
    x = layers.Dropout(config.dropout, name="dropout")(x)
    outputs = layers.Dense(
        config.num_classes,
        activation="linear",
        name="logits",
    )(x)

    return keras.Model(inputs=inputs, outputs=outputs, name="byte_textcnn")
