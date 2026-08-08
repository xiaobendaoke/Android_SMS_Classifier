#!/usr/bin/env python3
"""Distill the ByteCNN from the isolated provisional-overlay teacher logits."""
from __future__ import annotations
import copy, hashlib, json, os, subprocess, sys
from pathlib import Path
import yaml
T=Path(__file__).resolve().parent.parent; R=T.parent
RUN="stage2_xfyun_overlay_student_distill_20260803_r1"; ART=T/"artifacts/experiments"/RUN; REP=T/"reports/experiments"/RUN
TEACHER="artifacts/experiments/stage2_xfyun_overlay_teacher_20260803_r1/teacher_logits_manifest.json"
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if ART.exists() or REP.exists(): raise SystemExit("refusing to overwrite run")
 cfg=copy.deepcopy(yaml.safe_load((T/"configs/student.yaml").read_text(encoding="utf-8")))
 cfg["seed"]=42; cfg["data"]["train_manifest"]="data/processed_xfyun_ai_annotation_20260802_r1/train.jsonl"; cfg["data"]["val_manifest"]="data/processed_xfyun_ai_annotation_20260802_r1/validation.jsonl"; cfg["distillation"]["teacher_manifest"]=TEACHER; cfg["training"]["class_weight_multipliers"]["TRANSACTION"]=1.4; cfg["output"]["checkpoint_dir"]=str(ART.relative_to(T)); cfg["output"]["keras_path"]=str((ART/"sms_bytecnn_fp32.keras").relative_to(T))
 ART.mkdir(parents=True); REP.mkdir(parents=True); c=ART/"config.yaml"; c.write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False),encoding="utf-8")
 rc=subprocess.run([sys.executable,str(T/"scripts/distill_student.py"),"--config",str(c),"--seed","42"],cwd=R,env={**os.environ,"PYTHONPATH":str(T)}).returncode
 m=ART/"distill_manifest.json"; out={"run_id":RUN,"status":"EXPLORATORY_PROVISIONAL_VALIDATION_ONLY","claim_allowed":False,"formal_acceptance_allowed":False,"locked_test_read":False,"quantization_run":False,"android_export_run":False,"seed":42,"only_changed_variable":"distillation.teacher_manifest=isolated_overlay_teacher_logits","config_sha256":sha(c),"returncode":rc}
 if m.exists(): out.update({"val_metrics":json.loads(m.read_text(encoding="utf-8")).get("val_metrics",{}),"best_epoch":json.loads(m.read_text(encoding="utf-8")).get("best_epoch")})
 (REP/"experiment.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps({"run_id":RUN,"returncode":rc,"has_manifest":m.exists()})); return rc
if __name__=="__main__": raise SystemExit(main())
