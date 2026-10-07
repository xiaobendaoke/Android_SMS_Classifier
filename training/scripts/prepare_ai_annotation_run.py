#!/usr/bin/env python3
"""Prepare isolated GLM/DeepSeek blind annotation calls without copying labels."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
GUIDE = REPO / "docs" / "labeling-guide.md"
RUN_ID_DEFAULT = "ai_annotation_20260802_r1"
PASS_A_ID = "AI_GLM_XOPGLM52_PASS_A_001"
PASS_B_ID = "AI_DEEPSEEK_XOPDEEPSEEKV4FLASH_PASS_B_001"
PASS_A_MODEL = "xfyun/xopglm52"
PASS_B_MODEL = "xfyun/xopdeepseekv4flash"
ALLOWED = ("TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle)]


def chunks(rows: list[dict[str, str]], size: int) -> Iterable[list[dict[str, str]]]:
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def prompt_text(pass_id: str, task: str, rows: list[dict[str, str]], guide: str) -> str:
    records = [
        {
            "review_key": row["review_key"],
            "id": row["id"],
            "text": row["text"],
        }
        for row in rows
    ]
    return "\n".join(
        [
            f"ANNOTATOR_ID: {pass_id}",
            f"TASK: {task}",
            "You are an automated blind SMS annotator. Read every full message independently.",
            "You receive only review_key, id, text, and this labeling guide. Do not infer prior labels, model predictions, scores, test membership, or another pass.",
            "Return exactly one JSON object per input row as JSONL. Do not use markdown, prose before or after the JSONL, or code fences.",
            'Each object must be: {"review_key":"...","id":"...","label":"TRANSACTION|AD|HARASS|FRAUD|NEEDS_REVIEW","notes":"..."}.',
            "notes must be non-empty Chinese text stating the primary intent, decisive evidence, and why the closest confusing class is excluded.",
            "Never label surveys or satisfaction requests as TRANSACTION. Active loan marketing is not TRANSACTION. Do not call FRAUD without fraud evidence. Garbled content must be NEEDS_REVIEW.",
            "LABELING GUIDE:",
            guide.strip(),
            "INPUT RECORDS:",
            json.dumps(records, ensure_ascii=False, separators=(",", ":")),
            "",
        ]
    )


def runner_text(model: str, prompt: Path, stdout: Path, stderr: Path, status: Path) -> str:
    command = f"opencode run --model {model} \"$(cat {prompt})\""
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -u -o pipefail",
            f"mkdir -p {stdout.parent} {stderr.parent} {status.parent}",
            "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)",
            "set +e",
            f"bash -ic '{command}' >{stdout} 2>{stderr}",
            "rc=$?",
            "set -e",
            "ended_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)",
            "{",
            f"  printf 'model={model}\\n'",
            "  printf 'started_at=%s\\n' \"$started_at\"",
            "  printf 'ended_at=%s\\n' \"$ended_at\"",
            "  printf 'exit_code=%s\\n' \"$rc\"",
            f"  sha256sum {prompt} {stdout} {stderr}",
            f"}} >{status}",
            "exit \"$rc\"",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=RUN_ID_DEFAULT)
    parser.add_argument("--batch-size", type=int, default=40)
    args = parser.parse_args()
    if not 25 <= args.batch_size <= 50:
        raise SystemExit("--batch-size must be between 25 and 50")

    out = ROOT / "data" / "interim" / "annotation" / "automated_runs" / args.run_id
    if out.exists():
        raise SystemExit(f"Refusing to overwrite existing run: {out}")
    guide = GUIDE.read_text(encoding="utf-8")
    packs = [
        ("label_conflicts", "review_group_id", ROOT / "data/interim/annotation/label_conflicts_v2/blind_annotator_A.csv", ROOT / "data/interim/annotation/label_conflicts_v2/blind_annotator_B.csv"),
        ("transaction_specialist", "review_id", ROOT / "data/interim/annotation/transaction_specialist_v2/specialist_annotator_A.csv", ROOT / "data/interim/annotation/transaction_specialist_v2/specialist_annotator_B.csv"),
    ]
    manifest: dict[str, object] = {
        "run_id": args.run_id,
        "status": "PREPARED_PROVISIONAL_AUTOMATED_MULTI_PASS",
        "claim_allowed": False,
        "human_verified": False,
        "formal_acceptance_allowed": False,
        "models": {"pass_a": PASS_A_MODEL, "pass_b": PASS_B_MODEL},
        "annotator_ids": {"pass_a": PASS_A_ID, "pass_b": PASS_B_ID},
        "labeling_guide_sha256": sha256(GUIDE),
        "batch_size": args.batch_size,
        "inputs": {},
        "calls": [],
    }
    runners_by_pass: dict[str, list[Path]] = {"a": [], "b": []}
    out.mkdir(parents=True)
    for task, key, path_a, path_b in packs:
        for pass_key, pass_id, model, source in (
            ("a", PASS_A_ID, PASS_A_MODEL, path_a),
            ("b", PASS_B_ID, PASS_B_MODEL, path_b),
        ):
            rows = read_csv(source)
            required = {key, "id", "text", "label", "notes", "human_annotator_id"}
            if not rows or not required.issubset(rows[0]):
                raise SystemExit(f"Invalid blind schema: {source}")
            if any(row["label"] or row["notes"] or row["human_annotator_id"] for row in rows):
                raise SystemExit(f"Blind input is not empty: {source}")
            normalized = [{"review_key": row[key], "id": row["id"], "text": row["text"]} for row in rows]
            if len({(row["review_key"], row["id"]) for row in normalized}) != len(normalized):
                raise SystemExit(f"Duplicate review_key/id pair: {source}")
            manifest["inputs"][f"{task}_{pass_key}"] = {"path": str(source.relative_to(ROOT)), "sha256": sha256(source), "count": len(normalized)}
            for batch_index, batch in enumerate(chunks(normalized, args.batch_size), start=1):
                slug = f"{pass_key}_{task}_{batch_index:03d}"
                prompt = out / "prompts" / f"{slug}.txt"
                stdout = out / "stdout" / f"{slug}.txt"
                stderr = out / "stderr" / f"{slug}.txt"
                status = out / "status" / f"{slug}.txt"
                runner = out / "runners" / f"{slug}.sh"
                prompt.parent.mkdir(parents=True, exist_ok=True)
                runner.parent.mkdir(parents=True, exist_ok=True)
                prompt.write_text(prompt_text(pass_id, task, batch, guide), encoding="utf-8")
                runner.write_text(runner_text(model, prompt, stdout, stderr, status), encoding="utf-8")
                runner.chmod(0o700)
                runners_by_pass[pass_key].append(runner)
                manifest["calls"].append({"slug": slug, "task": task, "pass": pass_key, "model": model, "annotator_id": pass_id, "count": len(batch), "prompt_sha256": sha256(prompt), "input_sha256": hashlib.sha256(json.dumps(batch, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest(), "runner": str(runner.relative_to(out))})
    for pass_key, runners in runners_by_pass.items():
        script = out / f"run_pass_{pass_key}.sh"
        lines = ["#!/usr/bin/env bash", "set -u", "failed=0"]
        for runner in runners:
            lines += [f"bash {runner}", "rc=$?", "if [[ $rc -ne 0 ]]; then failed=1; fi"]
        lines += ["exit $failed", ""]
        script.write_text("\n".join(lines), encoding="utf-8")
        script.chmod(0o700)
    (out / "automated_annotation_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"run_id": args.run_id, "output": str(out), "calls": len(manifest["calls"]), "pass_a_calls": len(runners_by_pass["a"]), "pass_b_calls": len(runners_by_pass["b"]), "claim_allowed": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
