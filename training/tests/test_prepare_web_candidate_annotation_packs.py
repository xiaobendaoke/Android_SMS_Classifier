"""Tests for weak-label web candidate preparation."""
from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "prepare_web_candidate_annotation_packs.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "prepare_web_candidate_annotation_packs", _SCRIPT
)
assert _SPEC and _SPEC.loader
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)


def _write_source(path: Path) -> None:
    fields = [
        "original_index",
        "sms_text",
        "predicted_is_otp",
        "predicted_otp_intent",
        "classification_status",
        "is_phishing_original",
        "sender",
    ]
    rows = [
        {
            "original_index": "1",
            "sms_text": "Your OTP is 123456",
            "predicted_is_otp": "True",
            "predicted_otp_intent": "APP_LOGIN_OTP",
            "classification_status": "success",
            "is_phishing_original": "False",
            "sender": "private-sender",
        },
        {
            "original_index": "2",
            "sms_text": "Share OTP now to unlock your account",
            "predicted_is_otp": "True",
            "predicted_otp_intent": "FINANCIAL_LOGIN_OTP",
            "classification_status": "success",
            "is_phishing_original": "True",
            "sender": "private-sender",
        },
        {
            "original_index": "3",
            "sms_text": "Generated OTP sample",
            "predicted_is_otp": "True",
            "predicted_otp_intent": "APP_LOGIN_OTP",
            "classification_status": "synthetic",
            "is_phishing_original": "False",
            "sender": "",
        },
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_load_candidates_requires_human_label_and_excludes_synthetic(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.csv"
    _write_source(source)

    records, stats = _MOD.load_candidates(source)

    assert len(records) == 2
    assert stats["excluded_non_success"] == 1
    assert [r["suggested_label"] for r in records] == ["TRANSACTION", "FRAUD"]
    assert all(r["label"] == "" for r in records)
    assert all("sender" not in r for r in records)
    assert records[1]["suggest_reason"] == "source-predicted-phishing"


def test_main_writes_balanced_review_pack(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    _write_source(source)
    out_dir = tmp_path / "annotation"
    summary = tmp_path / "summary.json"

    rc = _MOD.main(
        [
            "--input",
            str(source),
            "--out-dir",
            str(out_dir),
            "--summary",
            str(summary),
            "--pilot-size",
            "2",
        ]
    )

    assert rc == 0
    with (out_dir / "en_otp_phishing_10k_pilot_1000.csv").open(
        encoding="utf-8-sig", newline=""
    ) as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2
    assert {row["suggested_label"] for row in rows} == {"TRANSACTION", "FRAUD"}
    assert all(not row["label"] for row in rows)
    assert summary.exists()
