"""Connect deterministic audit, planning, validation, and human approval."""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.approval import ApprovalService
from app.approval.service import ApprovalRecord
from app.audit import AuditTrail
from app.collection import LabTarget, NetmikoCollector
from app.compliance import ComplianceEngine
from app.execution import ControlledExecutor, configuration_hash
from app.models import (
    ComplianceRule,
    Finding,
    RemediationPlan,
    ValidationResult,
    ExecutionResult,
    ReauditResult,
)
from app.reaudit import ReauditService
from app.validation import CommandScopeValidator


class Planner(Protocol):
    def generate_plan(self, finding: Finding, rule: ComplianceRule) -> RemediationPlan:
        ...


WorkflowStatus = Literal["compliant", "approval_pending", "validation_failed"]


class WorkflowResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: WorkflowStatus
    configuration_hash: str | None = None
    findings: list[Finding] = Field(default_factory=list)
    plans: list[RemediationPlan] = Field(default_factory=list)
    validations: list[ValidationResult] = Field(default_factory=list)
    approvals: list[ApprovalRecord] = Field(default_factory=list)


class LiveWorkflowResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution: ExecutionResult
    reaudit: ReauditResult


class WorkflowOrchestrator:
    """Run a remediation proposal through every pre-execution control."""

    def __init__(
        self,
        planner: Planner,
        compliance_engine: ComplianceEngine | None = None,
        validator: CommandScopeValidator | None = None,
        approval_service: ApprovalService | None = None,
        audit_trail: AuditTrail | None = None,
    ) -> None:
        self.planner = planner
        self.compliance_engine = compliance_engine or ComplianceEngine()
        self.validator = validator or CommandScopeValidator()
        self.approval_service = approval_service or ApprovalService(audit_trail=audit_trail)
        self.audit_trail = audit_trail

    def run(
        self,
        configuration: str,
        rules: list[ComplianceRule],
        device_id: str,
        requested_by: str,
    ) -> WorkflowResult:
        source_hash = configuration_hash(configuration)
        self._record("workflow.started", {"device_id": device_id, "requested_by": requested_by})
        audit_result = self.compliance_engine.audit(configuration, rules, device_id)
        self._record(
            "audit.completed",
            {
                "device_id": device_id,
                "compliant": audit_result.compliant,
                "finding_count": len(audit_result.findings),
            },
        )
        if audit_result.compliant:
            self._record("workflow.completed", {"status": "compliant"})
            return WorkflowResult(status="compliant", configuration_hash=source_hash)

        rules_by_id = {rule.rule_id: rule for rule in rules}
        plans: list[RemediationPlan] = []
        validations: list[ValidationResult] = []
        approvals: list[ApprovalRecord] = []

        for finding in audit_result.findings:
            self._record(
                "finding.created",
                {"finding_id": finding.finding_id, "rule_id": finding.rule_id},
            )
            rule = rules_by_id[finding.rule_id]
            plan = self.planner.generate_plan(finding, rule)
            self._record(
                "plan.generated",
                {"plan_id": plan.plan_id, "finding_id": plan.finding_id},
            )
            validation = self.validator.validate(plan, finding)
            self._record(
                "validation.completed",
                {"plan_id": plan.plan_id, "valid": validation.valid},
            )
            plans.append(plan)
            validations.append(validation)

            if validation.valid:
                approvals.append(
                    self.approval_service.request(
                        plan,
                        finding,
                        validation,
                        requested_by,
                    )
                )

        status: WorkflowStatus = (
            "approval_pending"
            if all(validation.valid for validation in validations)
            else "validation_failed"
        )
        result = WorkflowResult(
            status=status,
            configuration_hash=source_hash,
            findings=audit_result.findings,
            plans=plans,
            validations=validations,
            approvals=approvals,
        )
        self._record(
            "workflow.completed",
            {"status": result.status, "approval_count": len(result.approvals)},
        )
        return result

    def run_target(
        self,
        target: LabTarget,
        rules: list[ComplianceRule],
        requested_by: str,
        collector: NetmikoCollector,
    ) -> WorkflowResult:
        """Collect a lab target and run the same workflow against its snapshot."""
        configuration = collector.collect(target)
        return self.run(configuration, rules, target.device_id, requested_by)

    def execute_approved(
        self,
        approvals: list[ApprovalRecord],
        target: LabTarget,
        original_configuration: str,
        rules: list[ComplianceRule],
        executor: ControlledExecutor,
    ) -> LiveWorkflowResult:
        """Execute one approved scenario and immediately re-audit its result."""
        if not rules:
            raise ValueError("At least one compliance rule is required")
        if any(approval.finding.rule_version != rules[0].version for approval in approvals):
            raise ValueError("Approval rule versions must match the execution rules")
        before = self.compliance_engine.audit(
            original_configuration,
            rules,
            target.device_id,
        )
        report = executor.execute_many(
            approvals,
            target,
            expected_precheck_hash=configuration_hash(original_configuration),
        )
        after = self.compliance_engine.audit(
            report.post_configuration,
            rules,
            target.device_id,
        )
        reaudit = ReauditService(audit_trail=self.audit_trail).compare(before, after)
        return LiveWorkflowResult(execution=report.result, reaudit=reaudit)

    def _record(self, event_type: str, payload: dict[str, object]) -> None:
        if self.audit_trail:
            self.audit_trail.append(event_type, payload)