from fastapi.testclient import TestClient

from app.api import app


client = TestClient(app)


def approval_payload() -> dict:
    return {
        "plan": {
            "plan_id": "plan-api-001",
            "finding_id": "finding-api-001",
            "summary": "Replace NTP server",
            "commands": [
                {
                    "sequence": 1,
                    "command": "ntp server 10.10.10.10",
                    "scope": "ntp",
                }
            ],
            "assumptions": [],
            "requires_approval": True,
            "model_metadata": {
                "provider": "test",
                "model": "test-model",
                "prompt_version": "1.0.0",
            },
        },
        "finding": {
            "finding_id": "finding-api-001",
            "device_id": "lab-router-01",
            "rule_id": "ntp-approved-server",
            "severity": "medium",
            "expected": "ntp server 10.10.10.10",
            "actual": ["ntp server 10.10.10.20"],
            "evidence": ["ntp server 10.10.10.20"],
            "allowed_scope": ["ntp"],
            "rule_version": "1.0.0",
        },
        "validation": {"valid": True},
        "requested_by": "operator-01",
    }


def test_api_can_create_and_approve_request() -> None:
    create_response = client.post("/approvals", json=approval_payload())

    assert create_response.status_code == 201
    approval_id = create_response.json()["approval_id"]
    assert create_response.json()["status"] == "pending"

    decide_response = client.post(
        f"/approvals/{approval_id}/approve",
        json={"decided_by": "reviewer-01"},
    )

    assert decide_response.status_code == 200
    assert decide_response.json()["status"] == "approved"


def test_api_rejects_invalid_plan() -> None:
    payload = approval_payload()
    payload["validation"] = {"valid": False, "blocked_commands": ["reload"]}

    response = client.post("/approvals", json=payload)

    assert response.status_code == 422