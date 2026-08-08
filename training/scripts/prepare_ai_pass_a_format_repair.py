#!/usr/bin/env python3
"""Prepare a new blind GLM batch only for records missing valid JSONL output."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from prepare_ai_annotation_run import PASS_A_ID, PASS_A_MODEL, ROOT, prompt_text, runner_text, sha256


def source_rows() -> list[dict[str, str]]:
    paths = [
        ("label_conflicts", "review_group_id", ROOT / "data/interim/annotation/label_conflicts_v2/blind_annotator_A.csv"),
        ("transaction_specialist", "review_id", ROOT / "data/interim/annotation/transaction_specialist_v2/specialist_annotator_A.csv"),
    ]
    result = []
    for task, key_name, path in paths:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                result.append({"task": task, "review_key": (row[key_name] or "").strip(), "id": (row["id"] or "").strip(), "text": (row["text"] or "").strip()})
    return result


def valid_pairs(out: Path) -> set[tuple[str, str]]:
    manifest = json.loads((out / "automated_annotation_manifest.json").read_text(encoding="utf-8"))
    result = set()
    for call in manifest["calls"]:
        if call["pass"] != "a" or call.get("format_repair"):
            continue
        path = out / "stdout" / f"{call['slug']}.txt"
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and {"review_key", "id", "label", "notes"}.issubset(value):
                result.add((str(value["review_key"]).strip(), str(value["id"]).strip()))
    return result


def main() -> int:
    out = ROOT / "data/interim/annotation/automated_runs/ai_annotation_20260802_r1"
    manifest_path = out / "automated_annotation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if any(call.get("format_repair") for call in manifest["calls"]):
        raise SystemExit("Pass A format repair is already prepared")
    rows = source_rows()
    expected = {(row["review_key"], row["id"]) for row in rows}
    valid = valid_pairs(out)
    covered = valid.intersection(expected)
    unexpected = valid.difference(expected)
    missing = [row for row in rows if (row["review_key"], row["id"]) not in covered]
    if not missing:
        raise SystemExit("No missing expected records require format repair")
    prompt = out / "prompts" / "a_format_repair_001.txt"
    prompt.write_text(prompt_text(PASS_A_ID, "format_repair", missing, (ROOT.parent / "docs/labeling-guide.md").read_text(encoding="utf-8")), encoding="utf-8")
    stdout = out / "stdout" / "a_format_repair_001.txt"; stderr = out / "stderr" / "a_format_repair_001.txt"; status = out / "status" / "a_format_repair_001.txt"; runner = out / "runners" / "a_format_repair_001.sh"
    runner.write_text(runner_text(PASS_A_MODEL, prompt, stdout, stderr, status), encoding="utf-8"); runner.chmod(0o700)
    call = {"slug": "a_format_repair_001", "task": "format_repair", "pass": "a", "model": PASS_A_MODEL, "annotator_id": PASS_A_ID, "count": len(missing), "prompt_sha256": sha256(prompt), "input_sha256": hashlib.sha256(json.dumps(missing, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest(), "runner": str(runner.relative_to(out)), "format_repair": True}
    for item in manifest["calls"]:
        if item["pass"] == "a" and not item.get("format_repair"):
            item["tolerate_malformed_jsonl"] = True
    manifest["calls"].append(call)
    manifest["pass_a_format_repair"] = {"original_valid_rows": len(covered), "unexpected_valid_pairs": len(unexpected), "missing_rows": len(missing), "original_format_deviation": True}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    script = out / "run_pass_a_format_repair.sh"
    script.write_text("#!/usr/bin/env bash\nset -euo pipefail\nbash " + str(runner) + "\n", encoding="utf-8"); script.chmod(0o700)
    print(json.dumps({"original_valid_rows": len(covered), "unexpected_valid_pairs": len(unexpected), "repair_rows": len(missing), "claim_allowed": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
