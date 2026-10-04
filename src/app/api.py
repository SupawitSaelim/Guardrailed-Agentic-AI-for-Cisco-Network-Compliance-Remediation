"""FastAPI transport for the approval workflow."""

import json
import os
import asyncio
from pathlib import Path
from typing import Literal
from threading import Lock

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoBaseException
from paramiko.ssh_exception import SSHException
from pydantic import BaseModel, Field

from app.approval import ApprovalService
from app.collection import LabTarget, NetmikoCollector
from app.execution import ControlledExecutor
from app.llm import MockLLMProvider
from app.models import ComplianceRule, Finding, RemediationPlan, ValidationResult
from app.workflow import WorkflowOrchestrator, WorkflowResult, LiveWorkflowResult

COLLECTION_ERRORS = (
    NetmikoBaseException,
    SSHException,
    EOFError,
    RuntimeError,
    ValueError,
    OSError,
    TimeoutError,
)


app = FastAPI(title="Guardrailed Cisco Compliance API", version="0.1.0")
approval_service = ApprovalService()
workflow = WorkflowOrchestrator(MockLLMProvider(), approval_service=approval_service)
executor: ControlledExecutor | None = None
scenario_store: dict[str, "ScenarioRecord"] = {}
inventory_store: dict[str, "InventoryRecord"] = {}
credential_store: dict[str, object] = {}
scenario_lock = Lock()
inventory_data_file = Path(
    os.getenv(
        "GUARDRAILED_INVENTORY_FILE",
        str(Path(__file__).resolve().parents[2] / "data" / "lab_inventory.json"),
    )
)


class ApprovalRequest(BaseModel):
    plan: RemediationPlan
    finding: Finding
    validation: ValidationResult
    requested_by: str = Field(min_length=1)


class DecisionRequest(BaseModel):
    decided_by: str = Field(min_length=1)
    reason: str | None = None


class ScenarioRequest(BaseModel):
    scenario_id: str = Field(min_length=1)
    configuration: str
    device_id: str = Field(min_length=1)
    host: str = Field(min_length=1)
    device_type: Literal["cisco_ios", "cisco_xe"]
    rules: list[ComplianceRule] = Field(min_length=1)
    requested_by: str = Field(min_length=1)
    manual_remediation: bool = False


class DeviceRequest(BaseModel):
    device_id: str = Field(min_length=1)
    host: str = Field(min_length=1)
    device_type: Literal["cisco_ios", "cisco_xe"]
    credential_profile: str = "global"
    username: str | None = None
    password: str | None = None
    secret: str | None = None


class DeviceUpdateRequest(BaseModel):
    device_id: str = Field(min_length=1)
    host: str = Field(min_length=1)
    device_type: Literal["cisco_ios", "cisco_xe"]


class GlobalCredentialRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)
    secret: str = ""
    port: int = Field(default=22, ge=1, le=65535)


class GlobalCredentialStatus(BaseModel):
    configured: bool
    username: str | None = None
    port: int = 22


class InventoryRecord(BaseModel):
    device_id: str
    target: LabTarget
    credential_profile: str
    status: Literal["registered", "reachable", "unreachable"] = "registered"
    last_audit_scenario_id: str | None = None
    last_audit_status: str | None = None


class DeviceAuditRequest(BaseModel):
    scenario_id: str = Field(min_length=1)
    rules: list[ComplianceRule] = Field(min_length=1)
    requested_by: str = Field(min_length=1)
    manual_remediation: bool = True


class RemediationResponse(BaseModel):
    summary: str = Field(min_length=1)
    commands: list[dict[str, object]] = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)


class ScenarioRecord(BaseModel):
    scenario_id: str
    configuration: str
    target: LabTarget
    rules: list[ComplianceRule]
    workflow: WorkflowResult
    live: LiveWorkflowResult | None = None


class BatchExecutionItem(BaseModel):
    scenario_id: str
    device_id: str
    status: Literal["executed", "skipped", "failed"]
    detail: str | None = None


class BatchExecutionResult(BaseModel):
    executed_count: int
    skipped_count: int
    failed_count: int
    results: list[BatchExecutionItem]


class BatchAuditItem(BaseModel):
    device_id: str
    scenario_id: str
    status: Literal["audited", "failed"]
    detail: str | None = None


class BatchAuditResult(BaseModel):
    audited_count: int
    failed_count: int
    results: list[BatchAuditItem]


def _credential_provider(target: LabTarget) -> dict[str, object]:
    credentials = {
        key: credential_store[key]
        for key in ("username", "password", "secret", "port")
        if key in credential_store
    }
    if not credentials:
        raise RuntimeError("Global SSH credentials are not configured")
    return credentials


def _persist_inventory() -> None:
    inventory_data_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "devices": [device.model_dump(mode="json") for device in inventory_store.values()],
        "credentials": credential_store,
    }
    temporary_file = inventory_data_file.with_suffix(".tmp")
    temporary_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary_file.replace(inventory_data_file)
    try:
        inventory_data_file.chmod(0o600)
    except OSError:
        pass


def _load_inventory() -> None:
    if not inventory_data_file.exists():
        return
    try:
        payload = json.loads(inventory_data_file.read_text(encoding="utf-8"))
        inventory_store.clear()
        credential_store.clear()
        for item in payload.get("devices", []):
            record = InventoryRecord.model_validate(item)
            inventory_store[record.device_id] = record
        credentials = payload.get("credentials", {})
        if isinstance(credentials, dict):
            credential_store.update(credentials)
    except (OSError, ValueError, TypeError) as error:
        raise RuntimeError(
            f"Could not load inventory database {inventory_data_file}: {error}"
        ) from error


collector = NetmikoCollector(_credential_provider)
executor = ControlledExecutor(
    credential_provider=_credential_provider,
    connection_factory=ConnectHandler,
)
_load_inventory()


@app.post("/approvals", status_code=201)
def create_approval(request: ApprovalRequest):
    try:
        return approval_service.request(
            request.plan,
            request.finding,
            request.validation,
            request.requested_by,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/approvals")
def list_approvals():
    return approval_service.list()


@app.get("/approvals/{approval_id}")
def get_approval(approval_id: str):
    try:
        return approval_service.get(approval_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/approvals/{approval_id}/{decision}")
def decide_approval(
    approval_id: str,
    decision: Literal["approve", "reject"],
    request: DecisionRequest,
):
    status = "approved" if decision == "approve" else "rejected"
    try:
        return approval_service.decide(
            approval_id,
            status,
            request.decided_by,
            request.reason,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/scenarios/audit", status_code=201)
def audit_scenario(request: ScenarioRequest):
    try:
        result = workflow.run(
            request.configuration,
            request.rules,
            request.device_id,
            request.requested_by,
            generate_plans=not request.manual_remediation,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    record = ScenarioRecord(
        scenario_id=request.scenario_id,
        configuration=request.configuration,
        target=LabTarget(
            device_id=request.device_id,
            host=request.host,
            device_type=request.device_type,
        ),
        rules=request.rules,
        workflow=result,
    )
    with scenario_lock:
        scenario_store[record.scenario_id] = record
    return record


@app.post("/devices", status_code=201)
def register_device(request: DeviceRequest):
    if request.device_id in inventory_store:
        raise HTTPException(status_code=409, detail="Device is already registered")
    target = LabTarget(
        device_id=request.device_id,
        host=request.host,
        device_type=request.device_type,
    )
    record = InventoryRecord(
        device_id=request.device_id,
        target=target,
        credential_profile=request.credential_profile,
    )
    with scenario_lock:
        inventory_store[record.device_id] = record
        if request.username and request.password:
            credential_store.update(
                {
                    "username": request.username,
                    "password": request.password,
                    "secret": request.secret or "",
                }
            )
            # Accept older clients while all connections use the same global values.
            credential_store[request.device_id] = {
                "username": request.username,
                "password": request.password,
                "secret": request.secret or "",
            }
        _persist_inventory()
    return record


@app.get("/devices")
def list_devices():
    _load_inventory()
    with scenario_lock:
        return list(inventory_store.values())


@app.post("/scenarios/reset")
def reset_scenarios():
    with scenario_lock:
        scenario_store.clear()
        for device_id, device in inventory_store.items():
            inventory_store[device_id] = device.model_copy(
                update={
                    "status": "registered",
                    "last_audit_scenario_id": None,
                    "last_audit_status": None,
                }
            )
    return {"cleared": True}


@app.get("/settings/credentials")
def get_global_credentials() -> GlobalCredentialStatus:
    return GlobalCredentialStatus(
        configured=bool(credential_store),
        username=credential_store.get("username") if isinstance(credential_store.get("username"), str) else None,
        port=int(credential_store.get("port", 22)),
    )


@app.put("/settings/credentials")
def update_global_credentials(request: GlobalCredentialRequest) -> GlobalCredentialStatus:
    with scenario_lock:
        credential_store.clear()
        credential_store.update(
            {
                "username": request.username,
                "password": request.password,
                "secret": request.secret,
                "port": request.port,
            }
        )
        _persist_inventory()
    return get_global_credentials()


@app.get("/devices/{device_id}")
def get_device(device_id: str):
    try:
        return inventory_store[device_id]
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Unknown inventory device") from error


@app.put("/devices/{device_id}")
def update_device(device_id: str, request: DeviceUpdateRequest):
    try:
        current = inventory_store[device_id]
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Unknown inventory device") from error
    if request.device_id != device_id and request.device_id in inventory_store:
        raise HTTPException(status_code=409, detail="Device name is already registered")

    updated = current.model_copy(
        update={
            "device_id": request.device_id,
            "target": LabTarget(
                device_id=request.device_id,
                host=request.host,
                device_type=request.device_type,
            ),
        }
    )
    with scenario_lock:
        del inventory_store[device_id]
        inventory_store[request.device_id] = updated
        _persist_inventory()
    return updated


@app.websocket("/devices/{device_id}/terminal")
async def device_terminal(device_id: str, websocket: WebSocket):
    await websocket.accept()
    device = inventory_store.get(device_id)
    if device is None:
        await websocket.send_json({"type": "error", "message": "Unknown inventory device"})
        await websocket.close(code=1008)
        return

    connection = None
    try:
        credentials = _credential_provider(device.target)
        connection = await asyncio.to_thread(
            ConnectHandler,
            device_type=device.target.device_type,
            host=device.target.host,
            ssh_strict=False,
            use_keys=False,
            allow_agent=False,
            conn_timeout=10,
            auth_timeout=10,
            banner_timeout=15,
            **credentials,
        )
        await websocket.send_json(
            {"type": "status", "message": f"Connected to {device.device_id}"}
        )
        connection.write_channel("\n")
        initial_output = await asyncio.to_thread(connection.read_channel)
        if initial_output:
            await websocket.send_json({"type": "output", "data": initial_output})

        while True:
            message = await websocket.receive_text()
            await asyncio.to_thread(connection.write_channel, message)
            await asyncio.sleep(0.1)
            output = await asyncio.to_thread(connection.read_channel)
            if output:
                await websocket.send_json({"type": "output", "data": output})
    except WebSocketDisconnect:
        pass
    except (NetmikoBaseException, SSHException, RuntimeError, OSError) as error:
        try:
            await websocket.send_json({"type": "error", "message": str(error)})
        except RuntimeError:
            pass
    finally:
        if connection is not None:
            connection.disconnect()


@app.post("/devices/{device_id}/audit", status_code=201)
def audit_device(device_id: str, request: DeviceAuditRequest):
    try:
        device = inventory_store[device_id]
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Unknown inventory device") from error
    try:
        configuration = collector.collect(device.target)
        result = workflow.run(
            configuration,
            request.rules,
            device.device_id,
            request.requested_by,
            generate_plans=not request.manual_remediation,
        )
    except COLLECTION_ERRORS as error:
        updated = device.model_copy(update={"status": "unreachable"})
        with scenario_lock:
            inventory_store[device_id] = updated
        raise HTTPException(status_code=503, detail=str(error)) from error
    record = ScenarioRecord(
        scenario_id=request.scenario_id,
        configuration=configuration,
        target=device.target,
        rules=request.rules,
        workflow=result,
    )
    with scenario_lock:
        scenario_store[record.scenario_id] = record
        inventory_store[device_id] = device.model_copy(
            update={
                "status": "reachable",
                "last_audit_scenario_id": record.scenario_id,
                "last_audit_status": result.status,
            }
        )
    return record


@app.post("/devices/audit-all")
def audit_all_devices(request: DeviceAuditRequest) -> BatchAuditResult:
    with scenario_lock:
        devices = list(inventory_store.values())
    results: list[BatchAuditItem] = []

    for device in devices:
        scenario_id = f"{request.scenario_id}-{device.device_id}"
        try:
            configuration = collector.collect(device.target)
            result = workflow.run(
                configuration,
                request.rules,
                device.device_id,
                request.requested_by,
                generate_plans=not request.manual_remediation,
            )
        except COLLECTION_ERRORS as error:
            with scenario_lock:
                inventory_store[device.device_id] = device.model_copy(
                    update={"status": "unreachable"}
                )
            results.append(
                BatchAuditItem(
                    device_id=device.device_id,
                    scenario_id=scenario_id,
                    status="failed",
                    detail=str(error),
                )
            )
            continue

        record = ScenarioRecord(
            scenario_id=scenario_id,
            configuration=configuration,
            target=device.target,
            rules=request.rules,
            workflow=result,
        )
        with scenario_lock:
            scenario_store[record.scenario_id] = record
            inventory_store[device.device_id] = device.model_copy(
                update={
                    "status": "reachable",
                    "last_audit_scenario_id": record.scenario_id,
                    "last_audit_status": result.status,
                }
            )
        results.append(
            BatchAuditItem(
                device_id=device.device_id,
                scenario_id=record.scenario_id,
                status="audited",
            )
        )

    return BatchAuditResult(
        audited_count=sum(item.status == "audited" for item in results),
        failed_count=sum(item.status == "failed" for item in results),
        results=results,
    )


@app.get("/scenarios/{scenario_id}/remediation-prompt")
def get_remediation_prompt(scenario_id: str):
    try:
        record = scenario_store[scenario_id]
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Unknown scenario") from error
    if not record.workflow.findings:
        raise HTTPException(status_code=409, detail="Scenario has no findings")
    finding = record.workflow.findings[0]
    rule = next(rule for rule in record.rules if rule.rule_id == finding.rule_id)
    return {
        "scenario_id": scenario_id,
        "finding": finding,
        "configuration_context": record.configuration,
        "allowed_scope": rule.allowed_scope,
        "output_schema": {
            "summary": "string",
            "commands": [
                {"sequence": "integer", "command": "string", "scope": "string"}
            ],
            "assumptions": ["string"],
        },
        "instruction": (
            "Return only JSON. Propose remediation commands within the allowed "
            "scope. Do not execute commands and do not include credentials."
        ),
    }


@app.post("/scenarios/{scenario_id}/remediation-response")
def submit_remediation_response(
    scenario_id: str,
    response: RemediationResponse,
):
    try:
        record = scenario_store[scenario_id]
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Unknown scenario") from error
    if record.workflow.approvals:
        raise HTTPException(status_code=409, detail="Remediation response already submitted")
    finding = record.workflow.findings[0] if record.workflow.findings else None
    if finding is None:
        raise HTTPException(status_code=409, detail="Scenario has no findings")
    rule = next(rule for rule in record.rules if rule.rule_id == finding.rule_id)
    try:
        from app.models.schemas import Command, ModelMetadata, RemediationPlan

        plan = RemediationPlan(
            plan_id=f"manual-plan-{scenario_id}",
            finding_id=finding.finding_id,
            summary=response.summary,
            commands=[Command.model_validate(command) for command in response.commands],
            assumptions=response.assumptions,
            model_metadata=ModelMetadata(
                provider="manual-chatbot",
                model="user-supplied",
                prompt_version="manual-v1",
            ),
        )
        validation = workflow.validator.validate(plan, finding)
        if not validation.valid:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Chatbot response failed guardrail validation",
                    "validation": validation.model_dump(),
                },
            )
        approval = approval_service.request(
            plan,
            finding,
            validation,
            requested_by="manual-chatbot-import",
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    updated_workflow = record.workflow.model_copy(
        update={
            "status": "approval_pending",
            "plans": [plan],
            "validations": [validation],
            "approvals": [approval],
        }
    )
    updated = record.model_copy(update={"workflow": updated_workflow})
    with scenario_lock:
        scenario_store[scenario_id] = updated
    return updated


@app.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: str):
    try:
        return scenario_store[scenario_id]
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Unknown scenario") from error


@app.post("/scenarios/execute-all")
def execute_all_scenarios() -> BatchExecutionResult:
    if executor is None:
        raise HTTPException(
            status_code=503,
            detail="Live execution is not configured for this API process",
        )

    with scenario_lock:
        records = list(scenario_store.values())

    results: list[BatchExecutionItem] = []
    for record in records:
        approvals = [
            approval_service.get(approval.approval_id)
            for approval in record.workflow.approvals
        ]
        if record.live is not None:
            results.append(
                BatchExecutionItem(
                    scenario_id=record.scenario_id,
                    device_id=record.target.device_id,
                    status="skipped",
                    detail="Scenario has already been executed",
                )
            )
            continue
        if not approvals:
            results.append(
                BatchExecutionItem(
                    scenario_id=record.scenario_id,
                    device_id=record.target.device_id,
                    status="skipped",
                    detail="No remediation approvals",
                )
            )
            continue
        if any(approval.status != "approved" for approval in approvals):
            results.append(
                BatchExecutionItem(
                    scenario_id=record.scenario_id,
                    device_id=record.target.device_id,
                    status="skipped",
                    detail="Waiting for all approvals",
                )
            )
            continue

        try:
            live = workflow.execute_approved(
                approvals,
                record.target,
                record.configuration,
                record.rules,
                executor,
            )
        except (*COLLECTION_ERRORS, PermissionError) as error:
            results.append(
                BatchExecutionItem(
                    scenario_id=record.scenario_id,
                    device_id=record.target.device_id,
                    status="failed",
                    detail=str(error),
                )
            )
            continue

        updated = record.model_copy(update={"live": live})
        with scenario_lock:
            scenario_store[record.scenario_id] = updated
        results.append(
            BatchExecutionItem(
                scenario_id=record.scenario_id,
                device_id=record.target.device_id,
                status="executed",
            )
        )

    return BatchExecutionResult(
        executed_count=sum(item.status == "executed" for item in results),
        skipped_count=sum(item.status == "skipped" for item in results),
        failed_count=sum(item.status == "failed" for item in results),
        results=results,
    )


@app.post("/scenarios/{scenario_id}/execute")
def execute_scenario(scenario_id: str):
    if executor is None:
        raise HTTPException(
            status_code=503,
            detail="Live execution is not configured for this API process",
        )
    try:
        record = scenario_store[scenario_id]
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Unknown scenario") from error
    approvals = [
        approval_service.get(approval.approval_id)
        for approval in record.workflow.approvals
    ]
    if not approvals or any(approval.status != "approved" for approval in approvals):
        raise HTTPException(
            status_code=409,
            detail="All scenario approvals must be approved before execution",
        )
    try:
        live = workflow.execute_approved(
            approvals,
            record.target,
            record.configuration,
            record.rules,
            executor,
        )
    except (*COLLECTION_ERRORS, PermissionError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    updated = record.model_copy(update={"live": live})
    with scenario_lock:
        scenario_store[scenario_id] = updated
    return updated