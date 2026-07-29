# Adversarial Robustness Report (engineering)

**Status:** Datasets prepared; formal scorecards pending model+label freeze.

## Generated slices

Under `training/data/processed/adversarial/` (after `generate_synthetic_dataset.py`):

| Slice | Description |
|-------|-------------|
| `clean.jsonl` | Clean test-like samples |
| `known_perturbation.jsonl` | Zero-width / spacing injections |
| `unseen_perturbation.jsonl` | Leetspeak-style character substitutions |

## Evaluation policy

Report clean / known / unseen separately. Do not tune thresholds on the adversarial test slices.

## Current numbers

Not claimed — re-run `evaluate.py` (or prediction export) per slice after real labeling.
