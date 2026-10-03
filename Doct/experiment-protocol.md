# Experiment Protocol

## Research purpose

Measure how increasing deterministic guardrails affects remediation correctness, unsafe commands, scope violations, regressions, hallucination, latency, and token cost.

## Experimental groups

- Group A: LLM with prompt constraints only.
- Group B: Group A plus Structured JSON Validation.
- Group C: Group B plus Command and Scope Validation.
- Group D: Group C plus Human Approval, Post-check, and Re-audit.

Execution must remain inside the virtual lab. Group differences must be recorded precisely so that safety controls are not accidentally bypassed in real environments.

## Factors

- Guardrail group.
- Scenario complexity.
- Compliance rule.
- Context condition: Full Context or one defined Context-Deficit condition.
- Fixed model, model version, prompt version, temperature, and retry policy.

## Primary metrics

- Remediation Correctness.
- Unsafe Command Rate.
- Out-of-scope Change Rate.
- Regression Rate.
- Hallucination or False Positive Rate.
- Guardrail Blocker Efficiency.

## Secondary metrics

- Schema Failure Rate.
- Compliance Pass Rate.
- Human Correction Rate.
- Processing Time.
- Input/output token usage and estimated API cost.

## Run record

Each run must store:

- Scenario and rule versions.
- Context condition.
- Group and guardrails enabled.
- Model and prompt metadata.
- Raw response with secrets removed.
- Validation outcome.
- Approval outcome.
- Execution and re-audit outcome.
- Error category.
- Timing and token usage.

## Pilot before final experiment

The pilot must verify that:

1. Ground truth is unambiguous.
2. Rules detect the intended faults.
3. Validators distinguish safe, unsafe, and out-of-scope commands.
4. Metrics can be calculated from stored records.
5. Context-Deficit conditions remove only the intended information.

Production-reference-derived rules must use synthetic Lab values. High-impact domains such as ACL behavior, IPsec/crypto, SNMP community migration, and routing are audit-only during the pilot and must not reach execution.

Final scenario counts, repetitions, and statistical tests must be fixed after the pilot and reviewed with the advisor.
