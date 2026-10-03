from app.audit import AuditTrail
from app.experiment import ExperimentRunner, ExperimentScenario
from app.llm import HallucinatingMockLLMProvider, MockLLMProvider
from app.models import ComplianceRule
from app.workflow import WorkflowOrchestrator


def make_rule() -> ComplianceRule:
    return ComplianceRule(
        rule_id="ntp-approved-server",
        version="1.0.0",
        description="NTP server must be approved",
        platform="cisco_ios",
        expected_state="ntp server 10.10.10.10",
        allowed_scope=["ntp"],
        ground_truth_commands=["ntp server 10.10.10.10"],
        severity="medium",
    )


def test_runner_records_scenario_and_metrics(tmp_path) -> None:
    audit_trail = AuditTrail(tmp_path / "audit.jsonl")
    runner = ExperimentRunner(
        WorkflowOrchestrator(MockLLMProvider(), audit_trail=audit_trail),
        audit_trail=audit_trail,
    )
    scenario = ExperimentScenario(
        scenario_id="single-fault-001",
        device_id="lab-router-01",
        configuration="ntp server 10.10.10.20\n",
        rules=[make_rule()],
        group="D",
        requested_by="researcher-01",
    )

    record = runner.run(scenario)

    assert record.workflow_status == "approval_pending"
    assert record.valid_plan_count == 1
    assert record.remediation_correct is False
    assert record.execution_completed is False
    assert record.post_compliant is None
    assert runner.summarize([record])["remediation_correctness_percent"] == 0.0
    event_types = [event["event_type"] for event in audit_trail.read_all()]
    assert event_types == [
        "workflow.started",
        "audit.completed",
        "finding.created",
        "plan.generated",
        "validation.completed",
        "approval.requested",
        "workflow.completed",
        "experiment.completed",
    ]


def test_runner_marks_scenario_correct_only_after_post_reaudit(tmp_path) -> None:
    audit_trail = AuditTrail(tmp_path / "audit.jsonl")
    runner = ExperimentRunner(
        WorkflowOrchestrator(MockLLMProvider(), audit_trail=audit_trail),
        audit_trail=audit_trail,
    )
    scenario = ExperimentScenario(
        scenario_id="single-fault-002",
        device_id="lab-router-01",
        configuration="ntp server 10.10.10.20\n",
        post_configuration="ntp server 10.10.10.10\n",
        rules=[make_rule()],
        group="D",
        requested_by="researcher-01",
    )

    record = runner.run(scenario)

    assert record.execution_completed is True
    assert record.post_compliant is True
    assert record.remediation_correct is True
    assert record.approval_count == 1


def test_runner_aggregates_multiple_findings_as_one_scenario(tmp_path) -> None:
    audit_trail = AuditTrail(tmp_path / "audit.jsonl")
    runner = ExperimentRunner(
        WorkflowOrchestrator(MockLLMProvider(), audit_trail=audit_trail),
        audit_trail=audit_trail,
    )
    http_rule = ComplianceRule(
        rule_id="http-disabled",
        version="1.0.0",
        description="HTTP server must be disabled",
        platform="cisco_ios",
        expected_state="no ip http server",
        allowed_scope=["ip http"],
        ground_truth_commands=["no ip http server"],
        severity="medium",
    )
    scenario = ExperimentScenario(
        scenario_id="concurrent-fault-001",
        device_id="lab-router-01",
        configuration="ntp server 10.10.10.20\nip http server\n",
        post_configuration="ntp server 10.10.10.10\n",
        rules=[make_rule(), http_rule],
        group="D",
        requested_by="researcher-01",
    )

    record = runner.run(scenario)

    assert record.finding_count == 2
    assert record.plan_count == 2
    assert record.approval_count == 2
    assert record.remediation_correct is True


def test_runner_records_hallucinated_command_blocked_by_scope() -> None:
    runner = ExperimentRunner(
        WorkflowOrchestrator(HallucinatingMockLLMProvider()),
    )
    scenario = ExperimentScenario(
        scenario_id="context-deficit-001",
        device_id="lab-router-01",
        configuration="ntp server 10.10.10.20\n",
        rules=[make_rule()],
        group="C",
        context_variant="missing-interface-context",
        requested_by="researcher-01",
    )

    record = runner.run(scenario)

    assert record.hallucination_count == 1
    assert record.blocked_hallucination_count == 1
    assert record.valid_plan_count == 0
    assert record.approval_count == 0