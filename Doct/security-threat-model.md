# Security and Threat Model

## Security objectives

1. Prevent unsafe or unrelated commands from reaching a device.
2. Keep credentials and sensitive configuration away from the LLM.
3. Ensure every write operation has human approval.
4. Preserve enough evidence to reconstruct each experiment.
5. Make production execution technically unavailable.

## Threats and controls

| Threat | Control |
|---|---|
| LLM invents an interface, IP, or neighbor | Bounded context, schema validation, scope validation, lab re-audit |
| LLM emits a destructive command | Blocklist, allowlist, command parser, fail-closed behavior |
| LLM changes unrelated configuration | Allowed scope and maximum command limit |
| Prompt injection in configuration text | Treat device text as data, fixed system policy, no tool access |
| Credential leakage | Separate credentials, secret redaction, no secrets in prompts or logs |
| Approval bypass | Approval is required after validation and before execution |
| Wrong target device | Lab inventory allowlist and environment assertion |
| Configuration changes between analysis and execution | Pre-execution snapshot/hash and revalidation |
| Regression after remediation | Post-check and full re-audit |
| Tampered audit record | Append-only event design or integrity hash |

## Credential separation

- Audit credential: read-only collection.
- Remediation credential: write access to lab targets only.
- LLM provider credential: API access only; never sent to the model.

## Security acceptance checks

- Production hostname or address is rejected.
- Missing lab environment marker is rejected.
- Any command not explicitly accepted by policy is rejected.
- Approval identity and timestamp are recorded.
- Logs contain no password, token, secret, or private key.

## Production reference handling

- Production configuration is reference material only and is not a test fixture.
- Keep the raw file outside the repository and outside LLM context.
- Derive only abstract policy patterns and manually create sanitized Lab fixtures.
- Replace private IPs, domains, usernames, device names, community strings, key strings, and certificate details.
- Treat type 7 passwords and obfuscated secrets as exposed secrets, not as anonymized data.
- If the raw file was previously shared or committed, review rotation of affected credentials, keys, and communities.
