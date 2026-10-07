# Stage 0 Baseline Report: stage0_baseline_20260802

Status: INVALID_ENVIRONMENT_RUN

This run was executed from `/home/colab/projects/Android_SMS_Classifier` and
must not be used as a model baseline. That WSL worktree was at commit
`58c3177662e9b0eccf377d55fcfa9c9364901c34` on `main`, while the Windows
workspace was at `4337d2c086329b174e9adf3b3bfba64361157943`. The WSL worktree
also had pre-existing, extensive uncommitted changes, so it was not modified.

Executed evidence:

- `pytest training/tests -q`: PASS, 35 passed.
- No-network permission check: PASS, 3 manifests contain no `INTERNET`.
- Sensitive-log heuristic: PASS.
- Release audit: PASS with framework-only status; no recall claim permitted.
- `validate_labels`, split-leakage, validation pipeline, and v4 startup gate:
  NOT EXECUTED against the intended code because their CLI/files were absent
  or incompatible in the stale WSL worktree (exit code 2).

No locked-test model metric was read. No SMS text, raw data, or model artifact
was copied into this report. `environment.txt`, command logs, and
`output_sha256s.txt` contain the reproducibility evidence and hashes.

Next action: create a new, isolated WSL worktree from the current Windows
commit, copy only local ignored data/model inputs required for a validation-only
baseline, and rerun under a new run ID.
