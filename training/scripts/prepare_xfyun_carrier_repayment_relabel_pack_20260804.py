#!/usr/bin/env python3
"""Prepare local-only blind packs for carrier/repayment transaction misses."""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(ROOT))
from scripts.prepare_transaction_specialist_freeze import coverage_subtype
from src.schema import LABEL_ORDER
from src.train_utils import load_labeled_records, records_to_xy, split_student_logits
RUN="xfyun_carrier_repayment_relabel_20260804_r1"; PACK=ROOT/"data/interim/annotation"/RUN; SAFE=ROOT/"reports/experiments"/f"{RUN}_export"
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if PACK.exists() or SAFE.exists(): raise SystemExit(f"refusing to overwrite run_id: {RUN}")
 import tensorflow as tf
 records=[r for r in load_labeled_records(ROOT/"data/processed_xfyun_error_relabel_20260803_r1/validation.jsonl") if r.language=="zh"]
 model=tf.keras.models.load_model(ROOT/"artifacts/experiments/stage2_xfyun_overlay_txn_weight_1p4_20260803_r1/sms_bytecnn_fp32.keras")
 x,_=records_to_xy(records,max_bytes=int(model.input_shape[-1])); logits,_=split_student_logits(np.asarray(model.predict(x,verbose=0)))
 selected=[r for r,index in zip(records,np.argmax(logits,axis=-1)) if r.label=="TRANSACTION" and LABEL_ORDER[int(index)]!="TRANSACTION" and coverage_subtype(r.text) in {"CARRIER","REPAYMENT"}]
 PACK.mkdir(parents=True); SAFE.mkdir(parents=True)
 rows=[{"review_key":hashlib.sha256((RUN+r.id).encode()).hexdigest()[:16],"id":r.id,"text":r.text} for r in selected]
 for name,payload in (("pass_a",rows),("pass_b",list(reversed(rows)))): (PACK/f"{name}_blind.jsonl").write_text("".join(json.dumps(row,ensure_ascii=False)+"\n" for row in payload),encoding="utf-8")
 manifest={"run_id":RUN,"status":"PENDING_EXTERNAL_APPROVAL","claim_allowed":False,"human_verified":False,"formal_acceptance_allowed":False,"locked_test_read":False,"candidate_count":len(rows),"category_counts":{"CARRIER":sum(coverage_subtype(r.text)=="CARRIER" for r in selected),"REPAYMENT":sum(coverage_subtype(r.text)=="REPAYMENT" for r in selected)},"pass_a_sha256":sha(PACK/"pass_a_blind.jsonl"),"pass_b_sha256":sha(PACK/"pass_b_blind.jsonl"),"blind_fields":["review_key","id","text"],"excluded_fields":["prior_label","model_prediction","confidence","test","pass_a","pass_b"]}
 (SAFE/"preparation_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps(manifest,ensure_ascii=False)); return 0
if __name__=="__main__": raise SystemExit(main())
