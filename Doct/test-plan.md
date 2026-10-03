# Test Plan

## 1. Unit tests

- Rule evaluation for compliant and non-compliant fixtures.
- Finding generation and allowed scope.
- RemediationPlan schema validation.
- Command blocklist and allowlist behavior.
- Scope violation detection.
- Maximum command count.
- Secret redaction.
- State transition rules.

## 2. Integration tests

- Fixture configuration to Finding.
- Finding to mock LLM plan.
- Plan to validation result.
- Approved plan to mocked executor.
- Post-check to re-audit.
- Audit artifact export.

## 3. Lab tests

- Single fault: NTP mismatch.
- Concurrent faults: HTTP, SSH, NTP, and Syslog.
- Out-of-scope trap: VTY SSH-only rule with unrelated `no login local` or `no exec-timeout`.
- Context-Deficit variants with controlled missing context.
- Execution failure and rollback or recovery behavior.
- Regression detection.

### Production-reference-derived synthetic tests

- AAA new-model and login lockout policy.
- SSH version, timeout, and authentication retry policy.
- NTP source interface and synthetic approved server.
- HTTP/HTTPS disablement and service timestamps.
- Syslog buffer and synthetic logging destination.
- VTY SSH-only transport and synthetic management ACL.
- BOOTP and source-route disablement.
- SNMP trap source using a synthetic loopback.

ACL semantics, SNMP community migration, IPsec/crypto policy, and routing behavior remain audit-only until reviewed by a network specialist.

## 4. Required negative tests

Every negative test must prove that execution is not reached.

- Invalid JSON.
- Missing required field.
- Unsafe command.
- Out-of-scope command.
- Unknown device.
- Missing approval.
- Changed pre-execution configuration.
- Production-like target.

## 5. Definition of done for a feature

- Test exists for normal behavior.
- Test exists for rejection behavior.
- Audit event is generated.
- No secret appears in output.
- `pytest` passes for the affected slice.
