from app.llm import MockLLMProvider
from app.models import ComplianceRule
from app.workflow import WorkflowOrchestrator


def make_ntp_rule() -> ComplianceRule:
    return ComplianceRule(
        rule_id="ntp-approved-server",
        version="1.0.0",
        description="NTP server must be approved",
        platform="cisco_ios",
        expected_state="ntp server 10.10.10.10",
        allowed_scope=["ntp"],
        ground_truth_commands=[
            "no ntp server 10.10.10.20",
            "ntp server 10.10.10.10",
        ],
        severity="medium",
    )


def test_non_compliant_device_reaches_pending_approval() -> None:
    result = WorkflowOrchestrator(MockLLMProvider()).run(
        "ntp server 10.10.10.20\n",
        [make_ntp_rule()],
        "lab-router-01",
        "operator-01",
    )

    assert result.status == "approval_pending"
    assert len(result.findings) == 1
    assert len(result.approvals) == 1
    assert result.approvals[0].status == "pending"


def test_compliant_device_does_not_create_approval() -> None:
    result = WorkflowOrchestrator(MockLLMProvider()).run(
        "ntp server 10.10.10.10\n",
        [make_ntp_rule()],
        "lab-router-01",
        "operator-01",
    )

    assert result.status == "compliant"
    assert result.findings == []
    assert result.approvals == []