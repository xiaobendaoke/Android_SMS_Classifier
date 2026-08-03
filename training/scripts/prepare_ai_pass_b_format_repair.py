#!/usr/bin/env python3
"""Prepare a new blind DeepSeek B batch only for missing valid JSONL output."""
from __future__ import annotations

import csv
import hashlib
import json

from prepare_ai_annotation_run import PASS_B_ID, PASS_B_MODEL, ROOT, prompt_text, runner_text, sha256


def main() -> int:
    out = ROOT / "data/interim/annotation/automated_runs/ai_annotation_20260802_r1"
    manifest_path = out / "automated_annotation_manifest.json"; manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if any(c.get("format_repair") and c["pass"] == "b" for c in manifest["calls"]): raise SystemExit("Pass B format repair is already prepared")
    sources = []
    for task, key_name, rel in (("label_conflicts", "review_group_id", "data/interim/annotation/label_conflicts_v2/blind_annotator_B.csv"), ("transaction_specialist", "review_id", "data/interim/annotation/transaction_specialist_v2/specialist_annotator_B.csv")):
        with (ROOT / rel).open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle): sources.append({"task":task,"review_key":(row[key_name] or "").strip(),"id":(row["id"] or "").strip(),"text":(row["text"] or "").strip()})
    expected = {(r["review_key"],r["id"]) for r in sources}; valid=set()
    for call in manifest["calls"]:
        if call["pass"] != "b": continue
        for line in (out / "stdout" / f"{call['slug']}.txt").read_text(encoding="utf-8").splitlines():
            try: value=json.loads(line)
            except json.JSONDecodeError: continue
            if isinstance(value,dict) and {"review_key","id","label","notes"}.issubset(value): valid.add((str(value["review_key"]).strip(),str(value["id"]).strip()))
    covered=valid & expected; unexpected=valid-expected; missing=[r for r in sources if (r["review_key"],r["id"]) not in covered]
    if not missing: raise SystemExit("No missing expected B records require format repair")
    prompt=out/"prompts"/"b_format_repair_001.txt"; prompt.write_text(prompt_text(PASS_B_ID,"format_repair",missing,(ROOT.parent/"docs/labeling-guide.md").read_text(encoding="utf-8")),encoding="utf-8")
    stdout=out/"stdout"/"b_format_repair_001.txt"; stderr=out/"stderr"/"b_format_repair_001.txt"; status=out/"status"/"b_format_repair_001.txt"; runner=out/"runners"/"b_format_repair_001.sh"
    runner.write_text(runner_text(PASS_B_MODEL,prompt,stdout,stderr,status),encoding="utf-8"); runner.chmod(0o700)
    call={"slug":"b_format_repair_001","task":"format_repair","pass":"b","model":PASS_B_MODEL,"annotator_id":PASS_B_ID,"count":len(missing),"prompt_sha256":sha256(prompt),"input_sha256":hashlib.sha256(json.dumps(missing,ensure_ascii=False,separators=(",",":")).encode("utf-8")).hexdigest(),"runner":str(runner.relative_to(out)),"format_repair":True}
    for item in manifest["calls"]:
        if item["pass"]=="b" and not item.get("format_repair"): item["tolerate_malformed_jsonl"]=True
    manifest["calls"].append(call); manifest["pass_b_format_repair"]={"original_valid_rows":len(covered),"unexpected_valid_pairs":len(unexpected),"missing_rows":len(missing),"original_format_deviation":True}
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    script=out/"run_pass_b_format_repair.sh"; script.write_text("#!/usr/bin/env bash\nset -euo pipefail\nbash "+str(runner)+"\n",encoding="utf-8"); script.chmod(0o700)
    print(json.dumps({"original_valid_rows":len(covered),"unexpected_valid_pairs":len(unexpected),"repair_rows":len(missing),"claim_allowed":False},ensure_ascii=False))
    return 0

if __name__ == "__main__": raise SystemExit(main())
