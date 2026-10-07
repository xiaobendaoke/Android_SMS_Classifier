"""Ensure Recall v7 defaults to validation-only and keeps test unreachable."""
from __future__ import annotations

from typing import List

import scripts.run_recall_v3 as pipeline


def test_validation_only_does_not_call_test_evaluation(monkeypatch):
    calls: List[tuple] = []

    def fake_run(script: str, *args: str) -> None:
        calls.append((script, args))

    monkeypatch.setattr(pipeline, "audit_v2_startup", lambda: [])
    monkeypatch.setattr(pipeline, "run", fake_run)
    code = pipeline.main(
        [
            "--skip-teacher",
            "--run-name",
            "recall_v7",
            "--seed",
            "42",
        ]
    )
    assert code == 0
    scripts = [item[0] for item in calls]
    assert "distill_student.py" in scripts
    assert "evaluate.py" in scripts
    assert "quantize_int8.py" not in scripts
    assert "export_android_assets.py" not in scripts
    evaluate_calls = [args for script, args in calls if script == "evaluate.py"]
    assert len(evaluate_calls) == 1
    assert any("processed_v2" in part for part in evaluate_calls[0])
    assert any("validation.jsonl" in part for part in evaluate_calls[0])
    assert not any("test.jsonl" in part for part in evaluate_calls[0])


def test_without_unlock_locked_test_path_unreachable(monkeypatch):
    reached = {"locked": False}

    def fake_run(script: str, *args: str) -> None:
        return None

    def fake_locked(*_args, **_kwargs):
        reached["locked"] = True

    monkeypatch.setattr(pipeline, "audit_v2_startup", lambda: [])
    monkeypatch.setattr(pipeline, "run", fake_run)
    monkeypatch.setattr(pipeline, "run_locked_test_path", fake_locked)
    code = pipeline.main(["--skip-teacher", "--run-name", "recall_v7"])
    assert code == 0
    assert reached["locked"] is False


def test_unlock_denied_when_audits_fail(monkeypatch):
    monkeypatch.setattr(pipeline, "audit_v2_startup", lambda: [])
    monkeypatch.setattr(pipeline, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        pipeline,
        "audit_unlock_allowed",
        lambda: ["validate_labels.py FAILED"],
    )
    reached = {"locked": False}
    monkeypatch.setattr(
        pipeline,
        "run_locked_test_path",
        lambda *_args, **_kwargs: reached.__setitem__("locked", True),
    )
    code = pipeline.main(
        ["--skip-teacher", "--run-name", "recall_v7", "--unlock-locked-test"]
    )
    assert code == 5
    assert reached["locked"] is False


def test_startup_denied_when_v2_blockers_present(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "audit_v2_startup",
        lambda: ["human annotation incomplete"],
    )
    calls = []
    monkeypatch.setattr(pipeline, "run", lambda *a, **k: calls.append(a))
    code = pipeline.main(["--skip-teacher", "--run-name", "recall_v7"])
    assert code == 6
    assert calls == []
