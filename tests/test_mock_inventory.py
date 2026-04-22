import pytest

from app.domain.exceptions import DeviceNotFoundError
from app.services.device_service import DeviceService
from app.store.mock_inventory import MockInventoryRepository


def test_list_mock_devices_returns_seeded_inventory():
    service = DeviceService(repository=MockInventoryRepository())

    devices = service.list_devices()

    assert len(devices) == 3
    assert devices[0].name == "lab-r1"
    assert devices[1].role == "distribution"


def test_get_unknown_mock_device_raises_not_found():
    service = DeviceService(repository=MockInventoryRepository())

    with pytest.raises(DeviceNotFoundError, match="lab-r99"):
        service.get_device("lab-r99")
