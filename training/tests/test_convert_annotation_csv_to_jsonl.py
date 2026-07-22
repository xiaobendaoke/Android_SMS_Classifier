"""Tests for annotation CSV → JSONL converter."""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

from src.schema import load_jsonl

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "convert_annotation_csv_to_jsonl.py"
_SPEC = importlib.util.spec_from_file_location("convert_annotation_csv_to_jsonl", _SCRIPT)
assert _SPEC and _SPEC.loader
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)
convert_pack = _MOD.convert_pack
main = _MOD.main


def test_convert_pack_drops_needs_review(tmp_path: Path) -> None:
    csv_path = tmp_path / "zh_all_suggested.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "id",
                "text",
                "language",
                "source",
                "label",
                "annotator",
                "template_group",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "id": "zh_t1",
                "text": "您的验证码是123456",
                "language": "zh",
                "source": "gitcode_zh_sms_8a104",
                "label": "TRANSACTION",
                "annotator": "tester",
                "template_group": "tpl1",
            }
        )
        writer.writerow(
            {
                "id": "zh_r1",
                "text": "今晚吃饭吗",
                "language": "zh",
                "source": "gitcode_zh_sms_8a104",
                "label": "NEEDS_REVIEW",
                "annotator": "tester",
                "template_group": "tpl2",
            }
        )
        writer.writerow(
            {
                "id": "zh_empty",
                "text": "",
                "language": "zh",
                "source": "gitcode_zh_sms_8a104",
                "label": "AD",
                "annotator": "",
                "template_group": "tpl3",
            }
        )

    records, by_label, skipped = convert_pack(
        csv_path,
        language_fallback="zh",
        source_fallback="gitcode_zh_sms_8a104",
        source_license="CC BY-NC-SA 4.0",
    )
    assert len(records) == 1
    assert records[0].id == "zh_t1"
    assert records[0].label == "TRANSACTION"
    assert records[0].sender_group == "snd-ann-zh_t1"
    assert records[0].annotator_ids == ["tester"]
    assert by_label["TRANSACTION"] == 1
    assert skipped == 2


def test_main_writes_jsonl(tmp_path: Path, monkeypatch) -> None:
    ann = tmp_path / "ann"
    ann.mkdir()
    # Minimal packs matching PACKS filenames; only zh present is enough with warns
    for fname, lang, label in [
        ("zh_all_suggested.csv", "zh", "AD"),
        ("uci_all_suggested.csv", "en", "FRAUD"),
        ("id_yudiwbs_all_suggested.csv", "id", "HARASS"),
        ("id_spamshield_all_suggested.csv", "id", "AD"),
        ("iiitd_all_suggested.csv", "hi", "AD"),
    ]:
        path = ann / fname
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "id",
                    "text",
                    "language",
                    "source",
                    "label",
                    "annotator",
                    "template_group",
                ],
            )
            writer.writeheader()
            stem = fname.replace(".csv", "")
            writer.writerow(
                {
                    "id": f"{stem}_1",
                    "text": f"sample text {lang} {fname}",
                    "language": lang,
                    "source": "test_src",
                    "label": label,
                    "annotator": "qa",
                    "template_group": "tg",
                }
            )
            writer.writerow(
                {
                    "id": f"{stem}_skip",
                    "text": f"chat {fname}",
                    "language": lang,
                    "source": "test_src",
                    "label": "NEEDS_REVIEW",
                    "annotator": "qa",
                    "template_group": "tg2",
                }
            )

    out = tmp_path / "out.jsonl"
    summary = tmp_path / "summary.json"
    rc = main(
        [
            "--ann-dir",
            str(ann),
            "--output",
            str(out),
            "--summary",
            str(summary),
        ]
    )
    assert rc == 0
    records = load_jsonl(out)
    assert len(records) == 5
    assert all(r.label != "NEEDS_REVIEW" for r in records)
    data = json.loads(summary.read_text(encoding="utf-8"))
    assert data["n_records"] == 5
    assert "NOT frozen" in data["note"]
