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
