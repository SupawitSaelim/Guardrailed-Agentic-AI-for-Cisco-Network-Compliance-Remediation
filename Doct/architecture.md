# System Architecture

## 1. Boundary

The system is split into a trusted control plane and an untrusted planning component.

```text
Lab Device
   |
   | read-only collection
   v
Netmiko Collector
   v
Compliance Engine ---> Finding
   v
Context Builder ---> LLM Provider
                         v
                 Structured Plan Validator
                         v
                 Command/Scope Validator
                         v
                    Human Approval
                         v
                 Netmiko Execution Controller
                         v
                 Post-check and Re-audit
                         v
                    Audit and Metrics Store
```

## 2. Component responsibilities

### Collector

Reads device state and returns sanitized configuration data. It must not decide compliance.

### Compliance Engine

The deterministic source of truth. It evaluates versioned policies and creates findings with expected values and allowed scope.

### Context Builder

Constructs the smallest context needed by the planner. It supports Full Context and controlled Context-Deficit variants for experiments.

### LLM Provider

A replaceable interface for a cloud LLM. It receives no credentials and has no device tool access.

### Plan Validator

Validates JSON structure, required fields, types, command count, and plan completeness.

### Command/Scope Validator

Checks blocklist, allowlist, command syntax, mode transitions, target scope, and maximum command limits. It fails closed.

### Approval Service

Presents the proposed commands and validation results to the operator and records approve/reject with an identity and timestamp.

### Execution Controller

The only component permitted to use write credentials. It connects only to an explicitly registered lab target.

### Re-auditor

Runs post-checks and the compliance engine again, then detects unresolved findings and regressions.

## 3. Trust rules

- LLM output is untrusted input.
- Compliance results do not come from the LLM.
- Approval cannot bypass validation.
- Execution cannot happen without approval.
- Production targets are rejected by configuration and environment checks.

## 4. Initial workflow states

`COLLECTED -> AUDITED -> PLANNED -> VALIDATED -> PENDING_APPROVAL -> APPROVED -> EXECUTED -> REAUDITED`

Failure states include `REJECTED`, `VALIDATION_FAILED`, `EXECUTION_FAILED`, and `RE_AUDIT_FAILED`.
