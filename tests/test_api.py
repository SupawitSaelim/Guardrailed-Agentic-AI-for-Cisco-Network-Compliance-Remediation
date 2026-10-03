from fastapi.testclient import TestClient

import app.api as api_module
from app.api import app
from app.execution import ControlledExecutor


client = TestClient(app)


def scenario_payload() -> dict:
    return {
        "scenario_id": "scenario-api-001",
        "configuration": "ntp server 10.10.10.20\n",
        "device_id": "lab-router-01",
        "host": "192.0.2.10",
        "device_type": "cisco_ios",
        "requested_by": "operator-01",
        "rules": [
            {
                "rule_id": "ntp-approved-server",
                "version": "1.0.0",
                "description": "NTP server must be approved",
                "platform": "cisco_ios",
                "expected_state": "ntp server 10.10.10.10",
                "allowed_scope": ["ntp"],
                "ground_truth_commands": ["ntp server 10.10.10.10"],
                "severity": "medium",
            }
        ],
    }


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


def test_api_audits_scenario_and_requires_approval_before_execution() -> None:
    api_module.scenario_store.clear()
    api_module.executor = None

    audit_response = client.post("/scenarios/audit", json=scenario_payload())

    assert audit_response.status_code == 201
    body = audit_response.json()
    assert body["workflow"]["status"] == "approval_pending"
    approval_id = body["workflow"]["approvals"][0]["approval_id"]

    execute_response = client.post("/scenarios/scenario-api-001/execute")

    assert execute_response.status_code == 503

    approval_response = client.post(
        f"/approvals/{approval_id}/approve",
        json={"decided_by": "reviewer-01"},
    )
    assert approval_response.status_code == 200


def test_api_executes_approved_scenario_with_configured_executor() -> None:
    api_module.scenario_store.clear()
    connection = _ScenarioConnection()
    api_module.executor = ControlledExecutor(
        credential_provider=lambda target: {},
        connection_factory=lambda **parameters: connection,
    )

    audit_response = client.post("/scenarios/audit", json=scenario_payload())
    approval_id = audit_response.json()["workflow"]["approvals"][0]["approval_id"]
    client.post(
        f"/approvals/{approval_id}/approve",
        json={"decided_by": "reviewer-01"},
    )

    execute_response = client.post("/scenarios/scenario-api-001/execute")

    assert execute_response.status_code == 200
    assert execute_response.json()["live"]["reaudit"]["post_compliant"] is True


def test_api_registers_inventory_device_and_audits_collected_configuration() -> None:
    api_module.inventory_store.clear()
    api_module.credential_store.clear()
    api_module.scenario_store.clear()
    api_module.collector = _FakeCollector()

    register_response = client.post(
        "/devices",
        json={
            "device_id": "lab-router-inventory",
            "host": "192.0.2.20",
            "device_type": "cisco_ios",
            "credential_profile": "lab-router-profile",
            "username": "lab-user",
            "password": "lab-password",
            "secret": "enable-secret",
        },
    )

    assert register_response.status_code == 201
    assert client.get("/devices").json()[0]["target"]["host"] == "192.0.2.20"
    assert "password" not in register_response.json()
    assert api_module.credential_store["lab-router-inventory"]["username"] == "lab-user"

    audit_response = client.post(
        "/devices/lab-router-inventory/audit",
        json={
            "scenario_id": "inventory-audit-001",
            "rules": scenario_payload()["rules"],
            "requested_by": "operator-01",
        },
    )

    assert audit_response.status_code == 201
    assert audit_response.json()["target"]["device_id"] == "lab-router-inventory"
    assert audit_response.json()["configuration"] == "ntp server 10.10.10.20\n"
    assert api_module.inventory_store["lab-router-inventory"].status == "reachable"


class _ScenarioConnection:
    def __init__(self) -> None:
        self.reads = 0

    def send_command(self, command: str) -> str:
        self.reads += 1
        return (
            "ntp server 10.10.10.20\n"
            if self.reads == 1
            else "ntp server 10.10.10.10\n"
        )

    def send_config_set(self, commands: list[str]) -> str:
        return "ok"

    def disconnect(self) -> None:
        pass


class _FakeCollector:
    def collect(self, target) -> str:
        assert target.host == "192.0.2.20"
        return "ntp server 10.10.10.20\n"