# Arbitration Package Design (No-Raw-Text Analysis)

## Status: AWAITING_USER_AUTHORIZATION

This document designs the next AI arbitration flow based on the consistency
audit (`stage2_xfyun_annotation_consistency_audit_20260806_r1/analysis.json`).
No raw SMS text, sample IDs, or AI raw outputs are included. All numbers are
aggregate counts from the audit.

## 1. Data Quality Bottleneck

The consistency audit identified the root cause of the persistent gate failure:

- AI multi-pass arbitration covers only 1109 of 12623 frozen rows (8.8%).
- 28 template groups in the 08-02 batch have internal label inconsistencies.
- The inconsistent label pairs are concentrated at HARASS boundaries:
  - FRAUD|HARASS: 9 groups
  - AD|HARASS: 7 groups
  - AD|NEEDS_REVIEW: 4 groups
  - NEEDS_REVIEW|TRANSACTION: 3 groups
  - AD|NEEDS_REVIEW|TRANSACTION: 2 groups
  - AD|FRAUD: 1 group
  - AD|TRANSACTION: 1 group
  - HARASS|NEEDS_REVIEW: 1 group

HARASS is involved in 17 of 28 inconsistent groups (60.7%). This directly
explains why HARASS F1 has never reached the 0.800 gate.

## 2. Arbitration Targets

Priority targets for new AI arbitration (ordered by impact):

1. FRAUD|HARASS boundary groups (9): These are messages where the AI labeled
   some templates in a group as FRAUD and others as HARASS. Resolving these
   will improve both HARASS F1 and FRAUD Recall.
2. AD|HARASS boundary groups (7): These are promotional messages that blur
   the line between advertising and harassment. Resolving these will improve
   HARASS F1 and AD precision.
3. TRANSACTION|AD boundary groups (3+2): These are carrier/repayment messages
   where some are labeled TRANSACTION and others AD. Resolving these will
   improve TRANSACTION Recall and AD precision.

## 3. Proposed Arbitration Flow

Transport: XFYun OpenAI SDK compatible interface (same as previous passes).
Model: xopdeepseekv4flash (same model used for 08-02 batch).

Flow (multi-pass, same structure as existing passes):
- Pass A: Independent labeling of each candidate row.
- Pass B: Independent re-labeling with shuffled context.
- Pass C: Adjudication of A/B disagreements.
- QA: Exact agreement rate, conflict count, quarantine count.
- Overlay: Apply resolved labels to a new data version (not the frozen split).
- Split membership preserved. Locked test byte-identical.

Privacy safeguards:
- No raw SMS text in any report or committed file.
- No sample IDs in any report or committed file.
- No AI raw outputs committed.
- Only aggregate counts and SHA hashes in the manifest.

## 4. Estimated Sample Count

Based on the 28 inconsistent template groups and the existing arbitration
coverage gaps:
- Estimated new arbitration candidates: 2000-4000 rows (to expand coverage
  from 8.8% to approximately 25-35% of the frozen split).
- Focus on HARASS-adjacent boundary groups and the remaining unreviewed
  TRANSACTION/AD rows.

## 5. Expected Impact

If the HARASS boundary inconsistencies are resolved through arbitration:
- HARASS F1: expected improvement from 0.7373-0.7656 to 0.78-0.82 range.
- FRAUD Recall: should remain above 0.80 (currently 0.8122).
- TRANSACTION Recall: indirect improvement from cleaner AD/TRANSACTION boundary.
- Macro F1: expected to reach 0.85-0.87 range.

These are estimates based on the error cluster analysis, not guarantees.

## 6. Authorization Requirement

Per the goal objective: "新增外发标注必须走 XFYun OpenAI SDK兼容接口，
保留无原文审计元数据，且必须获得用户明确授权。"

This document is a design only. No external annotation calls have been made.
No raw SMS data has been read or transmitted.
Status remains AWAITING_USER_AUTHORIZATION.

## 7. Post-Authorization Steps

Once authorized:
1. Prepare candidate pack (no raw text, only IDs + hashes).
2. Run multi-pass AI arbitration via XFYun OpenAI SDK.
3. Generate QA report (agreement rates, conflict counts, quarantine).
4. Apply overlay to new data version with SHA tracking.
5. Re-run training with the improved data on the best historical config
   (round 4: lr=5e-4, hard-only, both-sides hard-boundary 1.5).
6. Run independent Keras zh validation evaluation.
7. Check five gates; write decision.json.
8. If pass: generate human review package with sampling strategy and disclaimer.
9. Explicitly state: "该候选已通过自动 validation-only门禁，仍未读取 locked
   test，仍等待用户人工审核，因此不构成正式验收结论。"
