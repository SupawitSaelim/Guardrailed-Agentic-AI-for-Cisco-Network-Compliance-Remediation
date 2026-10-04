"""Netmiko-based read-only collector with a lab-only target boundary."""

from collections.abc import Callable
from typing import Any, Literal

from netmiko import ConnectHandler
from pydantic import BaseModel, ConfigDict, Field


class LabTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1)
    host: str = Field(min_length=1)
    device_type: Literal["cisco_ios", "cisco_xe"]
    lab_only: Literal[True] = True


CredentialProvider = Callable[[LabTarget], dict[str, Any]]
ConnectionFactory = Callable[..., Any]


class NetmikoCollector:
    """Collect running configuration without exposing credentials to callers."""

    def __init__(
        self,
        credential_provider: CredentialProvider,
        connection_factory: ConnectionFactory = ConnectHandler,
    ) -> None:
        self.credential_provider = credential_provider
        self.connection_factory = connection_factory

    def collect(self, target: LabTarget) -> str:
        if target.lab_only is not True:
            raise ValueError("Only lab targets can be collected")

        connection_parameters = self.credential_provider(target)
        connection = self.connection_factory(
            device_type=target.device_type,
            host=target.host,
            ssh_strict=False,
            use_keys=False,
            allow_agent=False,
            conn_timeout=10,
            auth_timeout=10,
            banner_timeout=15,
            **connection_parameters,
        )
        try:
            return connection.send_command("show running-config")
        finally:
            connection.disconnect()