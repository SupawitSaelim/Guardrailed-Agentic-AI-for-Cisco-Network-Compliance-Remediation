"""Compare pre-change and post-change audits for remediation and regression."""

from app.models import AuditResult, ReauditResult
from app.audit import AuditTrail


class ReauditService:
    """Evaluate whether a remediation fixed its target without new failures."""

    def __init__(self, audit_trail: AuditTrail | None = None) -> None:
        self.audit_trail = audit_trail

    def compare(self, before: AuditResult, after: AuditResult) -> ReauditResult:
        if before.device_id != after.device_id:
            raise ValueError("Pre-check and post-check must target the same device")
        if before.rule_version != after.rule_version:
            raise ValueError("Pre-check and post-check must use the same rule version")

        before_failed_rule_ids = {finding.rule_id for finding in before.findings}
        unresolved_findings = [
            finding
            for finding in after.findings
            if finding.rule_id in before_failed_rule_ids
        ]
        regression_findings = [
            finding
            for finding in after.findings
            if finding.rule_id not in before_failed_rule_ids
        ]

        result = ReauditResult(
            device_id=after.device_id,
            remediation_succeeded=not unresolved_findings and not regression_findings,
            post_compliant=after.compliant,
            unresolved_findings=unresolved_findings,
            regression_findings=regression_findings,
        )
        if self.audit_trail:
            self.audit_trail.append(
                "reaudit.completed",
                {
                    "device_id": result.device_id,
                    "remediation_succeeded": result.remediation_succeeded,
                    "post_compliant": result.post_compliant,
                    "unresolved_count": len(result.unresolved_findings),
                    "regression_count": len(result.regression_findings),
                },
            )
        return result