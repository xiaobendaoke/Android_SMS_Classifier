HARASS / Indonesian gap re-label packs
=====================================

Files
-----
- harass_relabel_candidates.csv  (800 rows)
- id_gap_fill_candidates.csv     (1000 rows)

How to annotate
---------------
1. Only fill columns: label, annotator, notes (optional).
2. Legal labels: TRANSACTION | AD | HARASS | FRAUD | NEEDS_REVIEW
3. HARASS = 扰民但不靠骗转账（催收/灰产招揽/成人/硬推销贷款等）
4. If unsure → NEEDS_REVIEW (do not force).
5. Do NOT peek at another annotator's sheet if dual-labeling.

Suggested distributions (hints only)
------------------------------------
harass pack prior/suggested mix: {'NEEDS_REVIEW->HARASS': 41, 'AD->HARASS': 38, 'NEEDS_REVIEW->NEEDS_REVIEW': 721}
id pack suggested_label mix: {'HARASS': 9, 'TRANSACTION': 26, 'FRAUD': 5, 'AD': 5, 'NEEDS_REVIEW': 955}

After labeling
--------------
Merge filled labels back into the corresponding *_all_suggested.csv
(or ask the agent to run a merge helper), then:

  PYTHONPATH=training python training/scripts/convert_annotation_csv_to_jsonl.py
  make prepare-annotation-bootstrap

These packs are engineering refill — NOT the frozen dual-gold set.
