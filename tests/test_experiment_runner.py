from app.audit import AuditTrail
from app.experiment import ExperimentRunner, ExperimentScenario
from app.llm import MockLLMProvider
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
    assert record.remediation_correct is True
    assert runner.summarize([record])["remediation_correctness_percent"] == 100.0
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