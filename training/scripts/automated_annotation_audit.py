#!/usr/bin/env python3
"""Prepare and finalize a non-human, multi-pass blind SMS annotation audit.

This tool deliberately has no path to the original labels, model scores, or test
metrics.  It consumes only the two blank blind packs and the three automated
outputs produced from those packs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT.parent / "docs" / "labeling-guide.md"
LABELS = {"TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"}
PASS_A = "AUTO_GPT56_TERRA_PASS_A_001"
PASS_B = "AUTO_GPT56_TERRA_PASS_B_001"
PASS_C = "AUTO_GPT56_TERRA_ADJUDICATOR_001"
STATUS = "PROVISIONAL_AUTOMATED_MULTI_PASS"
RISK_IDS = [
    "zh_08937", "zh-n2w-07703", "zh-n2w-07929", "zh-n2w-09673",
    "zh-n2w-03416", "zh-n2w-06672", "zh-n2w-07304", "zh-n2w-07558",
    "zh-n2w-07605", "zh-n2w-07617", "zh-n2w-07725", "zh-n2w-07978",
    "zh-n2w-08206", "zh-n2w-07310", "zh_10548", "zh_01214",
    "zh-n2w-06829", "zh-n2w-04902", "zh-n2w-08728", "zh-n2w-08886",
]
PACKS = {
    "label_conflicts": {
        "key": "review_group_id",
        "a": ROOT / "data/interim/annotation/label_conflicts_v2/blind_annotator_A.csv",
        "b": ROOT / "data/interim/annotation/label_conflicts_v2/blind_annotator_B.csv",
        "a_out": "label_conflicts_terra_pass_a.csv",
        "b_out": "label_conflicts_terra_pass_b.csv",
        "c_out": "label_conflicts_terra_pass_c_conflicts.csv",
        "final": "label_conflicts_terra_adjudicated.csv",
    },
    "transaction_specialist": {
        "key": "review_id",
        "a": ROOT / "data/interim/annotation/transaction_specialist_v2/specialist_annotator_A.csv",
        "b": ROOT / "data/interim/annotation/transaction_specialist_v2/specialist_annotator_B.csv",
        "a_out": "transaction_specialist_terra_pass_a.csv",
        "b_out": "transaction_specialist_terra_pass_b.csv",
        "c_out": "transaction_specialist_terra_pass_c_conflicts.csv",
        "final": "transaction_specialist_terra_adjudicated.csv",
    },
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_text_sha(value: str) -> str:
    return text_sha(value.replace("\r\n", "\n").replace("\r", "\n").strip("\ufeff").strip())


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [{key: (value or "").strip() for key, value in row.items()}
                for row in csv.DictReader(handle)]


def write_csv(path: Path, rows: Iterable[dict], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def key_of(row: Dict[str, str], key: str) -> Tuple[str, str]:
    return row.get(key, ""), row.get("id", "")


def kappa(a: Sequence[str], b: Sequence[str]) -> float:
    if not a:
        return 1.0
    observed = sum(x == y for x, y in zip(a, b)) / len(a)
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[x] * cb[x] for x in LABELS) / (len(a) * len(a))
    return 1.0 if expected == 1.0 else (observed - expected) / (1 - expected)


def validate_blank(path: Path, key: str) -> List[Dict[str, str]]:
    rows = read_csv(path)
    required = {key, "id", "text", "label", "notes", "human_annotator_id"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"invalid blind-sheet schema: {path}")
    if any(row["label"] or row["notes"] or row["human_annotator_id"] for row in rows):
        raise ValueError(f"human blind sheet is no longer blank: {path}")
    if len({key_of(row, key) for row in rows}) != len(rows):
        raise ValueError(f"duplicate review/id key: {path}")
    return rows


def validate_pass(path: Path, blank: Sequence[Dict[str, str]], key: str, annotator: str) -> List[Dict[str, str]]:
    rows = read_csv(path)
    required = {key, "id", "text", "label", "notes", "annotator_id"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"invalid automated sheet schema: {path}")
    source = {key_of(row, key): row for row in blank}
    got = {key_of(row, key): row for row in rows}
    if set(source) != set(got) or len(got) != len(rows):
        raise ValueError(f"membership/order key mismatch: {path}")
    for row in rows:
        original = source[key_of(row, key)]
        if row["text"] != original["text"]:
            raise ValueError(f"text was modified: {path}:{row['id']}")
        if row["label"] not in LABELS or not row["notes"]:
            raise ValueError(f"missing/invalid annotation: {path}:{row['id']}")
        if row["annotator_id"] != annotator or "HUMAN_" in row["annotator_id"]:
            raise ValueError(f"forbidden annotator identity: {path}:{row['id']}")
    return rows


def note_issues(row: Dict[str, str]) -> List[str]:
    note, label, body = row.get("notes", ""), row.get("final_label", row.get("label", "")), row.get("text", "")
    issues: List[str] = []
    if any(x in note for x in ("无法判断", "无法可靠", "不确定")) and label != "NEEDS_REVIEW":
        issues.append("uncertain_note_not_review")
    if any(x in note for x in ("不是业务结果", "贷款推广", "主动营销")) and label == "TRANSACTION":
        issues.append("promotion_note_transaction")
    if "没有诈骗证据" in note and label == "FRAUD":
        issues.append("no_fraud_evidence_fraud")
    if any(x in note for x in ("明确到账", "扣款", "验证码", "取件码")) and label in {"AD", "HARASS"}:
        issues.append("transaction_evidence_non_transaction")
    if any(x in row.get("text", "") for x in ("\ufffd",)) and label != "NEEDS_REVIEW":
        issues.append("garbled_text_not_review")
    if label == "TRANSACTION" and any(x in body for x in ("满意度", "服务评价", "进行评价", "服务调研", "调查问卷")):
        issues.append("survey_transaction")
    loan_words = ("贷款", "借款", "授信", "额度", "预审")
    marketing_words = ("申请", "查询利率", "低利率", "放款快", "可循环", "点击")
    existing_result = ("已申请", "申请结果", "还款", "扣款", "到账", "账单", "调整", "生效", "审批通过", "审批未通过", "额度调至", "额度将在", "尾号")
    if label == "TRANSACTION" and any(x in body for x in loan_words) and any(x in body for x in marketing_words) and not any(x in body for x in existing_result):
        issues.append("loan_marketing_transaction")
    return issues


def confidence(label_a: str, label_b: str, final_label: str) -> str:
    if label_a == label_b == final_label and final_label != "NEEDS_REVIEW":
        return "HIGH"
    if final_label == "NEEDS_REVIEW":
        return "LOW"
    return "MEDIUM"


def prepare(output: Path, independence: bool) -> None:
    output.mkdir(parents=True, exist_ok=True)
    if (output / "automated_annotation_pre_adjudication.json").exists():
        raise ValueError(f"refusing to overwrite prepared audit: {output}")
    report = {"status": "PENDING_AUTOMATED_ADJUDICATION", "independence": independence,
              "input_sha256": {}, "tasks": {}}
    for name, spec in PACKS.items():
        blank_a, blank_b = validate_blank(spec["a"], spec["key"]), validate_blank(spec["b"], spec["key"])
        a = validate_pass(output / spec["a_out"], blank_a, spec["key"], PASS_A)
        b = validate_pass(output / spec["b_out"], blank_b, spec["key"], PASS_B)
        by_a = {key_of(row, spec["key"]): row for row in a}
        by_b = {key_of(row, spec["key"]): row for row in b}
        if all(by_a[k]["label"] == by_b[k]["label"] and by_a[k]["notes"] == by_b[k]["notes"] for k in by_a):
            raise ValueError(f"Pass A/B are a direct copy: {name}")
        conflicts = []
        pairs = Counter()
        for item in by_a:
            left, right = by_a[item], by_b[item]
            pairs[f"{left['label']} -> {right['label']}"] += 1
            if left["label"] != right["label"]:
                conflicts.append({spec["key"]: left[spec["key"]], "id": left["id"], "text": left["text"],
                                  "pass_a_label": left["label"], "pass_a_notes": left["notes"],
                                  "pass_b_label": right["label"], "pass_b_notes": right["notes"],
                                  "final_label": "", "annotator_id": "", "notes": ""})
        write_csv(output / spec["c_out"], conflicts, [spec["key"], "id", "text", "pass_a_label", "pass_a_notes", "pass_b_label", "pass_b_notes", "final_label", "annotator_id", "notes"])
        labels_a, labels_b = [x["label"] for x in a], [x["label"] for x in b]
        report["input_sha256"][name] = {"blind_a": sha(spec["a"]), "blind_b": sha(spec["b"]), "pass_a": sha(output / spec["a_out"]), "pass_b": sha(output / spec["b_out"])}
        report["tasks"][name] = {"total": len(a), "agreement_count": len(a) - len(conflicts), "conflict_count": len(conflicts), "raw_agreement": (len(a) - len(conflicts)) / len(a), "cohen_kappa": kappa(labels_a, labels_b), "pass_a_distribution": dict(Counter(labels_a)), "pass_b_distribution": dict(Counter(labels_b)), "conflict_pairs": {p: n for p, n in pairs.items() if p.split(" -> ")[0] != p.split(" -> ")[1]}, "pass_a_transaction_minus_b": labels_a.count("TRANSACTION") - labels_b.count("TRANSACTION")}
    report["labeling_guide_sha256"] = sha(GUIDE)
    (output / "automated_annotation_pre_adjudication.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def finalize(output: Path, independence: bool) -> None:
    pre = json.loads((output / "automated_annotation_pre_adjudication.json").read_text(encoding="utf-8"))
    revisions_path = output / "post_qa_revisions.csv"
    revisions = {row["id"]: row for row in read_csv(revisions_path)} if revisions_path.exists() else {}
    for item, revision in revisions.items():
        if revision.get("final_label") not in LABELS or not revision.get("notes") or revision.get("annotator_id") != PASS_C:
            raise ValueError(f"invalid post-QA revision: {item}")
    final_rows: List[Dict[str, str]] = []
    rows_by_task: Dict[str, List[Dict[str, str]]] = {}
    qa: List[dict] = []
    task_reports = pre["tasks"]
    for name, spec in PACKS.items():
        blank_a, blank_b = validate_blank(spec["a"], spec["key"]), validate_blank(spec["b"], spec["key"])
        a, b = validate_pass(output / spec["a_out"], blank_a, spec["key"], PASS_A), validate_pass(output / spec["b_out"], blank_b, spec["key"], PASS_B)
        by_a, by_b = ({key_of(x, spec["key"]): x for x in a}, {key_of(x, spec["key"]): x for x in b})
        c = {key_of(x, spec["key"]): x for x in read_csv(output / spec["c_out"])}
        expected = {item for item in by_a if by_a[item]["label"] != by_b[item]["label"]}
        if set(c) != expected:
            raise ValueError(f"Pass C membership is not exactly the conflicts: {name}")
        rows = []
        for item, left in by_a.items():
            right = by_b[item]
            if item in c:
                resolution = c[item]
                if resolution.get("annotator_id") != PASS_C or resolution.get("final_label") not in LABELS or not resolution.get("notes"):
                    raise ValueError(f"invalid Pass C annotation: {name}:{left['id']}")
                final, c_note, c_id, mode = resolution["final_label"], resolution["notes"], PASS_C, "ADJUDICATED"
            else:
                final, c_note, c_id, mode = left["label"], "Pass A/B 一致；保留共同判定。", "", "AGREED"
            revision = revisions.get(left["id"])
            if revision:
                final, c_note, c_id, mode = revision["final_label"], revision["notes"], PASS_C, "POST_QA_REVIEW"
            row = {spec["key"]: left[spec["key"]], "id": left["id"], "text": left["text"], "pass_a_label": left["label"], "pass_a_notes": left["notes"], "pass_b_label": right["label"], "pass_b_notes": right["notes"], "final_label": final, "adjudicator_id": c_id, "adjudication_notes": c_note, "resolution": mode}
            rows.append(row); final_rows.append(row)
            for issue in note_issues({**row, "notes": c_note or left["notes"]}):
                qa.append({"task": name, "id": left["id"], "issue": issue})
        write_csv(output / spec["final"], rows, [spec["key"], "id", "text", "pass_a_label", "pass_a_notes", "pass_b_label", "pass_b_notes", "final_label", "adjudicator_id", "adjudication_notes", "resolution"])
        rows_by_task[name] = rows
        task_reports[name]["adjudicated_third_label_count"] = sum(1 for row in rows if row["resolution"] == "ADJUDICATED" and row["final_label"] not in {row["pass_a_label"], row["pass_b_label"]})
        task_reports[name]["final_distribution"] = dict(Counter(row["final_label"] for row in rows))
    by_id = {row["id"]: row for row in final_rows}
    risk = []
    for item in RISK_IDS:
        row = by_id.get(item)
        if not row:
            risk.append({"id": item, "status": "MISSING_FROM_ALLOWED_BLIND_INPUT"})
        else:
            risk.append({"id": item, "text_summary": row["text"][:80], "pass_a": row["pass_a_label"], "pass_b": row["pass_b_label"], "pass_c": row["adjudication_notes"], "final_label": row["final_label"], "reason": row["adjudication_notes"] or row["pass_a_notes"], "confidence_category": confidence(row["pass_a_label"], row["pass_b_label"], row["final_label"])})
    # Only this post-adjudication block uses template/sender metadata.  It does
    # not access the pool's historical-label column.
    pool = read_csv(ROOT / "data/interim/annotation/label_conflicts_v2/conflict_pool.csv")
    metadata = {row["id"]: {field: row.get(field, "") for field in ("template_group", "sender_group")} for row in pool}
    template_groups: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in rows_by_task["label_conflicts"]:
        group = metadata.get(row["id"], {}).get("template_group", "")
        if group:
            template_groups[group].append(row)
    inconsistencies = []
    for group, rows in sorted(template_groups.items()):
        labels = sorted({row["final_label"] for row in rows})
        if len(labels) > 1:
            inconsistencies.append({"template_group": group, "ids": "|".join(row["id"] for row in rows), "labels": "|".join(labels), "explanation": "需自动复核；未按多数票强制统一。"})
    write_csv(output / "template_consistency_audit.csv", inconsistencies, ["template_group", "ids", "labels", "explanation"])
    template_summary = {"status": "REVIEW_REQUIRED" if inconsistencies else "PASS", "audited_task": "label_conflicts", "audited_groups": len(template_groups), "unexplained_inconsistent_groups": len(inconsistencies), "specialist_metadata": "not present in permitted blind/internal specialist input"}
    corrections = [{"id": row["id"], "text_sha256": text_sha(row["text"]), "text_sha256_canonical": canonical_text_sha(row["text"]), "final_label": row["final_label"], "annotator_ids": [PASS_A, PASS_B] + ([PASS_C] if row["adjudicator_id"] else [])} for row in final_rows]
    overlay = {"version": "terra_v1", "status": STATUS, "claim_allowed": False, "human_verified": False, "formal_acceptance_allowed": False, "model_scores_used": False, "pass_a_model": "GPT-5.6 Terra", "pass_b_model": "GPT-5.6 Terra", "adjudicator_model": "GPT-5.6 Terra", "independence": independence, "labeling_guide_sha256": sha(GUIDE), "input_sha256": pre["input_sha256"], "agreement": {name: {k: value for k, value in report.items() if k in {"total", "agreement_count", "conflict_count", "raw_agreement", "cohen_kappa"}} for name, report in task_reports.items()}, "corrections": corrections, "needs_review_count": sum(x["final_label"] == "NEEDS_REVIEW" for x in final_rows), "template_consistency_audit": template_summary}
    overlay_path = ROOT / "data/manifests/automated_label_corrections_terra_v1.json"
    overlay_path.write_text(json.dumps(overlay, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"status": STATUS, "claim_allowed": False, "human_verified": False, "formal_acceptance_allowed": False, "independence": independence, "labeling_guide_sha256": sha(GUIDE), "input_sha256": pre["input_sha256"], "output_sha256": {path.name: sha(path) for path in output.glob("*.csv")}, "overlay_path": str(overlay_path.relative_to(ROOT)).replace("\\", "/"), "overlay_sha256": sha(overlay_path)}
    (output / "automated_annotation_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {"status": STATUS, "tasks": task_reports, "qa_failures": qa, "high_risk_ids": risk, "needs_review_count": overlay["needs_review_count"], "quarantine_count": None, "template_consistency_audit": template_summary, "declaration": "本次结果是 GPT-5.6 Terra 自动多轮审计标签，不是两名真人独立标注，不能用于正式双人金标声明。", "eligibility": {"exploratory_validation_only_v7": not qa and not inconsistencies, "formal_validation_only_v7": False, "locked_test": False}}
    (output / "automated_annotation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "finalize"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--independence", choices=("true", "false"), required=True)
    args = parser.parse_args()
    (prepare if args.command == "prepare" else finalize)(args.output_dir, args.independence == "true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
