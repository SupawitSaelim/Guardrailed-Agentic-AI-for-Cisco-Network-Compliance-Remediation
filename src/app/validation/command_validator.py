"""Fail-closed validation for remediation commands."""

import re

from app.models import Finding, RemediationPlan, ValidationResult


class CommandScopeValidator:
    """Validate command safety and scope before human approval."""

    DEFAULT_BLOCKLIST = (
        r"^reload(?:\s|$)",
        r"^write\s+erase(?:\s|$)",
        r"^erase\s+startup-config(?:\s|$)",
        r"^format(?:\s|$)",
        r"^delete(?:\s|$)",
        r"^configure\s+replace(?:\s|$)",
        r"^no\s+service\s+password-encryption(?:\s|$)",
        r"^shutdown(?:\s|$)",
        r"^interface\s+.+\s+shutdown(?:\s|$)",
    )

    def __init__(self, max_commands: int = 20) -> None:
        if max_commands < 1:
            raise ValueError("max_commands must be at least 1")
        self.max_commands = max_commands
        self._blocked_patterns = tuple(
            re.compile(pattern, re.IGNORECASE) for pattern in self.DEFAULT_BLOCKLIST
        )

    def validate(self, plan: RemediationPlan, finding: Finding) -> ValidationResult:
        """Return all validation failures without allowing partial execution."""
        schema_errors: list[str] = []
        blocked_commands: list[str] = []
        out_of_scope_commands: list[str] = []
        warnings: list[str] = []

        if plan.finding_id != finding.finding_id:
            schema_errors.append("Plan finding_id does not match the supplied finding")

        if finding.enforcement == "audit_only":
            schema_errors.append("Audit-only findings cannot produce executable plans")

        if len(plan.commands) > self.max_commands:
            schema_errors.append(
                f"Plan contains {len(plan.commands)} commands; maximum is {self.max_commands}"
            )

        allowed_scope = set(finding.allowed_scope)
        for command in plan.commands:
            normalized_command = command.command.strip()
            if any(pattern.search(normalized_command) for pattern in self._blocked_patterns):
                blocked_commands.append(normalized_command)

            if command.scope not in allowed_scope:
                out_of_scope_commands.append(normalized_command)

        valid = not (schema_errors or blocked_commands or out_of_scope_commands)
        return ValidationResult(
            valid=valid,
            schema_errors=schema_errors,
            blocked_commands=blocked_commands,
            out_of_scope_commands=out_of_scope_commands,
            warnings=warnings,
        )