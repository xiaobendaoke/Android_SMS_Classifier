"""JSONL sample schema and validation."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Set

# Four-class model output order (excludes NEEDS_REVIEW).
LABELS: FrozenSet[str] = frozenset({"TRANSACTION", "AD", "HARASS", "FRAUD"})
VALID_LABELS: FrozenSet[str] = LABELS | frozenset({"NEEDS_REVIEW"})
VALID_SPLITS: FrozenSet[str] = frozenset({"train", "validation", "test"})
VALID_LANGUAGES: FrozenSet[str] = frozenset({"zh", "en", "hi", "id"})

LABEL_ORDER: List[str] = ["TRANSACTION", "AD", "HARASS", "FRAUD"]


@dataclass
class SmsRecord:
    """Single SMS training/evaluation record."""

    id: str
    text: str
    label: str
    language: str
    source: str
    source_license: str
    sender_group: str
    template_group: str
    split: str
    is_synthetic: bool = False
    is_adversarial: bool = False
    parent_id: Optional[str] = None
    annotator_ids: List[str] = field(default_factory=list)

    def validate(self) -> List[str]:
        """Return list of validation error messages (empty if valid)."""
        errors: List[str] = []
        if not self.id:
            errors.append("id is required")
        if not self.text:
            errors.append("text is required")
        if self.label not in VALID_LABELS:
            errors.append(f"invalid label: {self.label}")
        if self.language not in VALID_LANGUAGES:
            errors.append(f"invalid language: {self.language}")
        if self.split not in VALID_SPLITS:
            errors.append(f"invalid split: {self.split}")
        if not self.source:
            errors.append("source is required")
        if not self.source_license:
            errors.append("source_license is required")
        if not self.sender_group:
            errors.append("sender_group is required")
        if not self.template_group:
            errors.append("template_group is required")
        return errors

    def is_valid(self) -> bool:
        return not self.validate()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "label": self.label,
            "language": self.language,
            "source": self.source,
            "source_license": self.source_license,
            "sender_group": self.sender_group,
            "template_group": self.template_group,
            "is_synthetic": self.is_synthetic,
            "is_adversarial": self.is_adversarial,
            "parent_id": self.parent_id,
            "annotator_ids": list(self.annotator_ids),
            "split": self.split,
        }


def record_from_dict(data: Dict[str, Any]) -> SmsRecord:
    """Build SmsRecord from a JSON object."""
    return SmsRecord(
        id=str(data.get("id", "")),
        text=str(data.get("text", "")),
        label=str(data.get("label", "")),
        language=str(data.get("language", "")),
        source=str(data.get("source", "")),
        source_license=str(data.get("source_license", "")),
        sender_group=str(data.get("sender_group", "")),
        template_group=str(data.get("template_group", "")),
        split=str(data.get("split", "")),
        is_synthetic=bool(data.get("is_synthetic", False)),
        is_adversarial=bool(data.get("is_adversarial", False)),
        parent_id=data.get("parent_id"),
        annotator_ids=list(data.get("annotator_ids", [])),
    )


def validate_record(data: Dict[str, Any]) -> List[str]:
    """Validate a raw JSON dict; returns error messages."""
    return record_from_dict(data).validate()


def validate_records(records: Sequence[SmsRecord]) -> List[str]:
    """Validate a batch of records."""
    errors: List[str] = []
    seen_ids: Set[str] = set()
    for idx, record in enumerate(records):
        for msg in record.validate():
            errors.append(f"record[{idx}] {msg}")
        if record.id in seen_ids:
            errors.append(f"duplicate id: {record.id}")
        seen_ids.add(record.id)
    return errors


def load_jsonl(path: Path) -> List[SmsRecord]:
    """Load records from a JSONL file."""
    records: List[SmsRecord] = []
    text = path.read_text(encoding="utf-8")
    for line_no, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        records.append(record_from_dict(data))
    return records


def write_jsonl(path: Path, records: Sequence[SmsRecord]) -> None:
    """Write records to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record.to_dict(), ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
