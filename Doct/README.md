# Guardrailed Agentic AI for Cisco Configuration Compliance

## Purpose

A laboratory-only prototype for auditing Cisco IOS/IOS XE configuration and generating controlled remediation plans with an LLM.

The LLM is a planner only. It has no credentials and no direct SSH access.

## Scope

- Cisco IOS/IOS XE virtual lab devices
- Deterministic compliance auditing
- Structured remediation plans
- Command and scope validation
- Human approval before execution
- Controlled Netmiko execution
- Post-check and re-audit
- Evaluation of correctness, safety, latency, token cost, and hallucination

## Out of scope

- Production devices or production configuration
- Direct LLM-to-device access
- BGP/OSPF policy changes
- Model training or fine-tuning
- Full dashboard, multi-agent orchestration, or local LLM as a required feature

## Planned documentation

- `requirements.md`: product and research requirements
- `architecture.md`: system boundaries and data flow
- `technical-design.md`: implementation modules and interfaces
- `data-schema.md`: data contracts
- `compliance-rules.md`: initial rules and ground truth
- `security-threat-model.md`: security controls and threats
- `test-plan.md`: software and lab verification
- `experiment-protocol.md`: research groups and metrics

Production configuration is not part of this documentation set. Use it only to derive sanitized policy patterns; keep raw configuration outside the repository.

## Development principles

1. The compliance engine is the source of truth for Pass/Fail.
2. Every LLM output is untrusted input.
3. Validation must happen before approval and execution.
4. Execution is allowed only in the virtual lab.
5. Every decision and command must be auditable.
