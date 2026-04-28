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
        site="msk-core",
        management_ip="172.16.159.11",
        username="admin",
        password="admin",
        interfaces=[
            InterfaceSpec(
                name="GigabitEthernet0/0",
                description="Transit to R2",
                ipv4_address="10.0.12.1/30",
            ),
        ],
    ),
    MockRouter(
        name="lab-r2",
        hostname="R2",
        platform="cisco_ios",
        vendor="Cisco",
        role="distribution",
        site="msk-core",
        management_ip="172.16.159.12",
        username="admin",
        password="admin",
        interfaces=[
            InterfaceSpec(
                name="GigabitEthernet0/0",
                description="Transit to R1",
                ipv4_address="10.0.12.2/30",
            ),
            InterfaceSpec(
                name="GigabitEthernet1/0",
                description="Transit to R3",
                ipv4_address="10.0.23.1/30",
            ),
            InterfaceSpec(
                name="GigabitEthernet2/0",
                description="Transit to R4",
                ipv4_address="10.0.24.1/30",
            ),
        ],
    ),
    MockRouter(
        name="lab-r3",
        hostname="R3",
        platform="cisco_ios",
        vendor="Cisco",
        role="edge",
        site="msk-branch-a",
        management_ip="172.16.159.13",
        username="admin",
        password="admin",
        interfaces=[
            InterfaceSpec(
                name="GigabitEthernet0/0",
                description="Transit to R2",
                ipv4_address="10.0.23.2/30",
            ),
        ],
    ),
    MockRouter(
        name="lab-r4",
        hostname="R4",
        platform="cisco_ios",
        vendor="Cisco",
        role="edge",
        site="msk-branch-b",
        management_ip="172.16.159.14",
        username="admin",
        password="admin",
        interfaces=[
            InterfaceSpec(
                name="GigabitEthernet0/0",
                description="Transit to R2",
                ipv4_address="10.0.24.2/30",
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
