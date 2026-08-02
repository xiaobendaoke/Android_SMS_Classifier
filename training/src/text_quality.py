"""UTF-8 / mojibake quality gates for formal processed splits."""
from __future__ import annotations

import re
import unicodedata
from typing import List, Sequence

REPLACEMENT = "\ufffd"
SCANNER_VERSION = "text_quality_v1"
# Latin letters mixed with CJK replacement density, or long runs of symbols.
_MOJIBAKE_SYMBOL_RE = re.compile(r"[ÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞßàáâãäåæçèéêëìíîï]+")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

REASON_EMPTY = "empty_or_whitespace"
REASON_REPLACEMENT = "replacement_character"
REASON_NULL_PREFIX = "null_prefix"
REASON_MOJIBAKE = "mojibake_high_confidence"


def classify_text_quality_reasons(text: str) -> List[str]:
    """Return machine-readable quality failure reason codes (no SMS body)."""
    reasons: List[str] = []
    if text is None or not str(text).strip():
        return [REASON_EMPTY]
    value = str(text)
    if REPLACEMENT in value:
        reasons.append(REASON_REPLACEMENT)
    if value.lstrip().lower().startswith("null"):
        reasons.append(REASON_NULL_PREFIX)
    if _CONTROL_RE.search(value):
        reasons.append(REASON_MOJIBAKE)
    mojibake_chars = sum(
        len(match.group(0)) for match in _MOJIBAKE_SYMBOL_RE.finditer(value)
    )
    if len(value) >= 20 and mojibake_chars / len(value) >= 0.25:
        if REASON_MOJIBAKE not in reasons:
            reasons.append(REASON_MOJIBAKE)
    bad = 0
    for char in value:
        if unicodedata.category(char) in {"Co", "Cn"}:
            bad += 1
    if len(value) >= 20 and bad / len(value) >= 0.15:
        if REASON_MOJIBAKE not in reasons:
            reasons.append(REASON_MOJIBAKE)
    return reasons


def text_quality_issues(text: str, *, record_id: str = "") -> List[str]:
    """Return human-readable quality failures for a single SMS body."""
    prefix = f"{record_id}: " if record_id else ""
    reason_messages = {
        REASON_EMPTY: "empty text",
        REASON_REPLACEMENT: "contains U+FFFD replacement character",
        REASON_NULL_PREFIX: "text has null prefix",
        REASON_MOJIBAKE: "high-density mojibake",
    }
    return [
        f"{prefix}{reason_messages.get(reason, reason)}"
        for reason in classify_text_quality_reasons(text)
    ]


def records_failing_text_quality(records: Sequence[object]) -> List[str]:
    """Return ids of records that fail text quality gates."""
    failed: List[str] = []
    for record in records:
        record_id = getattr(record, "id", "")
        text = getattr(record, "text", "")
        if text_quality_issues(text, record_id=str(record_id)):
            failed.append(str(record_id))
    return failed
