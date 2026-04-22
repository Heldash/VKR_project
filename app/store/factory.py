"""Factory functions for selecting inventory backends."""

from typing import Literal

from app.core.config import settings
from app.domain.exceptions import InventoryBackendError
from app.store.contracts import DeviceRepository
from app.store.mock_inventory import MockInventoryRepository
from app.store.netbox_inventory import NetBoxInventoryRepository

InventoryBackend = Literal["mock", "netbox"]


def build_device_repository(
    backend: InventoryBackend | None = None,
    netbox_url: str | None = None,
    netbox_token: str | None = None,
) -> DeviceRepository:
    """Builds the inventory adapter selected for the current environment."""

    selected_backend = backend or settings.inventory_backend
    if selected_backend == "mock":
        return MockInventoryRepository()
    if selected_backend == "netbox":
        return NetBoxInventoryRepository(
            base_url=netbox_url or settings.netbox_url,
            token=netbox_token or settings.netbox_token,
        )
    raise InventoryBackendError(
        f"Unsupported inventory backend '{selected_backend}'"
    )
