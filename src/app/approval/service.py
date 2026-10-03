"""Backend approval state machine with an in-memory store for the prototype."""

from datetime import datetime, timezone
from threading import Lock
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.models import Finding, RemediationPlan, ValidationResult
from app.audit import AuditTrail


ApprovalStatus = Literal["pending", "approved", "rejected"]


class ApprovalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: str = Field(min_length=1)
    plan: RemediationPlan
    finding: Finding
    validation: ValidationResult
    requested_by: str = Field(min_length=1)
    status: ApprovalStatus
    decided_by: str | None = None
    decision_reason: str | None = None
    requested_at: datetime
    decided_at: datetime | None = None


class ApprovalService:
    """Create and decide approval requests without executing device commands."""

    def __init__(self, audit_trail: AuditTrail | None = None) -> None:
        self._records: dict[str, ApprovalRecord] = {}
        self._lock = Lock()
        self.audit_trail = audit_trail

    def request(
        self,
        plan: RemediationPlan,
        finding: Finding,
        validation: ValidationResult,
        requested_by: str,
    ) -> ApprovalRecord:
        if not validation.valid:
            raise ValueError("Only a valid remediation plan can request approval")
        if plan.finding_id != finding.finding_id:
            raise ValueError("Plan finding_id does not match the supplied finding")

        record = ApprovalRecord(
            approval_id=f"approval-{uuid4().hex}",
            plan=plan,
            finding=finding,
            validation=validation,
            requested_by=requested_by,
            status="pending",
            requested_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._records[record.approval_id] = record
        if self.audit_trail:
            self.audit_trail.append(
                "approval.requested",
                {
                    "approval_id": record.approval_id,
                    "finding_id": finding.finding_id,
                    "requested_by": requested_by,
                },
            )
        return record

    def get(self, approval_id: str) -> ApprovalRecord:
        try:
            return self._records[approval_id]
        except KeyError as error:
            raise KeyError(f"Unknown approval request: {approval_id}") from error

    def list(self) -> list[ApprovalRecord]:
        return list(self._records.values())

    def decide(
        self,
        approval_id: str,
        status: Literal["approved", "rejected"],
        decided_by: str,
        reason: str | None = None,
    ) -> ApprovalRecord:
        with self._lock:
            record = self.get(approval_id)
            if record.status != "pending":
                raise ValueError(f"Approval request is already {record.status}")

            updated_record = record.model_copy(
                update={
                    "status": status,
                    "decided_by": decided_by,
                    "decision_reason": reason,
                    "decided_at": datetime.now(timezone.utc),
                }
            )
            self._records[approval_id] = updated_record
            if self.audit_trail:
                self.audit_trail.append(
                    "approval.decided",
                    {
                        "approval_id": approval_id,
                        "status": status,
                        "decided_by": decided_by,
                        "reason": reason,
                    },
                )
            return updated_record