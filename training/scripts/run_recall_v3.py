#!/usr/bin/env python3
"""Shared implementation for the leakage-safe Recall training pipeline.

Default mode is validation-only against processed_v2. Quantization, locked-test
evaluation, and Android export require an explicit --unlock-locked-test after
all audits pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent

PROCESSED_V2 = ROOT / "data" / "processed_v2"
ASSIGNMENT_V2 = ROOT / "data" / "manifests" / "split_assignment_v2.json"
DATASET_V2 = ROOT / "data" / "manifests" / "dataset_manifest_v2.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Train teacher/dual-head student and evaluate the v2 validation "
            "pipeline. Locked test / quantize / Android export remain gated."
        )
    )
    parser.add_argument(
        "--teacher-model-path",
        type=Path,
        help="Approved local/intranet teacher model directory.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--run-name",
        choices=["recall_v4", "recall_v5", "recall_v6", "recall_v7"],
        default="recall_v4",
        help="Versioned report/stage prefix.",
    )
    parser.add_argument(
        "--skip-teacher",
        action="store_true",
        help="Reuse an existing teacher_logits_manifest.json.",
    )
    parser.add_argument(
        "--unlock-locked-test",
        action="store_true",
        help=(
            "Explicitly unlock quantization, locked-test evaluation, and "
            "Android export after validation gates and provenance audits pass."
        ),
    )
    return parser


def run(script: str, *args: str) -> None:
    command = [sys.executable, str(ROOT / "scripts" / script), *args]
    print("RUN", " ".join(command), flush=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    completed = subprocess.run(command, cwd=REPO, env=env)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_v2_startup() -> list[str]:
    """Blockers that forbid even validation-only v7 startup."""
    blockers: list[str] = []
    if not ASSIGNMENT_V2.exists():
        blockers.append("missing split_assignment_v2.json")
        return blockers
    if not DATASET_V2.exists():
        blockers.append("missing dataset_manifest_v2.json")
        return blockers
    if not PROCESSED_V2.exists():
        blockers.append("missing processed_v2/")
        return blockers

    assignment = json.loads(ASSIGNMENT_V2.read_text(encoding="utf-8"))
    dataset = json.loads(DATASET_V2.read_text(encoding="utf-8"))
    if assignment.get("claim_allowed"):
        blockers.append("assignment_v2 claim_allowed unexpectedly true")
    if dataset.get("claim_allowed"):
        blockers.append("dataset_manifest_v2 claim_allowed unexpectedly true")
    if assignment.get("replacement_policy") != "none":
        blockers.append("assignment_v2 replacement_policy must be none")
    if assignment.get("removal_policy") != "text_quality_only":
        blockers.append("assignment_v2 removal_policy must be text_quality_only")
    if assignment.get("model_scores_used") is not False:
        blockers.append("assignment_v2 model_scores_used must be false")

    for split_name in ("train", "validation", "test"):
        path = PROCESSED_V2 / f"{split_name}.jsonl"
        if not path.exists():
            blockers.append(f"missing processed_v2/{split_name}.jsonl")
            continue
        actual = sha256_file(path)
        expected = assignment["splits"][split_name]["sha256"]
        if actual != expected:
            blockers.append(f"{split_name} sha mismatch versus assignment_v2")

    # Validation text quality must be clean for startup.
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_labels.py"),
            "--input",
            str(PROCESSED_V2),
            "--split-assignment",
            str(ASSIGNMENT_V2),
        ],
        cwd=REPO,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        blockers.append("validate_labels.py on processed_v2 FAILED")

    # Human packs must exist and remain unfinished/provisional until closed.
    conflict_manifest = (
        ROOT / "data" / "interim" / "annotation" / "label_conflicts_v2" / "manifest.json"
    )
    specialist_manifest = (
        ROOT
        / "data"
        / "interim"
        / "annotation"
        / "transaction_specialist_v2"
        / "manifest.json"
    )
    for path in (conflict_manifest, specialist_manifest):
        if not path.exists():
            blockers.append(f"missing human pack manifest: {path.name}")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        status = payload.get("status")
        if status in {
            "PENDING_DUAL_HUMAN_ANNOTATION",
            "READY_FOR_HUMAN_ANNOTATION",
            "PENDING_ADJUDICATION",
            "PROVISIONAL_AUTOMATED_REVIEW",
        }:
            blockers.append(f"{path.parent.name}: human annotation incomplete ({status})")
        if payload.get("claim_allowed"):
            blockers.append(f"{path.parent.name}: claim_allowed true without closure")

    # Dataset-level human annotation blocker remains until packs close.
    for blocker in dataset.get("blockers", []):
        if blocker.get("type") == "human_annotation_incomplete":
            blockers.append("dataset_manifest_v2 human_annotation_incomplete")
    return blockers


def audit_unlock_allowed() -> list[str]:
    """Additional blockers for locked-test unlock."""
    blockers = audit_v2_startup()
    # Unlock requires completed dual-human evidence on both packs.
    for rel in (
        "data/interim/annotation/label_conflicts_v2/manifest.json",
        "data/interim/annotation/transaction_specialist_v2/manifest.json",
    ):
        path = ROOT / rel
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("status") != "FROZEN_DUAL_HUMAN_ANNOTATED":
            blockers.append(f"{path.parent.name}: not FROZEN_DUAL_HUMAN_ANNOTATED")
        if not payload.get("dual_human_evidence_complete"):
            blockers.append(f"{path.parent.name}: dual_human_evidence_complete=false")
    return blockers


def run_locked_test_path(seed: str, run_name: str) -> None:
    run(
        "generate_representative_manifest.py",
        "--summary",
        str(ROOT / "reports" / "metrics" / "representative_summary.json"),
        "--seed",
        seed,
    )
    model = ROOT / "artifacts" / "student" / "sms_bytecnn_int8.tflite"
    quant_report = ROOT / "reports" / "metrics" / "quantize.json"
    run(
        "quantize_int8.py",
        "--input-model",
        str(ROOT / "artifacts" / "student" / "sms_bytecnn_fp32.keras"),
        "--output-tflite",
        str(model),
        "--report",
        str(quant_report),
        "--profile",
        "formal",
        "--seed",
        seed,
    )
    run(
        "verify_tflite.py",
        "--keras",
        str(ROOT / "artifacts" / "student" / "sms_bytecnn_fp32.keras"),
        "--tflite",
        str(model),
        "--quant-report",
        str(quant_report),
        "--test",
        str(PROCESSED_V2 / "validation.jsonl"),
        "--seed",
        seed,
    )
    run(
        "evaluate.py",
        "--mode",
        "pipeline",
        "--tflite",
        str(model),
        "--test",
        str(PROCESSED_V2 / "test.jsonl"),
        "--stage",
        f"{run_name}_locked_test_pipeline",
        "--output",
        str(ROOT / "reports" / "metrics" / f"evaluate_{run_name}.json"),
        "--error-samples",
        "40",
        "--error-output",
        str(ROOT / "reports" / "metrics" / f"{run_name}_error_samples.json"),
        "--seed",
        seed,
    )
    run(
        "export_android_assets.py",
        "--model",
        str(model),
        "--quantization",
        "INT8",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    teacher_path = args.teacher_model_path.resolve() if args.teacher_model_path else None
    if not args.skip_teacher and teacher_path is None:
        print("--teacher-model-path is required unless --skip-teacher is used.", file=sys.stderr)
        return 1
    if not args.skip_teacher and teacher_path is not None and not teacher_path.exists():
        print(f"Teacher model path missing: {teacher_path}", file=sys.stderr)
        return 1

    startup_blockers = audit_v2_startup()
    if startup_blockers:
        print(
            json.dumps(
                {
                    "status": "V2_STARTUP_DENIED",
                    "blockers": startup_blockers,
                    "locked_test_reachable": False,
                    "data_root": "training/data/processed_v2",
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 6

    seed = str(args.seed)
    run_name = args.run_name
    if not args.skip_teacher:
        run(
            "train_teacher.py",
            "--config",
            str(ROOT / "configs" / "teacher.yaml"),
            "--model-path",
            str(teacher_path),
            "--seed",
            seed,
        )
    run(
        "distill_student.py",
        "--config",
        str(ROOT / "configs" / "student.yaml"),
        "--seed",
        seed,
    )
    run(
        "evaluate.py",
        "--mode",
        "pipeline",
        "--keras",
        str(ROOT / "artifacts" / "student" / "sms_bytecnn_fp32.keras"),
        "--test",
        str(PROCESSED_V2 / "validation.jsonl"),
        "--stage",
        f"{run_name}_validation_pipeline",
        "--output",
        str(
            ROOT
            / "reports"
            / "metrics"
            / f"validate_{run_name}_pipeline.json"
        ),
        "--require-acceptance",
        "--targets-config",
        str(ROOT / "configs" / "student.yaml"),
        "--seed",
        seed,
    )

    if not args.unlock_locked_test:
        print(
            json.dumps(
                {
                    "status": "VALIDATION_ONLY_COMPLETE",
                    "run_name": run_name,
                    "data_root": "training/data/processed_v2",
                    "locked_test_reachable": False,
                    "note": (
                        "Stopped after validation evaluation. Pass "
                        "--unlock-locked-test only after audits pass."
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    blockers = audit_unlock_allowed()
    if blockers:
        print(
            json.dumps(
                {
                    "status": "UNLOCK_DENIED",
                    "blockers": blockers,
                    "locked_test_reachable": False,
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 5

    run_locked_test_path(seed, run_name)

    manifest = json.loads(
        (ROOT / "artifacts" / "student" / "distill_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    print(
        json.dumps(
            {
                "status": "PIPELINE_OK",
                "best_epoch": manifest.get("best_epoch"),
                "validation": manifest.get("val_metrics"),
                "locked_test_report": (
                    f"training/reports/metrics/evaluate_{run_name}.json"
                ),
                "android_model": (
                    "android/classifier-sdk/src/main/assets/model/"
                    "sms_bytecnn_int8.tflite"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
