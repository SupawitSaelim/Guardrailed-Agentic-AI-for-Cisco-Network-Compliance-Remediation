# Initial Compliance Rules

All rules must have deterministic evaluation logic, a version, a fixture set, and a reviewed ground truth.

| Rule ID | Requirement | Allowed scope | Initial ground truth |
|---|---|---|---|
| `ntp-approved-server` | Approved NTP server is `10.10.10.10` | `ntp` | Remove old server and add approved server |
| `http-disabled` | HTTP server is disabled | `ip http` | `no ip http server` |
| `ssh-v2` | SSH version is 2 | `ip ssh` | `ip ssh version 2` |
| `syslog-approved-host` | Syslog host is `192.168.1.100` | `logging` | Remove old host and add approved host |
| `vty-ssh-only` | VTY transport accepts SSH only | `line vty`, `transport input` | `transport input ssh` |
| `ntp-source-interface` | NTP uses the approved source interface | `ntp` | `ntp source Loopback99` |
| `https-disabled` | HTTPS server is disabled when not required | `ip http` | `no ip http secure-server` |
| `ssh-authentication-retries` | SSH retries match policy | `ip ssh` | `ip ssh authentication-retries 2` |
| `ssh-timeout` | SSH timeout matches policy | `ip ssh` | `ip ssh time-out 60` |
| `syslog-buffered` | Buffered logging meets policy | `logging` | `logging buffered 64000` |
| `vty-access-class` | Every VTY range has the approved management ACL | `line vty` | `access-class MGMT-ACL in` |
| `aaa-new-model` | AAA processing is enabled | `aaa` | `aaa new-model` |
| `login-block-for` | Login lockout policy is configured | `login` | `login block-for 300 attempts 6 within 300` |
| `no-ip-source-route` | IP source routing is disabled | `ip source-route` | `no ip source-route` |
| `no-ip-bootp-server` | BOOTP server is disabled | `ip bootp` | `no ip bootp server` |
| `service-timestamps` | Debug and log timestamps meet policy | `service timestamps` | Policy-defined timestamp lines |
| `snmp-trap-source-interface` | SNMP traps use the approved source interface | `snmp` | `snmp-server trap-source Loopback99` |

## Synthetic lab values

Production configuration may be used only to identify policy patterns. All test values must be replaced with synthetic values such as:

- NTP: `192.0.2.10` and `192.0.2.11`
- Syslog: `192.0.2.20` and `192.0.2.21`
- Management subnet: `198.51.100.0/24`
- Device domain: `lab.example.invalid`
- Source interface: `Loopback99`

Do not place production IP addresses, domains, usernames, secrets, key strings, SNMP communities, or topology descriptions in fixtures, prompts, tests, or audit logs.

## Enforcement classes

- **Remediation-eligible:** NTP source, HTTP/HTTPS disablement, SSH settings, Syslog buffer, AAA hardening, login lockout, source-route/BOOTP disablement, timestamps, and VTY access class after validation.
- **Audit-only initially:** ACL semantics/ordering, SNMP community migration, interface ACL attachment, IPsec/crypto policy, and routing behavior. These require human review because an incorrect change can interrupt network services.

## Rule contract

Each rule must define:

- `rule_id`
- `version`
- `description`
- `platform`
- `check`
- `expected_state`
- `allowed_scope`
- `ground_truth_commands`
- `blocked_commands`
- `severity`

## Safety rules

The initial validator must reject, at minimum:

- `reload`
- `write erase`
- `erase startup-config`
- `format`
- `delete`
- `configure replace`
- interface shutdown commands
- commands outside the finding scope

The exact command policy must be reviewed against the selected IOS/IOS XE version before lab execution.
