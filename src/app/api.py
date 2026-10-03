"""FastAPI transport for the approval workflow."""

from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.approval import ApprovalService
from app.models import Finding, RemediationPlan, ValidationResult


app = FastAPI(title="Guardrailed Cisco Compliance API", version="0.1.0")
approval_service = ApprovalService()


class ApprovalRequest(BaseModel):
    plan: RemediationPlan
    finding: Finding
    validation: ValidationResult
    requested_by: str = Field(min_length=1)


class DecisionRequest(BaseModel):
    decided_by: str = Field(min_length=1)
    reason: str | None = None


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