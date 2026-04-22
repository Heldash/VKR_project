import httpx
import pytest

from app.domain.exceptions import DeviceNotFoundError, InventoryBackendError
from app.store.netbox_inventory import NetBoxInventoryRepository


@pytest.fixture
def netbox_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/dcim/devices/" and request.url.params.get("name") == "edge-r1":
            return httpx.Response(
                200,
                json={
                    "count": 1,
                    "next": None,
                    "previous": None,
                    "results": [
                        {
                            "id": 101,
                            "name": "edge-r1",
                            "platform": {"slug": "cisco_ios"},
                            "device_type": {
                                "manufacturer": {"name": "Cisco"}
                            },
                            "role": {"slug": "core-router"},
                            "site": {"slug": "msk-lab"},
                            "status": {"value": "active"},
                            "primary_ip4": {"address": "192.0.2.10/24"},
                        }
                    ],
                },
            )
        if request.url.path == "/api/dcim/devices/" and request.url.params.get("limit") == "100":
            return httpx.Response(
                200,
                json={
                    "count": 1,
                    "next": None,
                    "previous": None,
                    "results": [
                        {
                            "id": 101,
                            "name": "edge-r1",
                            "platform": {"slug": "cisco_ios"},
                            "device_type": {
                                "manufacturer": {"name": "Cisco"}
                            },
                            "role": {"slug": "distribution-router"},
                            "site": {"slug": "msk-lab"},
                            "status": {"value": "active"},
                            "primary_ip4": {"address": "192.0.2.10/24"},
                        }
                    ],
                },
            )
        if request.url.path == "/api/dcim/interfaces/" and request.url.params.get("device_id") == "101":
            return httpx.Response(
                200,
                json={
                    "count": 2,
                    "next": None,
                    "previous": None,
                    "results": [
                        {
                            "name": "GigabitEthernet0/0",
                            "description": "WAN uplink",
                            "enabled": True,
                        },
                        {
                            "name": "GigabitEthernet0/1",
                            "description": "LAN",
                            "enabled": False,
                        },
                    ],
                },
            )
        return httpx.Response(404, json={"detail": "Not found"})

    return httpx.MockTransport(handler)


def build_repository(transport: httpx.MockTransport) -> NetBoxInventoryRepository:
    client = httpx.Client(
        transport=transport,
        base_url="https://netbox.local/api/",
        headers={"Authorization": "Token token-123"},
    )
    return NetBoxInventoryRepository(
        base_url="https://netbox.local",
        token="token-123",
        client=client,
    )


def test_list_devices_maps_netbox_payload(netbox_transport: httpx.MockTransport):
    repository = build_repository(netbox_transport)

    devices = repository.list_devices()

    assert len(devices) == 1
    assert devices[0].name == "edge-r1"
    assert devices[0].platform == "cisco_ios"
    assert devices[0].vendor == "Cisco"
    assert devices[0].role == "distribution"
    assert devices[0].management_ip == "192.0.2.10"
    assert devices[0].interfaces[1].enabled is False


def test_get_device_uses_name_filter(netbox_transport: httpx.MockTransport):
    repository = build_repository(netbox_transport)

    device = repository.get_device("edge-r1")

    assert device.name == "edge-r1"
    assert device.role == "core"
    assert device.status == "reachable"
    assert device.site == "msk-lab"


def test_get_device_raises_not_found_when_netbox_returns_empty_result():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"count": 0, "next": None, "previous": None, "results": []},
        )
    )
    repository = build_repository(transport)

    with pytest.raises(DeviceNotFoundError, match="lab-r99"):
        repository.get_device("lab-r99")


def test_list_devices_wraps_http_errors_as_inventory_backend_error():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(500, json={"detail": "Server error"})
    )
    repository = build_repository(transport)

    with pytest.raises(InventoryBackendError, match="HTTP 500"):
        repository.list_devices()
