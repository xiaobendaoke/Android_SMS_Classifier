"""Python parity implementation of the Android transaction-protection router."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from .normalize import normalize_text

PROTECT_TYPES = {
    "OTP_PROTECT",
    "PICKUP_PROTECT",
    "TRANSACTION_PROTECT",
}
FRAUD_TYPE = "FRAUD_RISK"


@dataclass(frozen=True)
class CompiledProtectionRule:
    id: str
    type: str
    priority: int
    reason_code: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class ProtectionDecision:
    predicted_label: str
    action: str
    reason_code: str
    matched_rule_ids: Tuple[str, ...]
    protected: bool
    fraud_conflict: bool


def load_protection_rules(rules_dir: Path) -> List[CompiledProtectionRule]:
    """Load only safety-relevant rules from the exported JSON rule bundle."""
    compiled: List[CompiledProtectionRule] = []
    for path in sorted(rules_dir.glob("*_rules.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload.get("rules", []):
            rule_type = str(row.get("type", ""))
            if not row.get("enabled", True):
                continue
            if rule_type not in PROTECT_TYPES | {FRAUD_TYPE}:
                continue
            compiled.append(
                CompiledProtectionRule(
                    id=str(row["id"]),
                    type=rule_type,
                    priority=int(row.get("priority", 0)),
                    reason_code=str(row.get("reasonCode", "RULE_MATCH")),
                    pattern=re.compile(str(row["pattern"]), flags=re.IGNORECASE),
                )
            )
    return sorted(compiled, key=lambda rule: rule.priority, reverse=True)


def apply_transaction_protection(
    text: str,
    raw_prediction: str,
    rules: Sequence[CompiledProtectionRule],
    *,
    model_transaction_protect: bool = False,
) -> ProtectionDecision:
    """Apply fail-safe routing: protect transactions unless a fraud rule conflicts."""
    normalized = normalize_text(text)
    matched = [rule for rule in rules if rule.pattern.search(normalized)]
    matched_ids = tuple(rule.id for rule in matched)
    protect_matches = [rule for rule in matched if rule.type in PROTECT_TYPES]
    fraud_matches = [rule for rule in matched if rule.type == FRAUD_TYPE]
    protected = bool(protect_matches) or model_transaction_protect
    conflict = protected and bool(fraud_matches)

    if conflict:
        return ProtectionDecision(
            # Safety rules decide REVIEW/INBOX only. They must not overwrite the
            # independently evaluated four-class model output.
            predicted_label=raw_prediction,
            action="REVIEW",
            reason_code=(
                "OTP_FRAUD_CONFLICT"
                if any(rule.type == "OTP_PROTECT" for rule in protect_matches)
                else "TRANSACTION_FRAUD_CONFLICT"
            ),
            matched_rule_ids=matched_ids,
            protected=True,
            fraud_conflict=True,
        )
    if protected:
        winner = protect_matches[0] if protect_matches else None
        return ProtectionDecision(
            predicted_label=raw_prediction,
            action="INBOX",
            reason_code=(
                winner.reason_code if winner else "MODEL_TRANSACTION_PROTECT"
            ),
            matched_rule_ids=matched_ids,
            protected=True,
            fraud_conflict=False,
        )
    return ProtectionDecision(
        predicted_label=raw_prediction,
        action=(
            "INBOX"
            if raw_prediction == "TRANSACTION"
            else "SUSPECT"
        ),
        reason_code="MODEL_PREDICTION",
        matched_rule_ids=matched_ids,
        protected=False,
        fraud_conflict=False,
    )


def apply_transaction_protection_batch(
    texts: Iterable[str],
    raw_predictions: Iterable[str],
    rules: Sequence[CompiledProtectionRule],
    *,
    model_transaction_protect: Iterable[bool] | None = None,
) -> List[ProtectionDecision]:
    flags = model_transaction_protect or ()
    if model_transaction_protect is None:
        return [
            apply_transaction_protection(text, prediction, rules)
            for text, prediction in zip(texts, raw_predictions)
        ]
    return [
        apply_transaction_protection(
            text,
            prediction,
            rules,
            model_transaction_protect=flag,
        )
        for text, prediction, flag in zip(texts, raw_predictions, flags)
    ]
