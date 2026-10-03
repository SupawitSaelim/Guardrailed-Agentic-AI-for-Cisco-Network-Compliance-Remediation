"""Provider boundary and structured response parsing for remediation planning."""

import json
from typing import Protocol

from pydantic import ValidationError

from app.models import ComplianceRule, Finding, RemediationPlan


class LLMProvider(Protocol):
    """Interface implemented by cloud or local model adapters."""

    def generate_plan(self, finding: Finding, rule: ComplianceRule) -> RemediationPlan:
        ...


class StructuredPlanParser:
    """Parse untrusted model text into a strict remediation plan."""

    @staticmethod
    def parse(response_text: str) -> RemediationPlan:
        try:
            payload = json.loads(response_text)
            return RemediationPlan.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as error:
            raise ValueError("LLM response is not a valid RemediationPlan JSON") from error