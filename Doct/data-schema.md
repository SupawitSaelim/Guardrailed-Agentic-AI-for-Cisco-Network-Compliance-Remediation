# Data Schema

The following contracts are the initial implementation boundary. Field names may be refined during coding, but changes must be versioned.

## Finding

```json
{
  "finding_id": "finding-001",
  "device_id": "lab-router-01",
  "rule_id": "ntp-approved-server",
  "severity": "medium",
  "expected": "ntp server 10.10.10.10",
  "actual": ["ntp server 10.10.10.20"],
  "evidence": ["ntp server 10.10.10.20"],
  "allowed_scope": ["ntp"],
  "rule_version": "1.0.0",
  "enforcement": "remediation"
}
```

`enforcement` is either `remediation` or `audit_only`. Audit-only findings may be reported and measured but cannot produce executable plans.

## ComplianceRule

```json
{
  "rule_id": "ntp-approved-server",
  "version": "1.1.0",
  "description": "NTP server must be approved",
  "platform": "cisco_ios",
  "expected_state": "ntp server 192.0.2.10",
  "allowed_scope": ["ntp"],
  "ground_truth_commands": [
    "no ntp server 192.0.2.11",
    "ntp server 192.0.2.10"
  ],
  "blocked_commands": ["reload", "write erase"],
  "severity": "medium",
  "enforcement": "remediation"
}
```

`platform` is `cisco_ios` or `cisco_ios_xe`. `enforcement` controls whether a finding can produce executable commands.

## AuditResult

```json
{
  "device_id": "lab-router-01",
  "compliant": false,
  "findings": [],
  "rule_version": "1.1.0",
  "evaluated_rule_ids": ["ntp-approved-server", "ssh-v2"]
}
```

## ReauditResult

```json
{
  "device_id": "lab-router-01",
  "remediation_succeeded": true,
  "post_compliant": true,
  "unresolved_findings": [],
  "regression_findings": []
}
```

`unresolved_findings` are failures that existed before remediation and remain afterward. `regression_findings` are new failures detected after the change.

## RemediationPlan

```json
{
  "plan_id": "plan-001",
  "finding_id": "finding-001",
  "summary": "Replace the non-approved NTP server",
  "commands": [
    {"sequence": 1, "command": "no ntp server 10.10.10.20", "scope": "ntp"},
    {"sequence": 2, "command": "ntp server 10.10.10.10", "scope": "ntp"}
  ],
  "assumptions": [],
  "requires_approval": true,
  "model_metadata": {
    "provider": "example",
    "model": "example-model",
    "prompt_version": "1.0.0"
  }
}
```

## ValidationResult

```json
{
  "valid": false,
  "schema_errors": [],
  "blocked_commands": [],
  "out_of_scope_commands": [],
  "warnings": []
}
```

## ApprovalRecord

```json
{
  "approval_id": "approval-001",
  "plan": {},
  "finding": {},
  "validation": {"valid": true},
  "requested_by": "operator-01",
  "status": "pending",
  "decided_by": null,
  "decision_reason": null,
  "requested_at": "2026-10-03T00:00:00Z",
  "decided_at": null
}
```

`status` is `pending`, `approved`, or `rejected`. Execution is allowed only when the status is `approved`.

## ExecutionResult

```json
{
  "execution_id": "exec-001",
  "device_id": "lab-router-01",
  "approved_by": "operator-id",
  "commands": ["..."],
  "success": true,
  "precheck_hash": "sha256:...",
  "postcheck_hash": "sha256:...",
  "started_at": "2026-10-03T00:00:00Z",
  "finished_at": "2026-10-03T00:00:10Z"
}
```

## AuditTrailEvent

Audit events are stored as JSON Lines. Each line is one event.

```json
{
  "event_id": "event-001",
  "event_type": "approval.decided",
  "timestamp": "2026-10-03T00:00:00Z",
  "payload": {
    "approval_id": "approval-001",
    "status": "approved",
    "decided_by": "reviewer-01"
  }
}
```

Known secret keys such as `password`, `token`, `api_key`, `secret`, `private_key`, and `community_string` must be replaced with `[REDACTED]` before persistence.

## ExperimentScenario

```json
{
  "scenario_id": "single-fault-001",
  "device_id": "lab-router-01",
  "configuration": "ntp server 192.0.2.11",
  "rules": [],
  "group": "D",
  "context_variant": "full",
  "requested_by": "researcher-01"
}
```

`group` is `A`, `B`, `C`, or `D`. `context_variant` identifies Full Context or a controlled Context-Deficit condition.

## ExperimentRecord

```json
{
  "scenario_id": "single-fault-001",
  "group": "D",
  "context_variant": "full",
  "workflow_status": "approval_pending",
  "finding_count": 1,
  "plan_count": 1,
  "valid_plan_count": 1,
  "unsafe_command_count": 0,
  "out_of_scope_change": false,
  "remediation_correct": true,
  "latency_seconds": 1.25,
  "input_tokens": 0,
  "output_tokens": 0,
  "api_cost": 0.0
}
```

## EvaluationRun

```json
{
  "remediation_correct": true,
  "proposed_command_count": 2,
  "unsafe_command_count": 0,
  "out_of_scope": false,
  "regression": false,
  "latency_seconds": 1.25,
  "input_tokens": 1200,
  "output_tokens": 180,
  "api_cost": 0.0042
}
```

`EvaluationRun` is the normalized input to `MetricsCalculator`. It must contain only sanitized Lab data and measurement metadata.

Secrets, passwords, tokens, private keys, and full unsanitized configurations must not appear in LLM requests or persisted audit records.
