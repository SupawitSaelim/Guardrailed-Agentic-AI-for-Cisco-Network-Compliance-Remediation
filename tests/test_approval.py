import pytest

from app.approval import ApprovalService
from app.models import Command, Finding, RemediationPlan, ValidationResult


def make_finding() -> Finding:
    return Finding(
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


def make_plan() -> RemediationPlan:
    return RemediationPlan(
        plan_id="plan-001",
        finding_id="finding-001",
        summary="Replace NTP server",
        commands=[Command(sequence=1, command="ntp server 10.10.10.10", scope="ntp")],
        model_metadata={
            "provider": "test",
            "model": "test-model",
            "prompt_version": "1.0.0",
        },
    )


def test_approval_request_can_be_approved_once() -> None:
    service = ApprovalService()
    record = service.request(
        make_plan(),
        make_finding(),
        ValidationResult(valid=True),
        "operator-01",
    )

    approved = service.decide(record.approval_id, "approved", "reviewer-01")

    assert approved.status == "approved"
    assert approved.decided_by == "reviewer-01"
    with pytest.raises(ValueError, match="already approved"):
        service.decide(record.approval_id, "rejected", "reviewer-02")


def test_invalid_plan_cannot_request_approval() -> None:
    with pytest.raises(ValueError, match="valid remediation plan"):
        ApprovalService().request(
            make_plan(),
            make_finding(),
            ValidationResult(valid=False, blocked_commands=["reload"]),
            "operator-01",
        )