"""Contracts for inventory backends."""

from typing import Protocol

from app.domain.models import MockRouter


class DeviceRepository(Protocol):
    """Minimal inventory contract used by services and API dependencies."""

    def list_devices(self) -> list[MockRouter]:
        ...

    def get_device(self, device_name: str) -> MockRouter:
        ...
