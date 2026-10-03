# Technical Design

## 1. Suggested stack

- Python 3.11+
- Netmiko
- Pydantic
- FastAPI, optional for the first milestone
- PyYAML
- pytest
- SQLite or JSONL for the first experiment store

## 2. Suggested package layout

```text
src/
  app/
    api/
    audit/
    compliance/
    context/
    execution/
    llm/
    validation/
    storage/
    evaluation/
tests/
  fixtures/
  unit/
  integration/
configs/
  compliance_rules.yaml
scenarios/
  single_fault/
  concurrent_faults/
  context_deficit/
```

## 3. Core interfaces

```python
class ComplianceChecker(Protocol):
    def audit(self, configuration: str, rules: list[ComplianceRule]) -> AuditResult: ...

class LLMProvider(Protocol):
    def generate_plan(self, request: PlanRequest) -> RemediationPlan: ...

class PlanValidator(Protocol):
    def validate(self, plan: RemediationPlan, finding: Finding) -> ValidationResult: ...

class DeviceExecutor(Protocol):
    def execute(self, target: LabTarget, commands: list[str]) -> ExecutionResult: ...
```

The implemented workflow now exposes a `run_target` entry point that collects
the sanitized running configuration before auditing. The resulting
configuration hash is retained as the expected pre-execution snapshot.
`ControlledExecutor` compares its fresh pre-check with that hash and refuses
to write when configuration drift is detected. Approval and execution are
still separate state transitions.
For a multi-fault scenario, its batch operation verifies every approval before
opening one connection, submits the combined command set, captures one
post-check configuration, and returns that snapshot to re-audit.

The FastAPI transport exposes scenario-level audit, retrieval, and execution
endpoints around this workflow. The API keeps scenario state in memory for the
prototype; a persistent store is required before production use. The execute
endpoint refuses to run unless all scenario approvals are approved and a
Lab-only executor has been explicitly configured.

## 4. Implementation order

1. Pydantic data contracts and fixture loading.
2. Deterministic compliance rules and unit tests.
3. Command and scope validator with blocklist tests.
4. Mock LLM provider and planner workflow.
5. Netmiko collector and execution controller for the lab.
6. Post-check, re-audit, and audit storage.
7. Real LLM provider adapter.
8. Evaluation scripts and experiment runner.

## 5. Error handling

All validation and execution failures must produce a typed result and audit event. The default action for ambiguity, missing fields, unsupported syntax, or target mismatch is rejection.
