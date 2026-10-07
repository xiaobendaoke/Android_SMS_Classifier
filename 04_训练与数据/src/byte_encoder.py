"""UTF-8 byte-level encoder for Byte TextCNN."""
from __future__ import annotations

from typing import List, Sequence

PAD_ID = 0
BYTE_OFFSET = 1
MAX_BYTES = 512
HEAD_BYTES = 384
TAIL_BYTES = 128


def truncate_utf8_bytes(data: bytes) -> bytes:
    """Keep head 384 + tail 128 bytes when input exceeds 512 bytes."""
    if len(data) <= MAX_BYTES:
        return data
    return data[:HEAD_BYTES] + data[-TAIL_BYTES:]


def bytes_to_token_ids(data: bytes) -> List[int]:
    """Map unsigned bytes 0..255 to token IDs 1..256."""
    return [b + BYTE_OFFSET for b in data]


def pad_or_truncate(ids: Sequence[int], length: int = MAX_BYTES) -> List[int]:
    """Pad with PAD_ID or truncate to fixed length."""
    if len(ids) >= length:
        return list(ids[:length])
    return list(ids) + [PAD_ID] * (length - len(ids))


def encode_text(text: str, length: int = MAX_BYTES) -> List[int]:
    """
    Encode normalized text to fixed-length int32 token sequence.

    Algorithm:
    1. UTF-8 encode
    2. Truncate (384 head + 128 tail) if needed
    3. Map bytes to IDs 1..256
    4. Pad to `length` with PAD_ID=0
    """
    raw = text.encode("utf-8")
    raw = truncate_utf8_bytes(raw)
    token_ids = bytes_to_token_ids(raw)
    return pad_or_truncate(token_ids, length)


def encode_batch(texts: Sequence[str], length: int = MAX_BYTES) -> List[List[int]]:
    return [encode_text(t, length=length) for t in texts]
