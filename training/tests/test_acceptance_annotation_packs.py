"""Tests for acceptance annotation pack helpers."""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

from src.schema import LABEL_ORDER
from src.schema import record_from_dict


def _load(name: str):
    script = Path(__file__).resolve().parents[1] / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_pack(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id",
        "text",
        "language",
        "source",
        "label",
        "annotator",
        "template_group",
        "suggested_label",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def test_report_label_gaps(tmp_path: Path) -> None:
    mod = _load("report_label_gaps.py")
    ann = tmp_path / "annotated.jsonl"
    # 2 TXN zh only
    ann.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": f"zh_{i}",
                        "text": f"验证码{i}",
                        "label": "TRANSACTION",
                        "language": "zh",
                        "source": "t",
                        "source_license": "x",
                        "sender_group": "s",
                        "template_group": "g",
                        "split": "train",
                        "is_synthetic": False,
                        "is_adversarial": False,
                        "parent_id": None,
                        "annotator_ids": ["a"],
                    }
                )
                for i in range(2)
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "gap.json"
    rc = mod.main(
        [
            "--annotated",
            str(ann),
            "--ann-dir",
            str(tmp_path / "missing"),
            "--out",
            str(out),
            "--freeze-per-class",
            "5",
        ]
    )
    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["freeze_gaps"]["zh"]["TRANSACTION"]["have"] == 2
    assert report["freeze_gaps"]["zh"]["TRANSACTION"]["shortfall"] == 3
    assert report["freeze_gaps"]["en"]["AD"]["shortfall"] == 5


def test_harass_id_packs(tmp_path: Path) -> None:
    mod = _load("prepare_harass_id_relabel_packs.py")
    ann_dir = tmp_path / "annotation"
    _write_pack(
        ann_dir / "uci_all_suggested.csv",
        [
            {
                "id": "en_1",
                "text": "Your debt collection call overdue now",
                "language": "en",
                "source": "uci",
                "label": "NEEDS_REVIEW",
            },
            {
                "id": "en_2",
                "text": "Flash sale 50% off today only",
                "language": "en",
                "source": "uci",
                "label": "AD",
            },
        ],
    )
    _write_pack(
        ann_dir / "id_yudiwbs_all_suggested.csv",
        [
            {
                "id": "id_1",
                "text": "Kode OTP anda 123456 untuk login",
                "language": "id",
                "source": "yudi",
                "label": "NEEDS_REVIEW",
            },
            {
                "id": "id_2",
                "text": "Penagihan hutang segera bayar",
                "language": "id",
                "source": "yudi",
                "label": "NEEDS_REVIEW",
            },
        ],
    )
    out_dir = tmp_path / "out"
    rc = mod.main(
        [
            "--ann-dir",
            str(ann_dir),
            "--out-dir",
            str(out_dir),
            "--harass-max",
            "50",
            "--id-max",
            "50",
        ]
    )
    assert rc == 0
    harass = list(csv.DictReader((out_dir / "harass_relabel_candidates.csv").open(encoding="utf-8-sig")))
    id_rows = list(csv.DictReader((out_dir / "id_gap_fill_candidates.csv").open(encoding="utf-8-sig")))
    assert any(r["id"] == "en_1" for r in harass)
    assert {r["id"] for r in id_rows} >= {"id_1", "id_2"}
    assert all(r["label"] == "" for r in harass)
    assert (out_dir / "README_HARASS_ID_RELABEL.txt").exists()


def test_freeze_dual_packs(tmp_path: Path) -> None:
    mod = _load("prepare_freeze_dual_annotation_packs.py")
    ann_dir = tmp_path / "annotation"
    rows = []
    for i, lab in enumerate(LABEL_ORDER):
        rows.append(
            {
                "id": f"zh_{i}",
                "text": f"中文样本{i} {lab}",
                "language": "zh",
                "source": "zh",
                "label": lab,
            }
        )
    _write_pack(ann_dir / "zh_all_suggested.csv", rows)
    out_dir = tmp_path / "freeze"
    rc = mod.main(
        [
            "--ann-dir",
            str(ann_dir),
            "--out-dir",
            str(out_dir),
            "--per-class",
            "2",
        ]
    )
    assert rc == 0
    pool = list(csv.DictReader((out_dir / "freeze_pool.csv").open(encoding="utf-8-sig")))
    a = list(csv.DictReader((out_dir / "freeze_annotator_A.csv").open(encoding="utf-8-sig")))
    b = list(csv.DictReader((out_dir / "freeze_annotator_B.csv").open(encoding="utf-8-sig")))
    assert len(pool) == len(a) == len(b)
    assert all(r["label"] == "" and r["annotator"] == "" for r in a)
    assert {r["id"] for r in a} == {r["id"] for r in b}
    meta = json.loads((out_dir / "freeze_shortfall.json").read_text(encoding="utf-8"))
    assert meta["by_lang_label"]["zh"]["TRANSACTION"]["sampled"] == 1
    assert meta["by_lang_label"]["en"]["AD"]["shortfall"] == 2


def test_transaction_specialist_selects_all_six_coverage_buckets() -> None:
    mod = _load("prepare_transaction_specialist_freeze.py")
    texts = {
        "OTP": "您的验证码为123456，五分钟内有效",
        "LOGISTICS": "您的快递已到驿站，请凭取件码领取",
        "ORDER": "订单已支付成功，预计明日发货",
        "REPAYMENT": "本期账单还款成功",
        "CARRIER": "中国移动提醒您本月流量剩余2GB",
        "BANK": "银行卡尾号1234消费50元",
    }
    records = []
    for idx, (subtype, text) in enumerate(texts.items()):
        records.append(
            record_from_dict(
                {
                    "id": f"txn-{idx}",
                    "text": text,
                    "label": "TRANSACTION",
                    "language": "zh",
                    "source": "test",
                    "source_license": "internal-test",
                    "sender_group": f"sender-{idx}",
                    "template_group": f"template-{idx}",
                    "split": "train",
                    "annotator_ids": ["audit_pipeline_a", "audit_pipeline_b"],
                }
            )
        )
    selected, coverage = mod.select_records(records, per_subtype=1, seed=42)
    assert len(selected) == 6
    assert {row["coverage_subtype"] for row in selected} == set(texts)
    assert all(cell["shortfall"] == 0 for cell in coverage.values())
    assert all(row["existing_human_review_ids"] == [] for row in selected)
