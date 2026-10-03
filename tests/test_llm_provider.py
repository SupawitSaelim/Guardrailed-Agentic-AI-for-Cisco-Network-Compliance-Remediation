import json

import pytest

from app.llm import StructuredPlanParser


def valid_plan_payload() -> dict:
    return {
        "plan_id": "plan-001",
        "finding_id": "finding-001",
        "summary": "Replace NTP server",
        "commands": [
            {
                "sequence": 1,
                "command": "ntp server 10.10.10.10",
                "scope": "ntp",
            }
        ],
        "requires_approval": True,
        "model_metadata": {
            "provider": "test",
            "model": "test-model",
            "prompt_version": "1.0.0",
        },
    }


def test_parser_accepts_valid_json_plan() -> None:
    plan = StructuredPlanParser.parse(json.dumps(valid_plan_payload()))

    assert plan.plan_id == "plan-001"
    assert plan.commands[0].scope == "ntp"


@pytest.mark.parametrize(
    "response_text",
    [
        "not-json",
        json.dumps({"plan_id": "missing-required-fields"}),
        json.dumps({**valid_plan_payload(), "unexpected": "reject"}),
    ],
)
def test_parser_rejects_invalid_model_output(response_text: str) -> None:
    with pytest.raises(ValueError, match="valid RemediationPlan JSON"):
        StructuredPlanParser.parse(response_text)