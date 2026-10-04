import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

import app.api as api_module
from app.api import app
from app.collection import LabTarget
from app.execution import ControlledExecutor


client = TestClient(app)
api_module.inventory_data_file = Path(tempfile.mkdtemp()) / "lab_inventory.json"
api_module.inventory_store.clear()
api_module.credential_store.clear()


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


def test_api_supports_manual_chatbot_remediation_import() -> None:
    api_module.scenario_store.clear()
    api_module.approval_service._records.clear()

    audit_response = client.post(
        "/scenarios/audit",
        json={**scenario_payload(), "manual_remediation": True},
    )

    assert audit_response.status_code == 201
    scenario_id = audit_response.json()["scenario_id"]
    assert audit_response.json()["workflow"]["status"] == "awaiting_remediation"
    prompt_response = client.get(
        f"/scenarios/{scenario_id}/remediation-prompt",
    )
    assert prompt_response.status_code == 200
    assert prompt_response.json()["finding"]["rule_id"] == "ntp-approved-server"

    response = client.post(
        f"/scenarios/{scenario_id}/remediation-response",
        json={
            "summary": "Replace the NTP server",
            "commands": [
                {
                    "sequence": 1,
                    "command": "ntp server 10.10.10.10",
                    "scope": "ntp",
                }
            ],
            "assumptions": [],
        },
    )

    assert response.status_code == 200
    assert response.json()["workflow"]["status"] == "approval_pending"
    assert response.json()["workflow"]["approvals"][0]["plan"]["model_metadata"]["provider"] == "manual-chatbot"


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


def test_api_executes_all_approved_scenarios_and_skips_pending() -> None:
    api_module.scenario_store.clear()
    api_module.approval_service._records.clear()
    connections: list[_ScenarioConnection] = []

    def connection_factory(**parameters):
        connection = _ScenarioConnection()
        connections.append(connection)
        return connection

    api_module.executor = ControlledExecutor(
        credential_provider=lambda target: {},
        connection_factory=connection_factory,
    )

    first_payload = {**scenario_payload(), "scenario_id": "batch-approved-01"}
    second_payload = {
        **scenario_payload(),
        "scenario_id": "batch-pending-02",
        "device_id": "lab-router-02",
    }
    first_audit = client.post("/scenarios/audit", json=first_payload)
    second_audit = client.post("/scenarios/audit", json=second_payload)
    first_approval = first_audit.json()["workflow"]["approvals"][0]["approval_id"]
    client.post(
        f"/approvals/{first_approval}/approve",
        json={"decided_by": "reviewer-01"},
    )

    response = client.post("/scenarios/execute-all")

    assert response.status_code == 200
    assert response.json()["executed_count"] == 1
    assert response.json()["skipped_count"] == 1
    assert response.json()["failed_count"] == 0
    assert {item["status"] for item in response.json()["results"]} == {"executed", "skipped"}
    assert len(connections) == 1


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


def test_api_updates_inventory_device_name_and_host() -> None:
    api_module.inventory_store.clear()
    api_module.credential_store.clear()
    response = client.post(
        "/devices",
        json={
            "device_id": "R4",
            "host": "192.0.2.24",
            "device_type": "cisco_ios",
        },
    )
    assert response.status_code == 201

    response = client.put(
        "/devices/R4",
        json={
            "device_id": "R4-renamed",
            "host": "192.0.2.44",
            "device_type": "cisco_xe",
        },
    )

    assert response.status_code == 200
    assert response.json()["device_id"] == "R4-renamed"
    assert response.json()["target"]["host"] == "192.0.2.44"
    assert client.get("/devices/R4").status_code == 404
    assert client.get("/devices/R4-renamed").json()["target"]["device_type"] == "cisco_xe"


def test_api_audits_all_inventory_devices() -> None:
    api_module.inventory_store.clear()
    api_module.credential_store.clear()
    api_module.scenario_store.clear()
    api_module.collector = _MultiCollector()

    for device_id, host in (("lab-router-01", "192.0.2.21"), ("lab-router-02", "192.0.2.22")):
        response = client.post(
            "/devices",
            json={
                "device_id": device_id,
                "host": host,
                "device_type": "cisco_ios",
                "credential_profile": f"{device_id}-profile",
                "username": "lab-user",
                "password": "lab-password",
            },
        )
        assert response.status_code == 201

    response = client.post(
        "/devices/audit-all",
        json={
            "scenario_id": "batch-audit-001",
            "rules": scenario_payload()["rules"],
            "requested_by": "operator-01",
        },
    )

    assert response.status_code == 200
    assert response.json()["audited_count"] == 2
    assert response.json()["failed_count"] == 0
    assert set(api_module.scenario_store) == {
        "batch-audit-001-lab-router-01",
        "batch-audit-001-lab-router-02",
    }


def test_api_resets_scenarios_without_persisting_inventory() -> None:
    api_module.scenario_store["old-scenario"] = scenario_payload()
    api_module.inventory_store["R4"] = api_module.InventoryRecord(
        device_id="R4",
        target=LabTarget(device_id="R4", host="192.0.2.24", device_type="cisco_ios"),
        credential_profile="global",
        status="reachable",
        last_audit_scenario_id="old-scenario",
        last_audit_status="approval_pending",
    )

    response = client.post("/scenarios/reset")

    assert response.status_code == 200
    assert response.json() == {"cleared": True}
    assert api_module.scenario_store == {}
    assert api_module.inventory_store["R4"].status == "registered"
    assert api_module.inventory_store["R4"].last_audit_scenario_id is None
    assert api_module.inventory_store["R4"].last_audit_status is None


def test_api_web_terminal_connects_and_returns_command_output(monkeypatch) -> None:
    api_module.inventory_store.clear()
    api_module.credential_store.clear()
    api_module.inventory_store["R4"] = api_module.InventoryRecord(
        device_id="R4",
        target=LabTarget(device_id="R4", host="192.0.2.24", device_type="cisco_ios"),
        credential_profile="global",
    )
    api_module.credential_store.update(
        {"username": "admin", "password": "password", "secret": "", "port": 22}
    )
    connection = _TerminalConnection()
    monkeypatch.setattr(api_module, "ConnectHandler", lambda **kwargs: connection)

    with client.websocket_connect("/devices/R4/terminal") as websocket:
        assert websocket.receive_json()["type"] == "status"
        websocket.send_text("show version")
        message = websocket.receive_json()

    assert message == {"type": "output", "data": "R4#show version\n"}
    assert connection.disconnected is True


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


class _MultiCollector:
    def collect(self, target) -> str:
        return "ntp server 10.10.10.20\n"


class _TerminalConnection:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.disconnected = False

    def write_channel(self, value: str) -> None:
        self.commands.append(value)

    def read_channel(self) -> str:
        if "show version" in self.commands:
            return "R4#show version\n"
        return ""

    def disconnect(self) -> None:
        self.disconnected = True