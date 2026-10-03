"""Fail-closed Netmiko execution for approved lab remediation plans."""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.approval.service import ApprovalRecord
from app.audit import AuditTrail
from app.collection import LabTarget
from app.models import ExecutionResult


CredentialProvider = Callable[[LabTarget], dict[str, Any]]
ConnectionFactory = Callable[..., Any]


@dataclass(frozen=True)
class ExecutionReport:
    result: ExecutionResult
    post_configuration: str


class ControlledExecutor:
    """Execute only approved commands on explicitly marked lab targets."""

    def __init__(
        self,
        credential_provider: CredentialProvider,
        connection_factory: ConnectionFactory,
        audit_trail: AuditTrail | None = None,
    ) -> None:
        self.credential_provider = credential_provider
        self.connection_factory = connection_factory
        self.audit_trail = audit_trail

    def execute(
        self,
        approval: ApprovalRecord,
        target: LabTarget,
        expected_precheck_hash: str | None = None,
    ) -> ExecutionResult:
        return self.execute_many(
            [approval],
            target,
            expected_precheck_hash=expected_precheck_hash,
        ).result

    def execute_many(
        self,
        approvals: list[ApprovalRecord],
        target: LabTarget,
        expected_precheck_hash: str | None = None,
    ) -> ExecutionReport:
        if not approvals:
            raise ValueError("At least one approved remediation plan is required")
        for approval in approvals:
            self._check_execution_boundary(approval, target)
        approvers = {approval.decided_by for approval in approvals}
        if len(approvers) != 1:
            raise PermissionError("All plans in a batch must have the same approver")

        commands = [
            item.command
            for approval in approvals
            for item in approval.plan.commands
        ]
        connection_parameters = self.credential_provider(target)
        connection = self.connection_factory(
            device_type=target.device_type,
            host=target.host,
            **connection_parameters,
        )
        started_at = datetime.now(timezone.utc)
        try:
            precheck = connection.send_command("show running-config")
            precheck_hash = configuration_hash(precheck)
            if (
                expected_precheck_hash is not None
                and precheck_hash != expected_precheck_hash
            ):
                raise RuntimeError(
                    "Pre-execution configuration changed since the audit"
                )
            connection.send_config_set(commands)
            postcheck = connection.send_command("show running-config")
        finally:
            connection.disconnect()

        finished_at = datetime.now(timezone.utc)
        result = ExecutionResult(
            execution_id=f"exec-{uuid4().hex}",
            device_id=target.device_id,
            approved_by=next(iter(approvers)) or "unknown",
            commands=commands,
            success=True,
            precheck_hash=precheck_hash,
            postcheck_hash=configuration_hash(postcheck),
            started_at=started_at,
            finished_at=finished_at,
        )
        if self.audit_trail:
            self.audit_trail.append(
                "execution.completed",
                {
                    "execution_id": result.execution_id,
                    "device_id": result.device_id,
                    "approved_by": result.approved_by,
                    "commands": result.commands,
                    "precheck_hash": result.precheck_hash,
                    "postcheck_hash": result.postcheck_hash,
                },
            )
        return ExecutionReport(result=result, post_configuration=postcheck)

    @staticmethod
    def _check_execution_boundary(approval: ApprovalRecord, target: LabTarget) -> None:
        if approval.status != "approved":
            raise PermissionError("Only approved remediation plans can be executed")
        if not approval.validation.valid:
            raise PermissionError("The approved plan must have a valid validation result")
        if target.lab_only is not True:
            raise PermissionError("Execution is restricted to lab targets")
        if approval.finding.device_id != target.device_id:
            raise PermissionError("Approval and execution target must be the same device")


def configuration_hash(configuration: str) -> str:
    digest = hashlib.sha256(configuration.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"