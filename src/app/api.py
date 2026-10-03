"""FastAPI transport for the approval workflow."""

from typing import Literal
from threading import Lock

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.approval import ApprovalService
from app.collection import LabTarget, NetmikoCollector
from app.execution import ControlledExecutor
from app.llm import MockLLMProvider
from app.models import ComplianceRule, Finding, RemediationPlan, ValidationResult
from app.workflow import WorkflowOrchestrator, WorkflowResult, LiveWorkflowResult


app = FastAPI(title="Guardrailed Cisco Compliance API", version="0.1.0")
approval_service = ApprovalService()
workflow = WorkflowOrchestrator(MockLLMProvider(), approval_service=approval_service)
executor: ControlledExecutor | None = None
scenario_store: dict[str, "ScenarioRecord"] = {}
inventory_store: dict[str, "InventoryRecord"] = {}
credential_store: dict[str, dict[str, str]] = {}
scenario_lock = Lock()


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


class DeviceRequest(BaseModel):
    device_id: str = Field(min_length=1)
    host: str = Field(min_length=1)
    device_type: Literal["cisco_ios", "cisco_xe"]
    credential_profile: str = Field(min_length=1)
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)
    secret: str = ""


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


class ScenarioRecord(BaseModel):
    scenario_id: str
    configuration: str
    target: LabTarget
    rules: list[ComplianceRule]
    workflow: WorkflowResult
    live: LiveWorkflowResult | None = None


def _credential_provider(target: LabTarget) -> dict[str, str]:
    credentials = credential_store.get(target.device_id)
    if credentials is None:
        raise RuntimeError(
            f"Credentials are not configured for inventory device {target.device_id}"
        )
    return credentials


collector = NetmikoCollector(_credential_provider)


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
        credential_store[record.device_id] = {
            "username": request.username,
            "password": request.password,
            "secret": request.secret,
        }
    return record


@app.get("/devices")
def list_devices():
    with scenario_lock:
        return list(inventory_store.values())


@app.get("/devices/{device_id}")
def get_device(device_id: str):
    try:
        return inventory_store[device_id]
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Unknown inventory device") from error


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
        )
    except (RuntimeError, ValueError, OSError) as error:
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


@app.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: str):
    try:
        return scenario_store[scenario_id]
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Unknown scenario") from error


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
    except (PermissionError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    updated = record.model_copy(update={"live": live})
    with scenario_lock:
        scenario_store[scenario_id] = updated
    return updated