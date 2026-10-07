#!/usr/bin/env python3
"""Evaluate model-only and transaction-protected stages on one frozen split."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from scripts.evaluate import main as evaluate_main
    from scripts.evaluate import sha256_file
except ImportError:  # Direct execution from training/scripts.
    from evaluate import main as evaluate_main
    from evaluate import sha256_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare model-only and transaction-protected pipeline stages."
    )
    parser.add_argument(
        "--split",
        type=Path,
        default=ROOT / "data" / "processed" / "validation.jsonl",
        help=(
            "One JSONL split used unchanged for every stage. Defaults to validation; "
            "do not pass locked test until release gates pass."
        ),
    )
    parser.add_argument(
        "--dense-keras",
        type=Path,
        default=ROOT / "artifacts" / "student" / "sms_bytecnn_fp32.keras",
    )
    parser.add_argument(
        "--pruned-keras",
        type=Path,
        default=ROOT / "artifacts" / "student" / "sms_bytecnn_pruned.keras",
    )
    parser.add_argument(
        "--tflite",
        type=Path,
        default=ROOT / "artifacts" / "student" / "sms_bytecnn_int8.tflite",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "metrics" / "stage_comparison.json",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=None,
        help="Per-stage report directory (defaults beside --output).",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--error-samples", type=int, default=0)
    parser.add_argument(
        "--rules-dir",
        type=Path,
        default=ROOT / "rules" / "rules",
    )
    return parser


def _stage_specs(args: argparse.Namespace):
    return [
        ("dense_keras", "keras", args.dense_keras, "--keras"),
        ("dense_pipeline", "pipeline", args.dense_keras, "--keras"),
        ("pruned_keras", "keras", args.pruned_keras, "--keras"),
        ("pruned_pipeline", "pipeline", args.pruned_keras, "--keras"),
        ("tflite", "tflite", args.tflite, "--tflite"),
        ("tflite_pipeline", "pipeline", args.tflite, "--tflite"),
    ]


def run_pipeline(args: argparse.Namespace) -> Dict[str, object]:
    reports_dir = args.reports_dir or (args.output.parent / "pipeline_stages")
    stages: List[Dict[str, object]] = []

    for stage_name, mode, artifact, artifact_flag in _stage_specs(args):
        stage_report = reports_dir / f"{stage_name}.json"
        entry: Dict[str, object] = {
            "stage": stage_name,
            "mode": mode,
            "artifact_path": str(artifact).replace("\\", "/"),
        }
        if not artifact.exists():
            entry.update(
                status="skipped",
                reason=f"artifact_missing: {artifact}",
            )
            print(f"SKIP {stage_name}: artifact missing: {artifact}")
            stages.append(entry)
            continue

        # Never attach metrics from an earlier run when this invocation fails.
        if stage_report.exists():
            stage_report.unlink()
        eval_args = [
            "--test",
            str(args.split),
            "--mode",
            mode,
            artifact_flag,
            str(artifact),
            "--stage",
            stage_name,
            "--output",
            str(stage_report),
            "--seed",
            str(args.seed),
            "--error-samples",
            str(args.error_samples),
            "--rules-dir",
            str(args.rules_dir),
        ]
        if args.error_samples > 0:
            eval_args.extend(
                ["--error-output", str(reports_dir / f"{stage_name}_errors.json")]
            )

        exit_code = evaluate_main(eval_args)
        entry["exit_code"] = exit_code
        entry["report_path"] = str(stage_report).replace("\\", "/")
        entry["status"] = "completed" if exit_code == 0 else "failed"
        if exit_code != 0:
            entry["reason"] = f"evaluation_exit_{exit_code}"

        if stage_report.exists():
            report = json.loads(stage_report.read_text(encoding="utf-8"))
            entry.update(
                data_sha256=report.get("data_sha256"),
                model_sha256=report.get("model_sha256"),
                evaluated_count=report.get("evaluated_count"),
                macro_f1=report.get("macro_f1"),
                transaction_recall=report.get("transaction_recall"),
                error_count=report.get("error_count"),
            )
        stages.append(entry)

    completed = [stage for stage in stages if stage["status"] == "completed"]
    return {
        "split_path": str(args.split).replace("\\", "/"),
        "data_sha256": sha256_file(args.split),
        "stage_order": [
            "dense_keras",
            "dense_pipeline",
            "pruned_keras",
            "pruned_pipeline",
            "tflite",
            "tflite_pipeline",
        ],
        "stages": stages,
        "completed_count": len(completed),
        "skipped_count": sum(s["status"] == "skipped" for s in stages),
        "failed_count": sum(s["status"] == "failed" for s in stages),
        "rule_fallback_used": any(
            stage["stage"].endswith("_pipeline")
            and stage["status"] == "completed"
            for stage in stages
        ),
    }


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.split.exists():
        print(f"Split missing: {args.split}", file=sys.stderr)
        return 1

    comparison = run_pipeline(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote stage comparison to {args.output}")
    return 0 if comparison["failed_count"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
