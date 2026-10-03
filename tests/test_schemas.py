from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models import Command, ExecutionResult, Finding, RemediationPlan


def test_finding_accepts_required_compliance_data() -> None:
    finding = Finding(
        finding_id="finding-001",
        device_id="lab-router-01",
        rule_id="ntp-approved-server",
        severity="medium",
        expected="ntp server 10.10.10.10",
        actual=["ntp server 10.10.10.20"],
        evidence=["ntp server 10.10.10.20"],
        allowed_scope=["ntp"],
        rule_version="1.0.0",
    )

    assert finding.allowed_scope == ["ntp"]


def test_remediation_plan_requires_approval() -> None:
    with pytest.raises(ValidationError):
        RemediationPlan(
            plan_id="plan-001",
            finding_id="finding-001",
            summary="Replace NTP server",
            commands=[Command(sequence=1, command="ntp server 10.10.10.10", scope="ntp")],
            requires_approval=False,
            model_metadata={
                "provider": "test",
                "model": "test-model",
                "prompt_version": "1.0.0",
            },
        )


def test_schema_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Finding(
            finding_id="finding-001",
            device_id="lab-router-01",
            rule_id="ntp-approved-server",
            severity="medium",
            expected="ntp server 10.10.10.10",
            actual=[],
            evidence=[],
            allowed_scope=["ntp"],
            rule_version="1.0.0",
            unexpected="reject me",
        )


def test_execution_result_parses_timestamps() -> None:
    result = ExecutionResult(
        execution_id="exec-001",
        device_id="lab-router-01",
        approved_by="operator-01",
        commands=["ntp server 10.10.10.10"],
        success=True,
        precheck_hash="sha256:before",
        postcheck_hash="sha256:after",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )

    assert result.success is True