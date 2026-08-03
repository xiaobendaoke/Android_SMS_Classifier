#!/usr/bin/env python3
"""Train an isolated Chinese teacher and logits manifest for overlay distillation."""
from __future__ import annotations
import copy, json, os, subprocess, sys
from pathlib import Path
import yaml

TRAINING=Path(__file__).resolve().parent.parent; REPO=TRAINING.parent
RUN="stage2_xfyun_overlay_teacher_20260803_r1"; ART=TRAINING/"artifacts/experiments"/RUN

def main() -> int:
    if ART.exists(): raise SystemExit(f"refusing to overwrite {ART}")
    cfg=copy.deepcopy(yaml.safe_load((TRAINING/"configs/teacher.yaml").read_text(encoding="utf-8")))
    cfg["seed"]=42; cfg["data"]["train_manifest"]="data/processed_xfyun_ai_annotation_20260802_r1/train.jsonl"; cfg["data"]["val_manifest"]="data/processed_xfyun_ai_annotation_20260802_r1/validation.jsonl"
    cfg["output"]["checkpoint_dir"]=str(ART.relative_to(TRAINING)); cfg["output"]["manifest"]=str((ART/"teacher_manifest.json").relative_to(TRAINING))
    ART.mkdir(parents=True); config=ART/"config.yaml"; config.write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False),encoding="utf-8")
    cmd=[sys.executable,str(TRAINING/"scripts/train_teacher.py"),"--config",str(config),"--model-path","/home/colab/hf_cache/bert-base-chinese","--seed","42","--logits-manifest",str(ART/"teacher_logits_manifest.json")]
    rc=subprocess.run(cmd,cwd=REPO,env={**os.environ,"PYTHONPATH":str(TRAINING)}).returncode
    print(json.dumps({"run_id":RUN,"returncode":rc,"locked_test_read":False,"logits_manifest":str(ART/"teacher_logits_manifest.json")},ensure_ascii=False)); return rc
if __name__=="__main__": raise SystemExit(main())
