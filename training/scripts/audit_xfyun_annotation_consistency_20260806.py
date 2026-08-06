#!/usr/bin/env python3
"""Aggregate AI annotation QA evidence without raw text or sample IDs."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
RUN = "stage2_xfyun_annotation_consistency_audit_20260806_r1"
REPORTS = ROOT / "reports" / "experiments"

INPUTS = {
    "ai_annotation_20260802_r1": {
        "report": "ai_annotation_20260802_r1_direct_xfyun_export/automated_annotation_report.json",
        "manifest": "ai_annotation_20260802_r1_direct_xfyun_export/automated_annotation_manifest.json",
    },
    "xfyun_error_relabel_20260803_r1": {
        "qa": "xfyun_error_relabel_20260803_r1_export/qa_summary.json",
        "overlay": "xfyun_error_relabel_20260803_r1_export/overlay_summary.json",
    },
    "xfyun_carrier_repayment_relabel_20260804_r1": {
        "qa": "xfyun_carrier_repayment_relabel_20260804_r1/qa_summary.json",
        "overlay": "xfyun_carrier_repayment_relabel_20260804_r1/overlay_summary.json",
    },
    "xfyun_unmatched_transaction_relabel_20260805_r1": {
        "preparation": "xfyun_unmatched_transaction_relabel_20260805_r1_export/preparation_result.json",
    },
}


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def pass_counts(payload: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in ("pass_a", "pass_b", "pass_c"):
        item = payload.get(key)
        if isinstance(item, dict):
            out[key] = {
                "valid": item.get("valid"),
                "missing": item.get("missing"),
                "malformed": item.get("malformed"),
            }
    return out


def candidate_count(payload: Dict[str, Any]) -> Any:
    agreement = payload.get("agreement", {})
    if isinstance(agreement, dict) and agreement.get("common_valid") is not None:
        return agreement.get("common_valid")
    independence = payload.get("independence")
    if isinstance(independence, dict) and independence.get("common_valid") is not None:
        return independence.get("common_valid")
    blind = payload.get("blind_input")
    if isinstance(blind, dict):
        pass_a = blind.get("pass_a")
        if isinstance(pass_a, dict) and pass_a.get("count") is not None:
            return pass_a.get("count")
    return None


def aggregate_qa(run_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    agreement = payload.get("agreement", {})
    return {
        "run": run_name,
        "status": payload.get("status"),
        "claim_allowed": payload.get("claim_allowed"),
        "human_verified": payload.get("human_verified"),
        "formal_acceptance_allowed": payload.get("formal_acceptance_allowed"),
        "locked_test_read": payload.get("locked_test_read"),
        "passes": pass_counts(payload),
        "agreement": {
            "common_valid": agreement.get("common_valid"),
            "conflict_count": agreement.get("conflict_count"),
            "exact_agreement": agreement.get("exact_agreement"),
        },
        "candidate_count": candidate_count(payload),
        "final_label_counts": payload.get("final_label_counts"),
    }


def aggregate_overlay(run_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    manifest = payload.get("overlay_manifest", {})
    return {
        "run": run_name,
        "overlay_sha256": payload.get("overlay_sha256"),
        "correction_count": payload.get("correction_count"),
        "needs_review_count": payload.get("needs_review_count"),
        "transition_counts": payload.get("transition_counts"),
        "changed_labels": manifest.get("changed_labels"),
        "quarantine_count": manifest.get("quarantine_count"),
        "split_membership_preserved": manifest.get("split_membership_preserved"),
        "locked_test_byte_identical": manifest.get("locked_test_byte_identical"),
        "validation_reference_status": manifest.get("validation_reference_status"),
    }


def aggregate_batch(run_name: str, report: Dict[str, Any], manifest: Dict[str, Any]) -> Dict[str, Any]:
    template_audit = report.get("template_consistency_audit", {})
    groups = template_audit.get("groups", {})
    pair_counts: Counter = Counter()
    for labels in groups.values():
        if isinstance(labels, list) and len(labels) >= 2:
            pair_counts[tuple(sorted(labels))] += 1
    return {
        "run": run_name,
        "status": report.get("status"),
        "transport": report.get("transport") or manifest.get("transport"),
        "model": manifest.get("model"),
        "counts": report.get("counts"),
        "label_distribution": report.get("label_distribution"),
        "pass_c_validation": report.get("pass_c_validation"),
        "inconsistent_template_group_count": template_audit.get("inconsistent_review_groups"),
        "inconsistent_label_pair_counts": {
            "|".join(pair): count for pair, count in sorted(pair_counts.items())
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-root", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    report_dir = args.report_root / RUN
    if report_dir.exists() and not args.force:
        raise SystemExit(f"refusing to overwrite run_id: {RUN}")
    report_dir.mkdir(parents=True, exist_ok=True)

    runs: Dict[str, Any] = {}
    batch = load_json(REPORTS / INPUTS["ai_annotation_20260802_r1"]["report"])
    batch_manifest = load_json(REPORTS / INPUTS["ai_annotation_20260802_r1"]["manifest"])
    runs["ai_annotation_20260802_r1"] = aggregate_batch(
        "ai_annotation_20260802_r1", batch, batch_manifest
    )
    for run_name, paths in INPUTS.items():
        if run_name == "ai_annotation_20260802_r1":
            continue
        run_summary: Dict[str, Any] = {"run": run_name}
        qa_path = paths.get("qa")
        overlay_path = paths.get("overlay")
        prep_path = paths.get("preparation")
        if qa_path:
            qa = load_json(REPORTS / qa_path)
            run_summary["qa"] = aggregate_qa(run_name, qa) if qa else None
        if overlay_path:
            overlay = load_json(REPORTS / overlay_path)
            run_summary["overlay"] = aggregate_overlay(run_name, overlay) if overlay else None
        if prep_path:
            prep = load_json(REPORTS / prep_path)
            run_summary["preparation"] = {
                "status": prep.get("status"),
                "candidate_count": prep.get("candidate_count"),
                "external_send_performed": prep.get("external_send_performed"),
            } if prep else None
        runs[run_name] = run_summary

    documented_ai_rows = {
        "ai_annotation_20260802_r1": batch.get("counts", {}).get("total"),
        "xfyun_error_relabel_20260803_r1": (
            runs["xfyun_error_relabel_20260803_r1"].get("qa") or {}
        ).get("candidate_count"),
        "xfyun_carrier_repayment_relabel_20260804_r1": (
            runs["xfyun_carrier_repayment_relabel_20260804_r1"].get("qa") or {}
        ).get("candidate_count"),
    }
    documented_sum = sum(v for v in documented_ai_rows.values() if isinstance(v, int))

    payload = {
        "run_id": RUN,
        "status": "ANALYSIS_ONLY_NO_CANDIDATE",
        "annotation_status": "PROVISIONAL_AUTOMATED_MULTI_PASS",
        "claim_allowed": False,
        "human_verified": False,
        "formal_acceptance_allowed": False,
        "locked_test_read": False,
        "quantization_run": False,
        "android_export_run": False,
        "analysis_privacy": {
            "raw_sms_text_written": False,
            "raw_sample_ids_written": False,
            "raw_ai_outputs_written": False,
        },
        "documented_ai_arbitrated_row_counts": documented_ai_rows,
        "documented_ai_arbitrated_row_sum": documented_sum,
        "frozen_split_counts": {
            "train": 11221,
            "validation": 1402,
        },
        "runs": runs,
        "decision": "analysis_only_no_candidate",
        "decision_reason": (
            "Aggregate QA shows multi-pass AI arbitration covers only a small subset of "
            "the frozen split; most labels lack multi-pass AI agreement evidence. No "
            "candidate, no locked test read, no human review package generated."
        ),
    }
    (report_dir / "analysis.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "run_id": RUN,
                "documented_ai_arbitrated_row_sum": documented_sum,
                "inconsistent_template_group_count": runs["ai_annotation_20260802_r1"].get(
                    "inconsistent_template_group_count"
                ),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
