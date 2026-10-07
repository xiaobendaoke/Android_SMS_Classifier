"""Unicode text normalization for SMS classification."""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, Optional

DEFAULT_MAX_LENGTH = 4096

# Zero-width and format controls to remove (not all combining marks).
_ZERO_WIDTH_RE = re.compile(
    r"[\u200b\u200c\u200d\ufeff\u2060\u180e]"
)
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(
    text: Optional[str],
    max_length: int = DEFAULT_MAX_LENGTH,
    confusables: Optional[Dict[str, str]] = None,
) -> str:
    """
    Apply fixed normalization order (Phase 0 subset).

    1. Null guard and length cap
    2. Unicode NFKC
    3. Remove selected zero-width controls
    4. Collapse whitespace
    5. Optional confusables mapping
    """
    if text is None:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = _ZERO_WIDTH_RE.sub("", normalized)
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    if confusables:
        for src, dst in confusables.items():
            normalized = normalized.replace(src, dst)
    if len(normalized) > max_length:
        normalized = normalized[:max_length]
    return normalized
