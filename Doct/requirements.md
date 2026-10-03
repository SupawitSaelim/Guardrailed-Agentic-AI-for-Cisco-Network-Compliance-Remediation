# Requirements Specification

## 1. Objective

Build a lab-only system that detects selected Cisco IOS/IOS XE compliance violations and produces a validated remediation plan for human approval.

## 2. Actors

- Operator: starts audits, reviews plans, and approves or rejects execution.
- Compliance Engine: deterministically evaluates configuration against policy.
- LLM Planner: proposes a structured plan from a finding and bounded context.
- Execution Controller: runs approved commands through Netmiko.
- Evaluator: calculates experimental metrics from recorded artifacts.

## 3. Functional requirements

### FR-01: Configuration collection

The system shall collect a sanitized running configuration from a lab device using read-only access.

### FR-02: Compliance evaluation

The system shall evaluate configuration using versioned deterministic rules and produce Pass/Fail findings.

### FR-03: Remediation planning

The system shall send only the required finding, bounded configuration context, policy, and allowed scope to the LLM.

### FR-04: Structured output

The LLM response shall conform to the RemediationPlan schema or be rejected.

### FR-05: Command validation

The system shall reject malformed, blocked, or unsupported commands.

### FR-06: Scope validation

The system shall reject commands outside the allowed scope for the finding.

### FR-07: Human approval

The system shall require explicit approval before any write operation.

### FR-08: Controlled execution

The system shall execute only the approved command set on a designated virtual lab device.

### FR-09: Post-check and re-audit

The system shall collect post-change state, rerun compliance checks, and record regressions.

### FR-10: Audit trail

The system shall record input identifiers, model metadata, response, validation results, approval, executed commands, and post-check results without secrets.

### FR-11: Production-reference sanitization

The system shall support policy patterns derived from a production reference while using only synthetic IP addresses, hostnames, credentials, secrets, and topology data in Lab scenarios.

### FR-12: Enforcement classification

Each compliance rule shall declare whether it is remediation-eligible or audit-only. Audit-only findings shall not produce executable remediation commands.

## 4. Non-functional requirements

- No production connectivity or production credentials.
- Deterministic checks must be reproducible from the same input and rule version.
- Invalid LLM output must fail closed.
- Secrets must never be included in prompts or logs.
- Each experiment run must be reproducible from stored scenario, prompt, model, and parameter versions.
- The core workflow must be usable from a CLI or API without requiring a dashboard.

## 5. Acceptance criteria

A prototype is acceptable when it can:

1. Audit the initial compliance rules against fixture configurations.
2. Produce a valid remediation plan for a valid finding.
3. block an unsafe command and an out-of-scope command before execution.
4. require approval before write execution.
5. re-audit after execution and report Pass/Fail.
6. export machine-readable artifacts for evaluation.
