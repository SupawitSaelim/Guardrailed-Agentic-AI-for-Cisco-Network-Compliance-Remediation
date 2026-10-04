import pytest

from app.collection import LabTarget, NetmikoCollector


class FakeConnection:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.disconnected = False

    def send_command(self, command: str) -> str:
        self.commands.append(command)
        return "ntp server 10.10.10.20\n"

    def disconnect(self) -> None:
        self.disconnected = True


def test_collector_reads_running_config_and_disconnects() -> None:
    fake_connection = FakeConnection()

    collector = NetmikoCollector(
        credential_provider=lambda target: {
            "username": "lab-readonly",
            "password": "not-persisted",
        },
        connection_factory=lambda **parameters: fake_connection,
    )

    configuration = collector.collect(
        LabTarget(
            device_id="lab-router-01",
            host="192.0.2.10",
            device_type="cisco_ios",
        )
    )

    assert configuration == "ntp server 10.10.10.20\n"
    assert fake_connection.commands == ["show running-config"]
    assert fake_connection.disconnected is True


def test_collector_passes_lab_connection_timeouts() -> None:
    captured: dict[str, object] = {}

    def connection_factory(**parameters):
        captured.update(parameters)
        return FakeConnection()

    collector = NetmikoCollector(
        credential_provider=lambda target: {"username": "lab-readonly", "password": "secret"},
        connection_factory=connection_factory,
    )
    collector.collect(
        LabTarget(device_id="lab-router-01", host="192.0.2.10", device_type="cisco_ios")
    )

    assert captured["conn_timeout"] == 10
    assert captured["auth_timeout"] == 10
    assert captured["banner_timeout"] == 15


def test_target_cannot_disable_lab_only_boundary() -> None:
    with pytest.raises(ValueError):
        LabTarget(
            device_id="production-router",
            host="198.51.100.10",
            device_type="cisco_ios",
            lab_only=False,
        )