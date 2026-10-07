"""Parity tests for high-precision transaction protection."""
from pathlib import Path

from src.transaction_protection import (
    apply_transaction_protection,
    load_protection_rules,
)

ROOT = Path(__file__).resolve().parents[1]


def _rules():
    return load_protection_rules(ROOT / "rules" / "rules")


def test_bank_activity_protects_action_without_relabeling_category():
    decision = apply_transaction_protection(
        "招商银行信用卡尾号1234消费88.00元，余额变动",
        "AD",
        _rules(),
    )
    assert decision.predicted_label == "AD"
    assert decision.action == "INBOX"
    assert "TXN_BANK_PROTECT_CN_001" in decision.matched_rule_ids


def test_credit_card_promotion_is_not_protected():
    decision = apply_transaction_protection(
        "信用卡优惠活动，立即申请享好礼",
        "AD",
        _rules(),
    )
    assert decision.predicted_label == "AD"
    assert not decision.protected


def test_carrier_billing_is_protected_but_carrier_promotion_is_not():
    billing = apply_transaction_protection(
        "中国移动提醒：本月话费账单余额不足，请及时充值",
        "AD",
        _rules(),
    )
    promotion = apply_transaction_protection(
        "中国移动套餐到期优惠，充值赠送20GB，回复TD退订",
        "AD",
        _rules(),
    )
    assert billing.predicted_label == "AD"
    assert billing.action == "INBOX"
    assert "TXN_CARRIER_PROTECT_CN_001" in billing.matched_rule_ids
    assert promotion.predicted_label == "AD"
    assert not promotion.protected


def test_transaction_fraud_conflict_goes_to_review():
    decision = apply_transaction_protection(
        "银行账户扣款异常，请点击链接并转账到安全账户",
        "TRANSACTION",
        _rules(),
    )
    assert decision.predicted_label == "TRANSACTION"
    assert decision.action == "REVIEW"
    assert decision.fraud_conflict


def test_model_protection_head_can_protect_without_rule_match():
    decision = apply_transaction_protection(
        "您有一条新的服务通知",
        "AD",
        _rules(),
        model_transaction_protect=True,
    )
    assert decision.predicted_label == "AD"
    assert decision.action == "INBOX"
    assert decision.reason_code == "MODEL_TRANSACTION_PROTECT"
