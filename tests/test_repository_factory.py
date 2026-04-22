import pytest

from app.domain.exceptions import InventoryBackendError
from app.store.factory import build_device_repository
from app.store.mock_inventory import MockInventoryRepository
from app.store.netbox_inventory import NetBoxInventoryRepository


def test_build_device_repository_returns_mock_backend_when_requested():
    repository = build_device_repository(backend="mock")

    assert isinstance(repository, MockInventoryRepository)
    assert len(repository.list_devices()) == 3


def test_build_device_repository_creates_netbox_adapter_when_credentials_are_present():
    repository = build_device_repository(
        backend="netbox",
        netbox_url="https://netbox.local",
        netbox_token="token-123",
    )

    assert isinstance(repository, NetBoxInventoryRepository)


def test_build_device_repository_rejects_netbox_without_credentials():
    with pytest.raises(InventoryBackendError, match="NAA_NETBOX_URL"):
        build_device_repository(backend="netbox")
