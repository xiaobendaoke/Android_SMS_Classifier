from scripts.automated_annotation_audit import (
    PASS_A,
    PASS_B,
    PASS_C,
    STATUS,
    confidence,
    kappa,
    note_issues,
)
from src.label_corrections import load_corrections_manifest


def test_automated_status_is_provisional_and_never_human(tmp_path):
    path = tmp_path / "overlay.json"
    path.write_text(
        '{"status": "PROVISIONAL_AUTOMATED_MULTI_PASS", "claim_allowed": false, "corrections": []}',
        encoding="utf-8",
    )
    assert load_corrections_manifest(path)["status"] == STATUS
    assert all("HUMAN_" not in value for value in (PASS_A, PASS_B, PASS_C))


def test_note_contradictions_are_detected():
    assert "promotion_note_transaction" in note_issues(
        {"label": "TRANSACTION", "notes": "主意图=主动营销；排除=不是业务结果"}
    )
    assert "no_fraud_evidence_fraud" in note_issues(
        {"label": "FRAUD", "notes": "没有诈骗证据"}
    )
    assert "uncertain_note_not_review" in note_issues(
        {"label": "AD", "notes": "无法判断品牌真实性"}
    )


def test_agreement_metrics_and_confidence_are_not_forged():
    assert kappa(["AD", "FRAUD"], ["AD", "FRAUD"]) == 1.0
    assert confidence("AD", "AD", "AD") == "HIGH"
    assert confidence("AD", "HARASS", "NEEDS_REVIEW") == "LOW"
    assert confidence("AD", "HARASS", "FRAUD") == "MEDIUM"
