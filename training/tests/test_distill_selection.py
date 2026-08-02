"""Validation checkpoint selection tests without importing TensorFlow."""
from scripts.distill_student import checkpoint_score
from scripts.train_teacher import teacher_checkpoint_score


TARGETS = {
    "target_transaction_recall": 0.985,
    "min_transaction_precision": 0.92,
    "min_macro_f1": 0.86,
    "min_harass_f1": 0.80,
    "min_fraud_recall": 0.80,
}


def _metrics(
    txn: float,
    macro: float,
    harass: float,
    fraud: float,
    txn_precision: float = 0.95,
) -> dict:
    return {
        "macro_f1": macro,
        "per_class": {
            "TRANSACTION": {"recall": txn, "precision": txn_precision},
            "HARASS": {"f1": harass},
            "FRAUD": {"recall": fraud},
        },
    }


def test_safe_checkpoint_beats_higher_transaction_recall_with_collateral_damage():
    unsafe = _metrics(txn=0.995, macro=0.70, harass=0.60, fraud=0.55)
    safe = _metrics(txn=0.986, macro=0.87, harass=0.82, fraud=0.81)
    assert checkpoint_score(safe, TARGETS) > checkpoint_score(unsafe, TARGETS)


def test_transaction_recall_breaks_tie_between_safe_checkpoints():
    lower = _metrics(txn=0.986, macro=0.88, harass=0.82, fraud=0.82)
    higher = _metrics(txn=0.990, macro=0.87, harass=0.81, fraud=0.81)
    assert checkpoint_score(higher, TARGETS) > checkpoint_score(lower, TARGETS)


def test_low_transaction_precision_cannot_win_by_predicting_transaction_too_often():
    unsafe = _metrics(
        txn=1.0,
        macro=0.87,
        harass=0.81,
        fraud=0.81,
        txn_precision=0.70,
    )
    safe = _metrics(txn=0.986, macro=0.87, harass=0.81, fraud=0.81)
    assert checkpoint_score(safe, TARGETS) > checkpoint_score(unsafe, TARGETS)


def test_closest_joint_checkpoint_wins_when_no_checkpoint_passes_all_gates():
    epoch_one = _metrics(
        txn=0.942,
        macro=0.667,
        harass=0.404,
        fraud=0.761,
        txn_precision=0.638,
    )
    epoch_six = _metrics(
        txn=0.930,
        macro=0.812,
        harass=0.75,
        fraud=0.865,
        txn_precision=0.84,
    )
    assert checkpoint_score(epoch_six, TARGETS) > checkpoint_score(epoch_one, TARGETS)


def test_teacher_selection_also_protects_non_transaction_classes():
    unsafe = _metrics(txn=1.0, macro=0.75, harass=0.65, fraud=0.60)
    safe = _metrics(txn=0.98, macro=0.87, harass=0.81, fraud=0.81)
    assert teacher_checkpoint_score(safe, TARGETS) > teacher_checkpoint_score(
        unsafe, TARGETS
    )
