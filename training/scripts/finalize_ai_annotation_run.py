#!/usr/bin/env python3
"""Validate blind A/B output, prepare C, and finalize provisional AI labels."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from prepare_ai_annotation_run import (
    ALLOWED,
    GUIDE,
    PASS_A_ID,
    PASS_B_ID,
    ROOT,
    chunks,
    prompt_text,
    runner_text,
    sha256,
)

PASS_C_ID = "AI_DEEPSEEK_XOPDEEPSEEKV4FLASH_ADJUDICATOR_001"
PASS_C_MODEL = "xfyun/xopdeepseekv4flash"
PACKS = {
    "label_conflicts": ("review_group_id", ROOT / "data/interim/annotation/label_conflicts_v2/blind_annotator_A.csv", ROOT / "data/interim/annotation/label_conflicts_v2/blind_annotator_B.csv"),
    "transaction_specialist": ("review_id", ROOT / "data/interim/annotation/transaction_specialist_v2/specialist_annotator_A.csv", ROOT / "data/interim/annotation/transaction_specialist_v2/specialist_annotator_B.csv"),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle)]


def pair(row: dict[str, str]) -> tuple[str, str]:
    return row["review_key"], row["id"]


def status_ok(path: Path) -> bool:
    return path.exists() and "exit_code=0" in path.read_text(encoding="utf-8")


def parse_jsonl(path: Path, expected: set[tuple[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    if not path.exists():
        raise ValueError(f"missing output: {path}")
    result: dict[tuple[str, str], dict[str, str]] = {}
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"non-JSON output {path}:{line_no}: {exc.msg}") from exc
        if not isinstance(value, dict) or not {"review_key", "id", "label", "notes"}.issubset(value):
            raise ValueError(f"invalid output schema {path}:{line_no}")
        row = {field: str(value[field]).strip() for field in ("review_key", "id", "label", "notes")}
        key = pair(row)
        if key not in expected or key in result:
            raise ValueError(f"unexpected or duplicate record {path}:{line_no}")
        if row["label"] not in ALLOWED or not row["notes"]:
            raise ValueError(f"invalid label or empty notes {path}:{line_no}")
        result[key] = row
    return result


def parse_jsonl_tolerant(path: Path, expected: set[tuple[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    """Keep only independently valid expected rows from an audited malformed response."""
    result: dict[tuple[str, str], dict[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict) or not {"review_key", "id", "label", "notes"}.issubset(value):
            continue
        row = {field: str(value[field]).strip() for field in ("review_key", "id", "label", "notes")}
        key = pair(row)
        if key in expected and key not in result and row["label"] in ALLOWED and row["notes"]:
            result[key] = row
    return result


def kappa(left: list[str], right: list[str]) -> float:
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    ca, cb = Counter(left), Counter(right)
    expected = sum(ca[label] * cb[label] for label in ALLOWED) / (len(left) ** 2)
    return 1.0 if expected == 1.0 else (observed - expected) / (1 - expected)


def source_rows() -> dict[str, dict[str, list[dict[str, str]]]]:
    result: dict[str, dict[str, list[dict[str, str]]]] = {}
    for task, (key_name, path_a, path_b) in PACKS.items():
        result[task] = {}
        for pass_key, path in (("a", path_a), ("b", path_b)):
            rows = read_csv(path)
            if any(row.get("label") or row.get("notes") or row.get("human_annotator_id") for row in rows):
                raise ValueError(f"blind input is no longer blank: {path}")
            result[task][pass_key] = [{"review_key": row[key_name], "id": row["id"], "text": row["text"]} for row in rows]
    return result


def load_pass(out: Path, manifest: dict, pass_key: str, sources: dict) -> dict[str, dict[tuple[str, str], dict[str, str]]]:
    result: dict[str, dict[tuple[str, str], dict[str, str]]] = {task: {} for task in PACKS}
    task_for_pair = {
        (row["review_key"], row["id"]): task
        for task in PACKS
        for row in sources[task][pass_key]
    }
    expected_all = set(task_for_pair)
    for call in manifest["calls"]:
        if call["pass"] != pass_key:
            continue
        expected = expected_all if call.get("format_repair") else {
            (row["review_key"], row["id"])
            for row in sources[call["task"]][pass_key]
        }
        slug = call["slug"]
        if not status_ok(out / "status" / f"{slug}.txt"):
            raise ValueError(f"call did not complete successfully: {slug}")
        parser = parse_jsonl_tolerant if call.get("tolerate_malformed_jsonl") else parse_jsonl
        parsed = parser(out / "stdout" / f"{slug}.txt", expected)
        for key, row in parsed.items():
            task = task_for_pair[key]
            if key in result[task]:
                continue
            result[task][key] = row
    for task in PACKS:
        expected = {(row["review_key"], row["id"]) for row in sources[task][pass_key]}
        if set(result[task]) != expected:
            raise ValueError(f"incomplete pass {pass_key}: {task}")
    return result


def c_prompt(task: str, rows: list[dict[str, str]]) -> str:
    guide = GUIDE.read_text(encoding="utf-8")
    return "\n".join([
        f"ANNOTATOR_ID: {PASS_C_ID}",
        f"TASK: {task} conflict adjudication",
        "You are the independent automated adjudicator. You receive only a message body, Pass A label/notes, Pass B label/notes, and the labeling guide.",
        "Read each full message. Return exactly one JSON object per row as JSONL, with no markdown or extra prose.",
        'Each object must be: {"review_key":"...","id":"...","label":"TRANSACTION|AD|HARASS|FRAUD|NEEDS_REVIEW","notes":"primary intent; decisive evidence; reason to reject A; reason to reject B"}.',
        "LABELING GUIDE:", guide.strip(), "CONFLICT RECORDS:",
        json.dumps(rows, ensure_ascii=False, separators=(",", ":")), "",
    ])


def prepare_c(out: Path, manifest: dict) -> None:
    sources = source_rows()
    a, b = load_pass(out, manifest, "a", sources), load_pass(out, manifest, "b", sources)
    conflicts: dict[str, list[dict[str, str]]] = {}
    report: dict[str, object] = {"status": "PENDING_PROVISIONAL_ADJUDICATION", "claim_allowed": False, "human_verified": False, "formal_acceptance_allowed": False, "annotator_ids": {"pass_a": PASS_A_ID, "pass_b": PASS_B_ID, "pass_c": PASS_C_ID}, "tasks": {}}
    c_calls: list[dict] = []
    for task in PACKS:
        by_text = {(row["review_key"], row["id"]): row["text"] for row in sources[task]["a"]}
        rows = []
        labels_a, labels_b = [], []
        for key in sorted(a[task]):
            left, right = a[task][key], b[task][key]
            labels_a.append(left["label"]); labels_b.append(right["label"])
            if left["label"] != right["label"]:
                rows.append({"review_key": key[0], "id": key[1], "text": by_text[key], "pass_a_label": left["label"], "pass_a_notes": left["notes"], "pass_b_label": right["label"], "pass_b_notes": right["notes"]})
        conflicts[task] = rows
        report["tasks"][task] = {"total": len(labels_a), "agreement_count": len(labels_a) - len(rows), "conflict_count": len(rows), "raw_agreement": (len(labels_a) - len(rows)) / len(labels_a), "cohen_kappa": kappa(labels_a, labels_b), "pass_a_distribution": dict(Counter(labels_a)), "pass_b_distribution": dict(Counter(labels_b))}
        for index, batch in enumerate(chunks(rows, int(manifest["batch_size"])), start=1):
            slug = f"c_{task}_{index:03d}"
            prompt = out / "prompts" / f"{slug}.txt"; stdout = out / "stdout" / f"{slug}.txt"; stderr = out / "stderr" / f"{slug}.txt"; status = out / "status" / f"{slug}.txt"; runner = out / "runners" / f"{slug}.sh"
            prompt.write_text(c_prompt(task, batch), encoding="utf-8")
            runner.write_text(runner_text(PASS_C_MODEL, prompt, stdout, stderr, status), encoding="utf-8"); runner.chmod(0o700)
            c_calls.append({"slug": slug, "task": task, "pass": "c", "model": PASS_C_MODEL, "annotator_id": PASS_C_ID, "count": len(batch), "prompt_sha256": sha256(prompt), "input_sha256": hashlib.sha256(json.dumps(batch, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest(), "runner": str(runner.relative_to(out))})
    (out / "pre_adjudication.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    script = out / "run_pass_c.sh"
    lines = ["#!/usr/bin/env bash", "set -u", "failed=0"]
    for call in c_calls:
        lines += [f"bash {out / call['runner']}", "rc=$?", "if [[ $rc -ne 0 ]]; then failed=1; fi"]
    lines += ["exit $failed", ""]
    script.write_text("\n".join(lines), encoding="utf-8"); script.chmod(0o700)
    manifest["calls"].extend(c_calls); manifest["status"] = "PREPARED_PASS_C_PROVISIONAL_AUTOMATED_MULTI_PASS"
    (out / "automated_annotation_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "conflicts": {k: len(v) for k, v in conflicts.items()}, "pass_c_calls": len(c_calls)}, ensure_ascii=False))


def prepare_resume_c(out: Path, manifest: dict) -> None:
    """Preserve incomplete Pass C artifacts and run only calls without success status."""
    calls = [call for call in manifest["calls"] if call["pass"] == "c"]
    if not calls:
        raise ValueError("Pass C has not been prepared")
    existing_attempts = [
        int(match.group(1))
        for path in (out / "interrupted").glob("pass_c_resume_*")
        if (match := re.fullmatch(r"pass_c_resume_(\d{3})", path.name))
    ]
    attempt = max(existing_attempts, default=0) + 1
    recovery = out / "interrupted" / f"pass_c_resume_{attempt:03d}"
    recovery.mkdir(parents=True, exist_ok=True)
    preserved: list[dict[str, str]] = []
    pending: list[dict] = []
    for call in calls:
        slug = call["slug"]
        status = out / "status" / f"{slug}.txt"
        if status_ok(status):
            continue
        for kind in ("stdout", "stderr", "status"):
            source = out / kind / f"{slug}.txt"
            if not source.exists():
                continue
            target = recovery / f"{slug}.{kind}.txt"
            if target.exists():
                raise ValueError(f"refusing to overwrite preserved artifact: {target}")
            digest = sha256(source)
            source.rename(target)
            preserved.append({"slug": slug, "kind": kind, "sha256": digest, "path": str(target.relative_to(out))})
        pending.append(call)
    script = out / f"run_pass_c_resume_{attempt:03d}.sh"
    lines = ["#!/usr/bin/env bash", "set -u", "failed=0"]
    for call in pending:
        lines += [f"bash {out / call['runner']}", "rc=$?", "if [[ $rc -ne 0 ]]; then failed=1; fi"]
    lines += ["exit $failed", ""]
    script.write_text("\n".join(lines), encoding="utf-8")
    script.chmod(0o700)
    (recovery / "manifest.json").write_text(
        json.dumps({"status": "PRESERVED_INCOMPLETE_PASS_C_OUTPUT", "preserved": preserved, "pending_calls": [call["slug"] for call in pending]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest["status"] = "RESUME_PASS_C_PROVISIONAL_AUTOMATED_MULTI_PASS"
    (out / "automated_annotation_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "attempt": attempt, "preserved_files": len(preserved), "pending_calls": len(pending)}, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare-c", "prepare-resume-c"))
    parser.add_argument("--run-id", default="ai_annotation_20260802_r1")
    args = parser.parse_args()
    out = ROOT / "data/interim/annotation/automated_runs" / args.run_id
    manifest = json.loads((out / "automated_annotation_manifest.json").read_text(encoding="utf-8"))
    if args.command == "prepare-c":
        prepare_c(out, manifest)
    elif args.command == "prepare-resume-c":
        prepare_resume_c(out, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
