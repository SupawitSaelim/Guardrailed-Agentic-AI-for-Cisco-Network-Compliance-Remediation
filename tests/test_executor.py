import pytest

from app.approval import ApprovalService
from app.collection import LabTarget
from app.execution import ControlledExecutor, configuration_hash
from app.models import Command, Finding, RemediationPlan, ValidationResult


class FakeConnection:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.config_sets: list[list[str]] = []
        self.disconnected = False

    def send_command(self, command: str) -> str:
        self.commands.append(command)
        if len(self.commands) == 1:
            return "ntp server 10.10.10.20\n"
        return "ntp server 10.10.10.10\n"

    def send_config_set(self, commands: list[str]) -> str:
        self.config_sets.append(commands)
        return "ok"

    def disconnect(self) -> None:
        self.disconnected = True


def make_approval(status: str = "approved"):
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
    plan = RemediationPlan(
        plan_id="plan-001",
        finding_id=finding.finding_id,
        summary="Replace NTP server",
        commands=[Command(sequence=1, command="ntp server 10.10.10.10", scope="ntp")],
        model_metadata={
            "provider": "test",
            "model": "test-model",
            "prompt_version": "1.0.0",
        },
    )
    service = ApprovalService()
    approval = service.request(plan, finding, ValidationResult(valid=True), "operator-01")
    if status == "approved":
        return service.decide(approval.approval_id, "approved", "reviewer-01")
    return approval


def test_executor_runs_only_approved_commands_and_hashes_snapshots() -> None:
    fake_connection = FakeConnection()
    executor = ControlledExecutor(
        credential_provider=lambda target: {
            "username": "lab-write",
            "password": "not-persisted",
        },
        connection_factory=lambda **parameters: fake_connection,
    )

    result = executor.execute(
        make_approval(),
        LabTarget(device_id="lab-router-01", host="192.0.2.10", device_type="cisco_ios"),
    )

    assert result.success is True
    assert result.approved_by == "reviewer-01"
    assert result.precheck_hash != result.postcheck_hash
    assert fake_connection.config_sets == [["ntp server 10.10.10.10"]]
    assert fake_connection.disconnected is True


def test_executor_rejects_pending_approval() -> None:
    executor = ControlledExecutor(
        credential_provider=lambda target: {},
        connection_factory=lambda **parameters: FakeConnection(),
    )

    with pytest.raises(PermissionError, match="approved remediation"):
        executor.execute(
            make_approval(status="pending"),
            LabTarget(device_id="lab-router-01", host="192.0.2.10", device_type="cisco_ios"),
        )


def test_executor_rejects_configuration_drift_before_writing() -> None:
    fake_connection = FakeConnection()
    executor = ControlledExecutor(
        credential_provider=lambda target: {},
        connection_factory=lambda **parameters: fake_connection,
    )

    with pytest.raises(RuntimeError, match="configuration changed"):
        executor.execute(
            make_approval(),
            LabTarget(device_id="lab-router-01", host="192.0.2.10", device_type="cisco_ios"),
            expected_precheck_hash=configuration_hash("different configuration\n"),
        )

    assert fake_connection.config_sets == []


def test_executor_rejects_approval_for_another_device() -> None:
    executor = ControlledExecutor(
        credential_provider=lambda target: {},
        connection_factory=lambda **parameters: FakeConnection(),
    )

    with pytest.raises(PermissionError, match="same device"):
        executor.execute(
            make_approval(),
            LabTarget(device_id="lab-router-02", host="192.0.2.11", device_type="cisco_ios"),
        )


def test_executor_batches_approved_plans_with_one_precheck() -> None:
    fake_connection = FakeConnection()
    first = make_approval()
    second = make_approval()
    executor = ControlledExecutor(
        credential_provider=lambda target: {},
        connection_factory=lambda **parameters: fake_connection,
    )

    report = executor.execute_many(
        [first, second],
        LabTarget(device_id="lab-router-01", host="192.0.2.10", device_type="cisco_ios"),
        expected_precheck_hash=configuration_hash("ntp server 10.10.10.20\n"),
    )

    assert report.result.success is True
    assert report.post_configuration == "ntp server 10.10.10.10\n"
    assert fake_connection.commands == ["show running-config", "show running-config"]
    assert fake_connection.config_sets == [
        ["ntp server 10.10.10.10", "ntp server 10.10.10.10"]
    ]