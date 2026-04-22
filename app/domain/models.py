"""Core entities used by the application."""

from ipaddress import ip_interface
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class InterfaceSpec(BaseModel):
    """Represents a mocked network interface."""

    name: str
    description: str
    ipv4_address: str | None = None
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Interface name must not be empty")
        return normalized

    @field_validator("ipv4_address")
    @classmethod
    def validate_ipv4_address(cls, value: str | None) -> str | None:
        if value is None:
            return value
        ip_interface(value)
        return value


class MockRouter(BaseModel):
    """Represents a test router from the in-memory lab inventory."""

    name: str
    hostname: str
    platform: str
    vendor: str
    role: Literal["edge", "core", "distribution"]
    site: str
    management_ip: str
    port: int = 22
    username: str = Field(default="lab", repr=False)
    password: str = Field(default="lab", repr=False)
    secret: str | None = Field(default=None, repr=False)
    status: Literal["reachable", "maintenance"] = "reachable"
    interfaces: list[InterfaceSpec]
