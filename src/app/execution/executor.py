"""Fail-closed Netmiko execution for approved lab remediation plans."""

import hashlib
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.approval.service import ApprovalRecord
from app.audit import AuditTrail
from app.collection import LabTarget
from app.models import ExecutionResult


CredentialProvider = Callable[[LabTarget], dict[str, Any]]
ConnectionFactory = Callable[..., Any]


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

    def execute(self, approval: ApprovalRecord, target: LabTarget) -> ExecutionResult:
        self._check_execution_boundary(approval, target)

        commands = [item.command for item in approval.plan.commands]
        connection_parameters = self.credential_provider(target)
        connection = self.connection_factory(
            device_type=target.device_type,
            host=target.host,
            **connection_parameters,
        )
        started_at = datetime.now(timezone.utc)
        try:
            precheck = connection.send_command("show running-config")
            connection.send_config_set(commands)
            postcheck = connection.send_command("show running-config")
        finally:
            connection.disconnect()

        finished_at = datetime.now(timezone.utc)
        result = ExecutionResult(
            execution_id=f"exec-{uuid4().hex}",
            device_id=target.device_id,
            approved_by=approval.decided_by or "unknown",
            commands=commands,
            success=True,
            precheck_hash=_hash_configuration(precheck),
            postcheck_hash=_hash_configuration(postcheck),
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
        return result

    @staticmethod
    def _check_execution_boundary(approval: ApprovalRecord, target: LabTarget) -> None:
        if approval.status != "approved":
            raise PermissionError("Only approved remediation plans can be executed")
        if not approval.validation.valid:
            raise PermissionError("The approved plan must have a valid validation result")
        if target.lab_only is not True:
            raise PermissionError("Execution is restricted to lab targets")


def _hash_configuration(configuration: str) -> str:
    digest = hashlib.sha256(configuration.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"