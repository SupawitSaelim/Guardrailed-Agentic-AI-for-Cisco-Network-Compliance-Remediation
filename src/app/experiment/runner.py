"""Reproducible, safety-preserving experiment runner."""

from time import perf_counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.audit import AuditTrail
from app.evaluation import EvaluationRun, MetricsCalculator
from app.models import ComplianceRule
from app.reaudit import ReauditService
from app.workflow import WorkflowOrchestrator


ExperimentGroup = Literal["A", "B", "C", "D"]


class ExperimentScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    configuration: str
    rules: list[ComplianceRule] = Field(min_length=1)
    group: ExperimentGroup
    context_variant: str = Field(default="full", min_length=1)
    requested_by: str = Field(min_length=1)
    post_configuration: str | None = None


class ExperimentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    group: ExperimentGroup
    context_variant: str
    workflow_status: str
    finding_count: int = Field(ge=0)
    plan_count: int = Field(ge=0)
    proposed_command_count: int = Field(ge=0)
    valid_plan_count: int = Field(ge=0)
    unsafe_command_count: int = Field(ge=0)
    out_of_scope_change: bool
    remediation_correct: bool
    regression: bool
    latency_seconds: float = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    api_cost: float = Field(ge=0)
    execution_completed: bool
    post_compliant: bool | None = None
    approval_count: int = Field(ge=0)
    hallucination_count: int = Field(ge=0)
    schema_failure: bool
    blocked_hallucination_count: int = Field(ge=0)

    def as_evaluation_run(self) -> EvaluationRun:
        return EvaluationRun(
            remediation_correct=self.remediation_correct,
            proposed_command_count=self.proposed_command_count,
            unsafe_command_count=self.unsafe_command_count,
            out_of_scope=self.out_of_scope_change,
            regression=self.regression,
            latency_seconds=self.latency_seconds,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            api_cost=self.api_cost,
            hallucination_count=self.hallucination_count,
            schema_failure=self.schema_failure,
            blocked_hallucination_count=self.blocked_hallucination_count,
        )


class ExperimentRunner:
    """Run proposal-stage experiments without bypassing production safety gates."""

    def __init__(self, orchestrator: WorkflowOrchestrator, audit_trail: AuditTrail | None = None):
        self.orchestrator = orchestrator
        self.audit_trail = audit_trail

    def run(self, scenario: ExperimentScenario) -> ExperimentRecord:
        started = perf_counter()
        result = self.orchestrator.run(
            scenario.configuration,
            scenario.rules,
            scenario.device_id,
            scenario.requested_by,
        )
        elapsed = perf_counter() - started
        valid_plan_count = sum(validation.valid for validation in result.validations)
        unsafe_command_count = sum(
            len(validation.blocked_commands) for validation in result.validations
        )
        out_of_scope_change = any(
            validation.out_of_scope_commands for validation in result.validations
        )
        rules_by_id = {rule.rule_id: rule for rule in scenario.rules}
        findings_by_id = {finding.finding_id: finding for finding in result.findings}
        hallucination_count = 0
        blocked_hallucination_count = 0
        for plan, validation in zip(result.plans, result.validations):
            finding = findings_by_id[plan.finding_id]
            rule = rules_by_id[finding.rule_id]
            ground_truth = set(rule.ground_truth_commands)
            hallucinated = [
                command.command
                for command in plan.commands
                if command.command not in ground_truth
            ]
            hallucination_count += len(hallucinated)
            blocked_commands = set(validation.blocked_commands)
            blocked_commands.update(validation.out_of_scope_commands)
            blocked_hallucination_count += len(set(hallucinated).intersection(blocked_commands))

        post_compliant: bool | None = None
        remediation_correct = False
        regression = False
        execution_completed = False
        if scenario.post_configuration is not None and result.findings:
            before = self.orchestrator.compliance_engine.audit(
                scenario.configuration,
                scenario.rules,
                scenario.device_id,
            )
            after = self.orchestrator.compliance_engine.audit(
                scenario.post_configuration,
                scenario.rules,
                scenario.device_id,
            )
            reaudit = ReauditService(audit_trail=self.audit_trail).compare(before, after)
            post_compliant = reaudit.post_compliant
            remediation_correct = reaudit.remediation_succeeded
            regression = bool(reaudit.regression_findings)
            execution_completed = True
        record = ExperimentRecord(
            scenario_id=scenario.scenario_id,
            group=scenario.group,
            context_variant=scenario.context_variant,
            workflow_status=result.status,
            finding_count=len(result.findings),
            plan_count=len(result.plans),
            proposed_command_count=sum(len(plan.commands) for plan in result.plans),
            valid_plan_count=valid_plan_count,
            unsafe_command_count=unsafe_command_count,
            out_of_scope_change=out_of_scope_change,
            remediation_correct=remediation_correct,
            regression=regression,
            execution_completed=execution_completed,
            post_compliant=post_compliant,
            approval_count=len(result.approvals),
            hallucination_count=hallucination_count,
            schema_failure=any(
                validation.schema_errors for validation in result.validations
            ),
            blocked_hallucination_count=blocked_hallucination_count,
            latency_seconds=elapsed,
            input_tokens=0,
            output_tokens=0,
            api_cost=0.0,
        )
        if self.audit_trail:
            self.audit_trail.append(
                "experiment.completed",
                record.model_dump(mode="json"),
            )
        return record

    def summarize(self, records: list[ExperimentRecord]) -> dict[str, float]:
        return MetricsCalculator().summarize([record.as_evaluation_run() for record in records])