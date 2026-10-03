import pytest

from app.compliance import ComplianceEngine
from app.models import ComplianceRule


def make_rule(rule_id: str, expected_state: str) -> ComplianceRule:
    return ComplianceRule(
        rule_id=rule_id,
        version="1.1.0",
        description=f"Synthetic lab rule for {rule_id}",
        platform="cisco_ios",
        expected_state=expected_state,
        allowed_scope=[rule_id],
        ground_truth_commands=[expected_state],
        severity="medium",
    )


@pytest.mark.parametrize(
    ("rule", "configuration", "expected_compliant"),
    [
        (
            make_rule("aaa-new-model", "aaa new-model"),
            "aaa new-model\n",
            True,
        ),
        (
            make_rule("login-block-for", "login block-for 300 attempts 6 within 300"),
            "login block-for 300 attempts 6 within 300\n",
            True,
        ),
        (
            make_rule("ntp-source-interface", "ntp source Loopback99"),
            "ntp source GigabitEthernet0/0\n",
            False,
        ),
        (
            make_rule("https-disabled", "no ip http secure-server"),
            "ip http secure-server\n",
            False,
        ),
        (
            make_rule("ssh-authentication-retries", "ip ssh authentication-retries 2"),
            "ip ssh authentication-retries 3\n",
            False,
        ),
        (
            make_rule("ssh-timeout", "ip ssh time-out 60"),
            "ip ssh time-out 60\n",
            True,
        ),
        (
            make_rule("syslog-buffered", "logging buffered 64000"),
            "logging buffered 32000\n",
            False,
        ),
        (
            make_rule("vty-access-class", "access-class MGMT-ACL in"),
            "line vty 0 4\n access-class MGMT-ACL in\n transport input ssh\n!\n"
            "line vty 5 15\n access-class MGMT-ACL in\n transport input ssh\n!\n",
            True,
        ),
        (
            make_rule("no-ip-source-route", "no ip source-route"),
            "ip source-route\n",
            False,
        ),
        (
            make_rule("no-ip-bootp-server", "no ip bootp server"),
            "no ip bootp server\n",
            True,
        ),
        (
            make_rule("service-timestamps", "policy-defined"),
            "service timestamps debug datetime msec localtime\n"
            "service timestamps log datetime msec localtime show-timezone year\n",
            True,
        ),
        (
            make_rule("snmp-trap-source-interface", "snmp-server trap-source Loopback99"),
            "snmp-server trap-source Loopback1\n",
            False,
        ),
    ],
)
def test_synthetic_production_reference_rules(
    rule: ComplianceRule,
    configuration: str,
    expected_compliant: bool,
) -> None:
    result = ComplianceEngine().audit(configuration, [rule], "lab-router-01")

    assert result.compliant is expected_compliant