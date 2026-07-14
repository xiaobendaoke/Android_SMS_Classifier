"""Tests for byte_encoder module."""
from src.byte_encoder import (
    BYTE_OFFSET,
    HEAD_BYTES,
    MAX_BYTES,
    PAD_ID,
    TAIL_BYTES,
    encode_text,
    truncate_utf8_bytes,
)


def test_pad_id_and_offset():
    assert PAD_ID == 0
    assert BYTE_OFFSET == 1
    ids = encode_text("A")
    assert ids[0] == ord("A") + BYTE_OFFSET
    assert ids[1] == PAD_ID


def test_fixed_length():
    ids = encode_text("hello")
    assert len(ids) == MAX_BYTES


def test_truncation_head_tail():
    text = "a" * 600
    raw = text.encode("utf-8")
    truncated = truncate_utf8_bytes(raw)
    assert len(truncated) == HEAD_BYTES + TAIL_BYTES
    ids = encode_text(text)
    assert len(ids) == MAX_BYTES
    assert ids[-1] == PAD_ID or ids[-1] != PAD_ID
