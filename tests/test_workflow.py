from app.llm import MockLLMProvider
from app.collection import LabTarget, NetmikoCollector
from app.execution import ControlledExecutor
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


def test_run_target_collects_lab_config_before_auditing() -> None:
    configuration = "ntp server 10.10.10.20\n"
    result = WorkflowOrchestrator(MockLLMProvider()).run_target(
        LabTarget(
            device_id="lab-router-01",
            host="192.0.2.10",
            device_type="cisco_ios",
        ),
        [make_ntp_rule()],
        "operator-01",
        NetmikoCollector(
            credential_provider=lambda target: {},
            connection_factory=lambda **parameters: _Connection(configuration),
        ),
    )

    assert result.status == "approval_pending"
    assert result.configuration_hash is not None


def test_execute_approved_runs_batch_and_reaudits() -> None:
    orchestrator = WorkflowOrchestrator(MockLLMProvider())
    original = "ntp server 10.10.10.20\n"
    planned = orchestrator.run(
        original,
        [make_ntp_rule()],
        "lab-router-01",
        "operator-01",
    )
    approved = [
        orchestrator.approval_service.decide(
            approval.approval_id,
            "approved",
            "reviewer-01",
        )
        for approval in planned.approvals
    ]
    connection = _ExecutionConnection(
        before=original,
        after="ntp server 10.10.10.10\n",
    )
    result = orchestrator.execute_approved(
        approved,
        LabTarget(
            device_id="lab-router-01",
            host="192.0.2.10",
            device_type="cisco_ios",
        ),
        original,
        [make_ntp_rule()],
        ControlledExecutor(
            credential_provider=lambda target: {},
            connection_factory=lambda **parameters: connection,
        ),
    )

    assert result.execution.success is True
    assert result.reaudit.post_compliant is True
    assert result.reaudit.remediation_succeeded is True


class _Connection:
    def __init__(self, configuration: str) -> None:
        self.configuration = configuration

    def send_command(self, command: str) -> str:
        return self.configuration

    def disconnect(self) -> None:
        pass


class _ExecutionConnection:
    def __init__(self, before: str, after: str) -> None:
        self.before = before
        self.after = after
        self.config_sets: list[list[str]] = []
        self.reads = 0

    def send_command(self, command: str) -> str:
        self.reads += 1
        return self.before if self.reads == 1 else self.after

    def send_config_set(self, commands: list[str]) -> str:
        self.config_sets.append(commands)
        return "ok"

    def disconnect(self) -> None:
        pass