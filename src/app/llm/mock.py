"""Deterministic planner used to test the workflow without an external API."""

from app.models import Command, ComplianceRule, Finding, RemediationPlan


class MockLLMProvider:
    """Build a plan from rule ground truth to simulate a valid LLM response."""

    def generate_plan(self, finding: Finding, rule: ComplianceRule) -> RemediationPlan:
        commands = [
            Command(sequence=index, command=command, scope=rule.allowed_scope[0])
            for index, command in enumerate(rule.ground_truth_commands, start=1)
        ]
        return RemediationPlan(
            plan_id=f"plan-{finding.finding_id}",
            finding_id=finding.finding_id,
            summary=f"Remediate {finding.rule_id}",
            commands=commands,
            model_metadata={
                "provider": "mock",
                "model": "deterministic-test-model",
                "prompt_version": "test-1.0.0",
            },
        )


class HallucinatingMockLLMProvider(MockLLMProvider):
    """Add an out-of-context command to exercise hallucination guardrails."""

    def generate_plan(self, finding: Finding, rule: ComplianceRule) -> RemediationPlan:
        plan = super().generate_plan(finding, rule)
        plan.commands.append(
            Command(
                sequence=len(plan.commands) + 1,
                command="interface GigabitEthernet9/9",
                scope="interface",
            )
        )
        return plan