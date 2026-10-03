from app.models import Command, Finding, RemediationPlan
from app.validation import CommandScopeValidator


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


def make_plan(*commands: Command, finding_id: str = "finding-001") -> RemediationPlan:
    return RemediationPlan(
        plan_id="plan-001",
        finding_id=finding_id,
        summary="Apply the approved NTP remediation",
        commands=list(commands),
        model_metadata={
            "provider": "test",
            "model": "test-model",
            "prompt_version": "1.0.0",
        },
    )


def test_valid_plan_passes() -> None:
    plan = make_plan(
        Command(sequence=1, command="no ntp server 10.10.10.20", scope="ntp"),
        Command(sequence=2, command="ntp server 10.10.10.10", scope="ntp"),
    )

    result = CommandScopeValidator().validate(plan, make_finding())

    assert result.valid is True
    assert result.blocked_commands == []
    assert result.out_of_scope_commands == []


def test_blocked_command_fails_closed() -> None:
    plan = make_plan(Command(sequence=1, command="reload", scope="ntp"))

    result = CommandScopeValidator().validate(plan, make_finding())

    assert result.valid is False
    assert result.blocked_commands == ["reload"]


def test_out_of_scope_command_is_rejected() -> None:
    plan = make_plan(Command(sequence=1, command="no login local", scope="line vty"))

    result = CommandScopeValidator().validate(plan, make_finding())

    assert result.valid is False
    assert result.out_of_scope_commands == ["no login local"]


def test_plan_for_different_finding_is_rejected() -> None:
    plan = make_plan(
        Command(sequence=1, command="ntp server 10.10.10.10", scope="ntp"),
        finding_id="different-finding",
    )

    result = CommandScopeValidator().validate(plan, make_finding())

    assert result.valid is False
    assert result.schema_errors == ["Plan finding_id does not match the supplied finding"]


def test_audit_only_finding_cannot_be_executed() -> None:
    finding = make_finding().model_copy(update={"enforcement": "audit_only"})
    plan = make_plan(Command(sequence=1, command="ntp server 10.10.10.10", scope="ntp"))

    result = CommandScopeValidator().validate(plan, finding)

    assert result.valid is False
    assert result.schema_errors == [
        "Audit-only findings cannot produce executable plans"
    ]