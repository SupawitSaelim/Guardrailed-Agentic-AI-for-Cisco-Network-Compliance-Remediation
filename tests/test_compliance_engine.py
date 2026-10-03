import pytest

from app.compliance import ComplianceEngine
from app.models import ComplianceRule


def make_ntp_rule() -> ComplianceRule:
    return ComplianceRule(
        rule_id="ntp-approved-server",
        version="1.0.0",
        description="NTP server must be approved",
        platform="cisco_ios",
        expected_state="ntp server 10.10.10.10",
        allowed_scope=["ntp"],
        ground_truth_commands=[
            "no ntp server 10.10.10.20",
            "ntp server 10.10.10.10",
        ],
        severity="medium",
    )


def make_rule(
    rule_id: str,
    expected_state: str,
    allowed_scope: str,
) -> ComplianceRule:
    return ComplianceRule(
        rule_id=rule_id,
        version="1.0.0",
        description=f"Test rule for {rule_id}",
        platform="cisco_ios",
        expected_state=expected_state,
        allowed_scope=[allowed_scope],
        ground_truth_commands=[expected_state],
        severity="medium",
    )


def test_ntp_mismatch_creates_finding() -> None:
    result = ComplianceEngine().audit(
        "ntp server 10.10.10.20\n",
        [make_ntp_rule()],
        "lab-router-01",
    )

    assert result.compliant is False
    assert len(result.findings) == 1
    assert result.findings[0].actual == ["ntp server 10.10.10.20"]


def test_ntp_match_is_compliant() -> None:
    result = ComplianceEngine().audit(
        "ntp server 10.10.10.10\n",
        [make_ntp_rule()],
        "lab-router-01",
    )

    assert result.compliant is True
    assert result.findings == []


def test_unknown_rule_is_rejected() -> None:
    rule = make_ntp_rule().model_copy(update={"rule_id": "unknown-rule"})

    with pytest.raises(ValueError, match="Unsupported compliance rule"):
        ComplianceEngine().audit("", [rule], "lab-router-01")


@pytest.mark.parametrize(
    ("rule", "configuration", "expected_compliant"),
    [
        (
            make_rule("http-disabled", "no ip http server", "ip http"),
            "ip http server\n",
            False,
        ),
        (
            make_rule("ssh-v2", "ip ssh version 2", "ip ssh"),
            "ip ssh version 1\n",
            False,
        ),
        (
            make_rule("syslog-approved-host", "logging host 192.168.1.100", "logging"),
            "logging host 192.168.1.50\n",
            False,
        ),
        (
            make_rule("vty-ssh-only", "transport input ssh", "line vty"),
            "line vty 0 4\n transport input ssh telnet\n",
            False,
        ),
        (
            make_rule("http-disabled", "no ip http server", "ip http"),
            "no ip http server\n",
            True,
        ),
        (
            make_rule("ssh-v2", "ip ssh version 2", "ip ssh"),
            "ip ssh version 2\n",
            True,
        ),
        (
            make_rule("syslog-approved-host", "logging host 192.168.1.100", "logging"),
            "logging host 192.168.1.100\n",
            True,
        ),
        (
            make_rule("vty-ssh-only", "transport input ssh", "line vty"),
            "line vty 0 4\n transport input ssh\n",
            True,
        ),
    ],
)
def test_initial_rules_match_expected_state(
    rule: ComplianceRule,
    configuration: str,
    expected_compliant: bool,
) -> None:
    result = ComplianceEngine().audit(configuration, [rule], "lab-router-01")

    assert result.compliant is expected_compliant