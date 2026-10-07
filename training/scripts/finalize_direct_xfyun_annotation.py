#!/usr/bin/env python3
"""Finalize direct-xfyun C adjudication into local provisional-only artifacts."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from finalize_ai_annotation_run import PACKS, PASS_A_ID, PASS_B_ID, PASS_C_ID, load_pass, source_rows


TRAINING = Path(__file__).resolve().parent.parent
RUN_ID = "ai_annotation_20260802_r1"
OUT = TRAINING / "data/interim/annotation/automated_runs" / RUN_ID
DIRECT = OUT / "direct_xfyun_pass_c_20260803"
STATUS = "PROVISIONAL_AUTOMATED_MULTI_PASS"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_c(sources: dict) -> dict[str, dict[tuple[str, str], dict[str, str]]]:
    expected_to_task = {(row["review_key"], row["id"]): task for task in PACKS for row in sources[task]["a"]}
    result = {task: {} for task in PACKS}
    for path in sorted((DIRECT / "stdout").glob("c_*.txt")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict) or not {"review_key", "id", "label", "notes"}.issubset(row):
                continue
            normalized = {key: str(row[key]).strip() for key in ("review_key", "id", "label", "notes")}
            pair = (normalized["review_key"], normalized["id"])
            task = expected_to_task.get(pair)
            if task and pair not in result[task] and normalized["label"] in {"TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"} and normalized["notes"]:
                result[task][pair] = normalized
    return result


def main() -> int:
    validation = json.loads((DIRECT / "validation.json").read_text(encoding="utf-8"))
    if not validation["pass"]:
        raise ValueError("direct Pass C validation did not pass")
    sources = source_rows()
    old_manifest = json.loads((OUT / "automated_annotation_manifest.json").read_text(encoding="utf-8"))
    a, b, c = load_pass(OUT, old_manifest, "a", sources), load_pass(OUT, old_manifest, "b", sources), load_c(sources)
    records, corrections, quarantine, template_labels = [], [], [], defaultdict(set)
    for task in PACKS:
        text = {(row["review_key"], row["id"]): row["text"] for row in sources[task]["a"]}
        for pair in sorted(a[task]):
            left, right = a[task][pair], b[task][pair]
            conflict = left["label"] != right["label"]
            final = c[task][pair] if conflict else left
            if conflict and pair not in c[task]:
                raise ValueError(f"missing C result for {pair}")
            method = "DIRECT_XFYUN_PASS_C" if conflict else "AUTOMATED_A_B_AGREEMENT"
            record = {"review_key": pair[0], "id": pair[1], "text": text[pair], "label": final["label"], "status": STATUS, "claim_allowed": False, "human_verified": False, "formal_acceptance_allowed": False, "annotator_ids": [PASS_A_ID, PASS_B_ID] + ([PASS_C_ID] if conflict else []), "resolution_method": method}
            records.append(record)
            corrections.append({"review_key": pair[0], "id": pair[1], "label": final["label"], "resolution_method": method, "text_sha256": hashlib.sha256(text[pair].encode("utf-8")).hexdigest()})
            template_labels[pair[0].split("|", 1)[0]].add(final["label"])
            if final["label"] == "NEEDS_REVIEW":
                quarantine.append({key: record[key] for key in ("review_key", "id", "label", "status", "resolution_method")})
    processed = TRAINING / "data" / f"processed_{RUN_ID}"
    processed.mkdir(parents=True, exist_ok=True)
    (processed / "provisional_labels.jsonl").write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n", encoding="utf-8")
    (processed / "quarantine.json").write_text(json.dumps(quarantine, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    template_audit = {key: sorted(value) for key, value in template_labels.items() if len(value) > 1}
    report = {"run_id": RUN_ID, "status": STATUS, "claim_allowed": False, "human_verified": False, "formal_acceptance_allowed": False, "transport": "direct_openai_sdk_xfyun_v2", "counts": {"total": len(records), "quarantine": len(quarantine), "resolved_by_c": len(corrections) - sum(1 for row in records if row["resolution_method"] == "AUTOMATED_A_B_AGREEMENT")}, "label_distribution": dict(Counter(row["label"] for row in records)), "pass_c_validation": validation, "template_consistency_audit": {"inconsistent_review_groups": len(template_audit), "groups": template_audit}, "inputs": old_manifest["inputs"]}
    (DIRECT / "automated_annotation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DIRECT / f"automated_label_corrections_{RUN_ID}.json").write_text(json.dumps({"run_id": RUN_ID, "status": STATUS, "claim_allowed": False, "corrections": corrections}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    direct_manifest = json.loads((DIRECT / "manifest.json").read_text(encoding="utf-8"))
    direct_manifest.update({"status": STATUS, "claim_allowed": False, "human_verified": False, "formal_acceptance_allowed": False, "output_sha256": {"report": sha256(DIRECT / "automated_annotation_report.json"), "corrections": sha256(DIRECT / f"automated_label_corrections_{RUN_ID}.json"), "processed": sha256(processed / "provisional_labels.jsonl")}})
    (DIRECT / "automated_annotation_manifest.json").write_text(json.dumps(direct_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"total": len(records), "quarantine": len(quarantine), "status": STATUS}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
