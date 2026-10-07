# Stage 0 Baseline Report: stage0_baseline_20260802_r2

Status: BASELINE_COMPLETE_WITH_PHASE_1_BLOCKER

This is a local, validation-only baseline from the isolated WSL worktree
`/home/colab/projects/Android_SMS_Classifier_stage0_baseline_20260802_r2`.
It does not read model metrics from the locked test split and cannot support a
transaction-recall claim.

## Reproducibility and audits

- 74 Python tests passed.
- Label validation passed for 13,953 records.
- Source audit, split-leakage audit, no-network check, sensitive-log check,
  and engineering release audit passed.
- Split leakage: PASS; 11,158 train, 1,398 validation, and 1,397 test rows.
- The RTX 4070 was used for the validation-only Keras pipeline evaluation.
- Windows JDK 17, Android SDK, adb, and Gradle verification remain unavailable
  in the current host session; Android build checks are therefore not claimed.

## Chinese validation-only baseline

The current target language is Chinese. The evaluator still reports its formal
acceptance scope as all languages, so the following Chinese values are a
per-language baseline slice, not a formal acceptance result:

| Metric | Result | Gate | Status |
| --- | ---: | ---: | --- |
| TRANSACTION Recall | 0.9155 | 0.9850 | fail |
| TRANSACTION Precision | 0.8876 | 0.9200 | fail |
| Macro-F1 | 0.8514 | 0.8600 | fail |
| HARASS F1 | 0.7577 | 0.8000 | fail |
| FRAUD Recall | 0.8287 | 0.8000 | pass |

The all-language output also fails (TRANSACTION Recall 0.9065, Macro-F1
0.7503). No threshold-only routing change is justified by these results.

## Phase 1/2 decision

`run_recall_v4.py --skip-teacher` returned `V2_STARTUP_DENIED` because
`label_conflicts_v2` and `transaction_specialist_v2` remain
`PENDING_DUAL_HUMAN_ANNOTATION`, and the dataset manifest retains the
`human_annotation_incomplete` blocker. The locked test remained unreachable.

The next required work is the specified provisional AI A/B/C annotation and
QA workflow. Its outputs must remain `PROVISIONAL_AUTOMATED_MULTI_PASS` with
`claim_allowed=false`, `human_verified=false`, and
`formal_acceptance_allowed=false`; they may support exploratory
validation-only work but not formal or locked-test acceptance.
