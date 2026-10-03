"""Deterministic compliance evaluation for the initial Cisco rules."""

import re
from collections.abc import Callable

from app.models import AuditResult, ComplianceRule, Finding


RuleCheck = Callable[[str, ComplianceRule], tuple[bool, list[str]]]


class ComplianceEngine:
    """Evaluate Cisco configuration without using an LLM."""

    def __init__(self) -> None:
        self._checks: dict[str, RuleCheck] = {
            "ntp-approved-server": self._check_ntp,
            "ntp-source-interface": self._check_ntp_source,
            "http-disabled": self._check_http_disabled,
            "https-disabled": self._check_https_disabled,
            "ssh-v2": self._check_ssh_v2,
            "ssh-authentication-retries": self._check_ssh_authentication_retries,
            "ssh-timeout": self._check_ssh_timeout,
            "syslog-approved-host": self._check_syslog,
            "syslog-buffered": self._check_syslog_buffered,
            "vty-ssh-only": self._check_vty_ssh_only,
            "vty-access-class": self._check_vty_access_class,
            "aaa-new-model": self._check_aaa_new_model,
            "login-block-for": self._check_login_block_for,
            "no-ip-source-route": self._check_no_ip_source_route,
            "no-ip-bootp-server": self._check_no_ip_bootp_server,
            "service-timestamps": self._check_service_timestamps,
            "snmp-trap-source-interface": self._check_snmp_trap_source,
        }

    def audit(
        self,
        configuration: str,
        rules: list[ComplianceRule],
        device_id: str,
    ) -> AuditResult:
        """Return deterministic findings for all supplied rules."""
        findings: list[Finding] = []

        for rule in rules:
            check = self._checks.get(rule.rule_id)
            if check is None:
                raise ValueError(f"Unsupported compliance rule: {rule.rule_id}")

            compliant, evidence = check(configuration, rule)
            if not compliant:
                findings.append(
                    Finding(
                        finding_id=f"{device_id}:{rule.rule_id}",
                        device_id=device_id,
                        rule_id=rule.rule_id,
                        severity=rule.severity,
                        expected=rule.expected_state,
                        actual=evidence,
                        evidence=evidence,
                        allowed_scope=rule.allowed_scope,
                        rule_version=rule.version,
                        enforcement=rule.enforcement,
                    )
                )

        rule_versions = {rule.version for rule in rules}
        if len(rule_versions) != 1:
            raise ValueError("All rules in one audit must use the same version")

        return AuditResult(
            device_id=device_id,
            compliant=not findings,
            findings=findings,
            rule_version=rule_versions.pop(),
            evaluated_rule_ids=[rule.rule_id for rule in rules],
        )

    @staticmethod
    def _check_ntp(configuration: str, rule: ComplianceRule) -> tuple[bool, list[str]]:
        configured_servers = re.findall(r"^ntp server\s+(\S+)", configuration, re.MULTILINE)
        expected_server = _value_from_expected(rule.expected_state, "ntp server")
        evidence = [f"ntp server {server}" for server in configured_servers]
        return configured_servers == [expected_server], evidence

    @staticmethod
    def _check_ntp_source(configuration: str, rule: ComplianceRule) -> tuple[bool, list[str]]:
        return _check_exact_line(configuration, rule.expected_state, "ntp source")

    @staticmethod
    def _check_http_disabled(configuration: str, _rule: ComplianceRule) -> tuple[bool, list[str]]:
        evidence = re.findall(r"^ip http server$", configuration, re.MULTILINE)
        return not evidence, evidence

    @staticmethod
    def _check_https_disabled(configuration: str, _rule: ComplianceRule) -> tuple[bool, list[str]]:
        evidence = re.findall(r"^ip http secure-server$", configuration, re.MULTILINE)
        return not evidence, evidence

    @staticmethod
    def _check_ssh_v2(configuration: str, _rule: ComplianceRule) -> tuple[bool, list[str]]:
        evidence = re.findall(r"^ip ssh version\s+\S+$", configuration, re.MULTILINE)
        return "ip ssh version 2" in evidence, evidence

    @staticmethod
    def _check_ssh_authentication_retries(
        configuration: str, rule: ComplianceRule
    ) -> tuple[bool, list[str]]:
        return _check_exact_line(
            configuration,
            rule.expected_state,
            "ip ssh authentication-retries",
        )

    @staticmethod
    def _check_ssh_timeout(configuration: str, rule: ComplianceRule) -> tuple[bool, list[str]]:
        return _check_exact_line(configuration, rule.expected_state, "ip ssh time-out")

    @staticmethod
    def _check_syslog(configuration: str, rule: ComplianceRule) -> tuple[bool, list[str]]:
        configured_hosts = re.findall(r"^logging host\s+(\S+)", configuration, re.MULTILINE)
        expected_host = _value_from_expected(rule.expected_state, "logging host")
        evidence = [f"logging host {host}" for host in configured_hosts]
        return configured_hosts == [expected_host], evidence

    @staticmethod
    def _check_syslog_buffered(configuration: str, rule: ComplianceRule) -> tuple[bool, list[str]]:
        return _check_exact_line(configuration, rule.expected_state, "logging buffered")

    @staticmethod
    def _check_vty_ssh_only(configuration: str, _rule: ComplianceRule) -> tuple[bool, list[str]]:
        transport_lines = re.findall(r"^\s+transport input\s+.+$", configuration, re.MULTILINE)
        evidence = [line.strip() for line in transport_lines]
        return evidence == ["transport input ssh"], evidence

    @staticmethod
    def _check_vty_access_class(configuration: str, rule: ComplianceRule) -> tuple[bool, list[str]]:
        blocks = re.findall(
            r"^line vty[^\n]*\n(.*?)(?=^line |^!|\Z)",
            configuration,
            re.MULTILINE | re.DOTALL,
        )
        expected = rule.expected_state.strip()
        evidence = [
            line.strip()
            for block in blocks
            for line in block.splitlines()
            if "access-class" in line
        ]
        return bool(blocks) and all(expected in block for block in blocks), evidence

    @staticmethod
    def _check_aaa_new_model(configuration: str, _rule: ComplianceRule) -> tuple[bool, list[str]]:
        evidence = re.findall(r"^aaa new-model$", configuration, re.MULTILINE)
        return bool(evidence), evidence

    @staticmethod
    def _check_login_block_for(configuration: str, rule: ComplianceRule) -> tuple[bool, list[str]]:
        return _check_exact_line(configuration, rule.expected_state, "login block-for")

    @staticmethod
    def _check_no_ip_source_route(configuration: str, _rule: ComplianceRule) -> tuple[bool, list[str]]:
        evidence = re.findall(r"^ip source-route$", configuration, re.MULTILINE)
        return not evidence, evidence

    @staticmethod
    def _check_no_ip_bootp_server(configuration: str, _rule: ComplianceRule) -> tuple[bool, list[str]]:
        evidence = re.findall(r"^ip bootp server$", configuration, re.MULTILINE)
        return not evidence, evidence

    @staticmethod
    def _check_service_timestamps(configuration: str, _rule: ComplianceRule) -> tuple[bool, list[str]]:
        required = (
            "service timestamps debug datetime msec localtime",
            "service timestamps log datetime msec localtime show-timezone year",
        )
        evidence = [line for line in required if line not in configuration]
        return not evidence, evidence

    @staticmethod
    def _check_snmp_trap_source(configuration: str, rule: ComplianceRule) -> tuple[bool, list[str]]:
        return _check_exact_line(configuration, rule.expected_state, "snmp-server trap-source")


def _value_from_expected(expected_state: str, prefix: str) -> str:
    value = expected_state.removeprefix(prefix).strip()
    if not value:
        raise ValueError(f"Expected state must contain a value after '{prefix}'")
    return value


def _check_exact_line(
    configuration: str,
    expected_state: str,
    prefix: str,
) -> tuple[bool, list[str]]:
    expected_line = expected_state.strip()
    if not expected_line.startswith(prefix):
        raise ValueError(f"Expected state must start with '{prefix}'")
    evidence = re.findall(rf"^{re.escape(prefix)}.*$", configuration, re.MULTILINE)
    return evidence == [expected_line], evidence