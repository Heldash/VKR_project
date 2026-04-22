"""In-memory mock inventory for test routers."""

from app.domain.exceptions import DeviceNotFoundError
from app.domain.models import InterfaceSpec, MockRouter


MOCK_ROUTERS: tuple[MockRouter, ...] = (
    MockRouter(
        name="lab-r1",
        hostname="R1",
        platform="cisco_ios",
        vendor="Cisco",
        role="edge",
        site="msk-lab",
        management_ip="192.0.2.11",
        interfaces=[
            InterfaceSpec(
                name="GigabitEthernet0/0",
                description="Uplink to ISP",
                ipv4_address="198.51.100.1/30",
            ),
            InterfaceSpec(
                name="GigabitEthernet0/1",
                description="LAN segment A",
                ipv4_address="10.10.10.1/24",
            ),
        ],
    ),
    MockRouter(
        name="lab-r2",
        hostname="R2",
        platform="cisco_ios",
        vendor="Cisco",
        role="distribution",
        site="msk-lab",
        management_ip="192.0.2.12",
        interfaces=[
            InterfaceSpec(
                name="GigabitEthernet0/0",
                description="Transit to core",
                ipv4_address="172.16.0.2/30",
            ),
            InterfaceSpec(
                name="GigabitEthernet0/1",
                description="Users VLAN gateway",
                ipv4_address="10.20.0.1/24",
            ),
        ],
    ),
    MockRouter(
        name="lab-r3",
        hostname="R3",
        platform="cisco_ios",
        vendor="Cisco",
        role="core",
        site="spb-lab",
        management_ip="192.0.2.13",
        status="maintenance",
        interfaces=[
            InterfaceSpec(
                name="GigabitEthernet1/0",
                description="Core ring west",
                ipv4_address="172.16.10.1/30",
            ),
            InterfaceSpec(
                name="GigabitEthernet1/1",
                description="Core ring east",
                ipv4_address="172.16.10.5/30",
            ),
        ],
    ),
)


class MockInventoryRepository:
    """Simple repository backed by static Python objects."""

    def __init__(self, devices: tuple[MockRouter, ...] = MOCK_ROUTERS) -> None:
        self._devices = {device.name: device for device in devices}

    def list_devices(self) -> list[MockRouter]:
        return list(self._devices.values())

    def get_device(self, device_name: str) -> MockRouter:
        device = self._devices.get(device_name)
        if device is None:
            raise DeviceNotFoundError(f"Mock device '{device_name}' not found")
        return device
