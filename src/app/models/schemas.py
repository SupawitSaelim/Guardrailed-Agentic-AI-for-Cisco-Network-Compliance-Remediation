"""Pydantic contracts for audit, planning, validation, and execution."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Severity = Literal["low", "medium", "high", "critical"]
EnforcementClass = Literal["remediation", "audit_only"]


class StrictModel(BaseModel):
    """Reject unknown fields so external and LLM data fail closed."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ComplianceRule(StrictModel):
    rule_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = Field(min_length=1)
    platform: Literal["cisco_ios", "cisco_ios_xe"]
    expected_state: str = Field(min_length=1)
    allowed_scope: list[str] = Field(min_length=1)
    ground_truth_commands: list[str] = Field(min_length=1)
    blocked_commands: list[str] = Field(default_factory=list)
    severity: Severity
    enforcement: EnforcementClass = "remediation"


class Finding(StrictModel):
    finding_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    severity: Severity
    expected: str = Field(min_length=1)
    actual: list[str]
    evidence: list[str]
    allowed_scope: list[str] = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    enforcement: EnforcementClass = "remediation"


class Command(StrictModel):
    sequence: int = Field(ge=1)
    command: str = Field(min_length=1)
    scope: str = Field(min_length=1)


class ModelMetadata(StrictModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)


class RemediationPlan(StrictModel):
    plan_id: str = Field(min_length=1)
    finding_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    commands: list[Command] = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)
    requires_approval: Literal[True] = True
    model_metadata: ModelMetadata


class ValidationResult(StrictModel):
    valid: bool
    schema_errors: list[str] = Field(default_factory=list)
    blocked_commands: list[str] = Field(default_factory=list)
    out_of_scope_commands: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AuditResult(StrictModel):
    device_id: str = Field(min_length=1)
    compliant: bool
    findings: list[Finding] = Field(default_factory=list)
    rule_version: str = Field(min_length=1)
    evaluated_rule_ids: list[str] = Field(default_factory=list)


class ReauditResult(StrictModel):
    device_id: str = Field(min_length=1)
    remediation_succeeded: bool
    post_compliant: bool
    unresolved_findings: list[Finding] = Field(default_factory=list)
    regression_findings: list[Finding] = Field(default_factory=list)


class ExecutionResult(StrictModel):
    execution_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    approved_by: str = Field(min_length=1)
    commands: list[str] = Field(min_length=1)
    success: bool
    precheck_hash: str = Field(min_length=1)
    postcheck_hash: str = Field(min_length=1)
    started_at: datetime
    finished_at: datetime