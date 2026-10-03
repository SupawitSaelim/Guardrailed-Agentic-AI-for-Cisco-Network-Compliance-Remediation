# Guardrailed Agentic AI for Cisco Configuration Compliance

Laboratory-only prototype for auditing Cisco IOS/IOS XE configuration and
proposing controlled remediation plans. The compliance engine is deterministic;
an LLM, when used, is only an untrusted planner and never receives device
credentials or direct device access.

## What is implemented

- Pydantic contracts for findings, remediation plans, validation, approvals,
  execution, and re-audit results
- Deterministic compliance checks for Cisco configuration text
- Command and scope validation with fail-closed behavior
- Human approval service and audit trail
- FastAPI approval API
- CLI for listing and inspecting approval requests
- Replaceable mock/LLM planner interfaces
- React + TypeScript frontend under `web/`
- Unit and API tests under `tests/`

The current milestone focuses on the control-plane workflow. Device collection,
execution, and post-check integrations remain laboratory-oriented components.

## Architecture

```text
Configuration
    |
    v
Deterministic Compliance Engine -> Finding
    |
    v
Planner (LLM or mock) -> Remediation Plan
    |
    v
Plan + Command/Scope Validation
    |
    v
Human Approval -> Controlled Lab Execution -> Re-audit
    |
    v
Audit Trail and Evaluation Metrics
```

The system must fail closed when input is incomplete, unsafe, out of scope, or
target information does not match the registered lab environment.

## Repository layout

```text
src/app/       Python application modules
tests/         Python unit and API tests
web/           React + TypeScript frontend
Doct/          Requirements, architecture, design, security, and test docs
```

## Requirements

- Python 3.11+
- Node.js and npm (for the frontend)

## Python setup

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run the test suite:

```bash
pytest
```

Start the FastAPI service:

```bash
uvicorn app.api:app --app-dir src --reload
```

The API is available at `http://127.0.0.1:8000`. Interactive OpenAPI
documentation is available at `/docs`.

Scenario endpoints used by the control-plane prototype:

```text
POST /scenarios/audit
GET  /scenarios/{scenario_id}
POST /scenarios/{scenario_id}/execute
POST /devices
GET  /devices
POST /devices/{device_id}/audit
```

`/scenarios/audit` accepts a sanitized Lab configuration and versioned rules,
then returns the findings, validated plans, and approval records. Execution is
fail-closed: every generated approval must be approved and the API process must
be configured with a Lab-only `ControlledExecutor`. Execution captures one
pre-check/post-check pair for the scenario and returns the re-audit result.

The Devices page accepts the lab username, password, and optional enable
secret, but the backend stores them only in process memory. They are never
returned by the inventory endpoints or displayed in the table. Restarting the
API clears all credentials, so devices must be registered again before a live
audit. The backend collects `show running-config` before starting the same
audit and approval workflow. Remediation execution remains separately gated
and lab-only.

The approval CLI can be run with:

```bash
PYTHONPATH=src python -m app.cli list
PYTHONPATH=src python -m app.cli get <approval-id>
```

## Frontend setup

```bash
cd web
npm install
npm run dev
```

For a production build:

```bash
npm run build
npm run lint
```

## Safety boundaries

- Cisco IOS/IOS XE virtual lab devices only.
- The compliance engine, not the LLM, is the source of truth for Pass/Fail.
- Every LLM output is treated as untrusted input.
- Validation is required before approval and execution.
- Execution requires explicit human approval and an approved lab target.
- Every decision and command must be auditable.
- Production configuration and credentials must stay outside this repository.

## Documentation

- [`Doct/requirements.md`](Doct/requirements.md): product and research requirements
- [`Doct/architecture.md`](Doct/architecture.md): system boundaries and data flow
- [`Doct/technical-design.md`](Doct/technical-design.md): modules and interfaces
- [`Doct/data-schema.md`](Doct/data-schema.md): data contracts
- [`Doct/compliance-rules.md`](Doct/compliance-rules.md): initial rules and ground truth
- [`Doct/security-threat-model.md`](Doct/security-threat-model.md): threats and controls
- [`Doct/test-plan.md`](Doct/test-plan.md): software and lab verification
- [`Doct/experiment-protocol.md`](Doct/experiment-protocol.md): research groups and metrics

## Scope

- Cisco IOS/IOS XE virtual lab devices
- Deterministic compliance auditing
- Structured remediation plans
- Command and scope validation
- Human approval before execution
- Controlled Netmiko execution
- Post-check and re-audit
- Evaluation of correctness, safety, latency, token cost, and hallucination

Out of scope are production devices or production configuration, direct
LLM-to-device access, BGP/OSPF policy changes, model training or fine-tuning,
and requiring a local LLM.

## Development principles

1. The compliance engine is the source of truth for Pass/Fail.
2. Every LLM output is untrusted input.
3. Validation must happen before approval and execution.
4. Execution is allowed only in the virtual lab.
5. Every decision and command must be auditable.
