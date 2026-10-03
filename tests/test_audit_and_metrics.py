import json

import pytest

from app.audit import AuditTrail
from app.evaluation import EvaluationRun, MetricsCalculator


def test_audit_trail_redacts_nested_secrets(tmp_path) -> None:
    trail = AuditTrail(tmp_path / "audit.jsonl")

    trail.append(
        "execution.completed",
        {
            "device_id": "lab-router-01",
            "credentials": {"username": "lab", "password": "do-not-store"},
            "metadata": [{"api_key": "also-do-not-store"}],
        },
    )

    events = trail.read_all()
    payload = events[0]["payload"]
    assert payload["credentials"]["password"] == "[REDACTED]"
    assert payload["metadata"][0]["api_key"] == "[REDACTED]"
    assert "do-not-store" not in json.dumps(events)


def test_metrics_calculator_summarizes_experiment_runs() -> None:
    runs = [
        EvaluationRun(
            remediation_correct=True,
            proposed_command_count=2,
            unsafe_command_count=0,
            out_of_scope=False,
            regression=False,
            latency_seconds=1.0,
            input_tokens=100,
            output_tokens=50,
            api_cost=0.01,
        ),
        EvaluationRun(
            remediation_correct=False,
            proposed_command_count=2,
            unsafe_command_count=1,
            out_of_scope=True,
            regression=True,
            latency_seconds=3.0,
            input_tokens=200,
            output_tokens=100,
            api_cost=0.02,
        ),
    ]

    summary = MetricsCalculator().summarize(runs)

    assert summary["remediation_correctness_percent"] == 50.0
    assert summary["unsafe_command_rate_percent"] == 25.0
    assert summary["regression_rate_percent"] == 50.0
    assert summary["average_latency_seconds"] == 2.0
    assert summary["total_api_cost"] == 0.03
    assert summary["hallucination_false_positive_rate_percent"] == 0.0
    assert summary["schema_failure_rate_percent"] == 0.0
    assert summary["guardrail_blocker_efficiency_percent"] == 0.0


def test_metrics_reject_empty_runs() -> None:
    with pytest.raises(ValueError, match="At least one evaluation run"):
        MetricsCalculator().summarize([])