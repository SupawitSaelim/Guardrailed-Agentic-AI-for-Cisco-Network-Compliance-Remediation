from app.compliance import ComplianceEngine
from app.models import ComplianceRule
from app.reaudit import ReauditService


def make_rules() -> list[ComplianceRule]:
    return [
        ComplianceRule(
            rule_id="ntp-approved-server",
            version="1.0.0",
            description="NTP server must be approved",
            platform="cisco_ios",
            expected_state="ntp server 10.10.10.10",
            allowed_scope=["ntp"],
            ground_truth_commands=["ntp server 10.10.10.10"],
            severity="medium",
        ),
        ComplianceRule(
            rule_id="http-disabled",
            version="1.0.0",
            description="HTTP server must be disabled",
            platform="cisco_ios",
            expected_state="no ip http server",
            allowed_scope=["ip http"],
            ground_truth_commands=["no ip http server"],
            severity="medium",
        ),
    ]


def test_reaudit_reports_success_when_finding_is_fixed() -> None:
    engine = ComplianceEngine()
    rules = make_rules()
    before = engine.audit("ntp server 10.10.10.20\n", rules, "lab-router-01")
    after = engine.audit("ntp server 10.10.10.10\n", rules, "lab-router-01")

    result = ReauditService().compare(before, after)

    assert result.remediation_succeeded is True
    assert result.post_compliant is True
    assert result.unresolved_findings == []
    assert result.regression_findings == []


def test_reaudit_detects_a_new_regression() -> None:
    engine = ComplianceEngine()
    rules = make_rules()
    before = engine.audit(
        "ntp server 10.10.10.20\nno ip http server\n",
        rules,
        "lab-router-01",
    )
    after = engine.audit(
        "ntp server 10.10.10.10\nip http server\n",
        rules,
        "lab-router-01",
    )

    result = ReauditService().compare(before, after)

    assert result.remediation_succeeded is False
    assert [finding.rule_id for finding in result.regression_findings] == [
        "http-disabled"
    ]


def test_reaudit_detects_an_unresolved_finding() -> None:
    engine = ComplianceEngine()
    rules = make_rules()
    before = engine.audit("ntp server 10.10.10.20\n", rules, "lab-router-01")
    after = engine.audit("ntp server 10.10.10.20\n", rules, "lab-router-01")

    result = ReauditService().compare(before, after)

    assert result.remediation_succeeded is False
    assert [finding.rule_id for finding in result.unresolved_findings] == [
        "ntp-approved-server"
    ]