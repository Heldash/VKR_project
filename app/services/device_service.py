"""Use cases for working with network inventory devices."""

from app.automation.models import DeviceSelectionResponse, DeviceSelector, ResolvedDeviceTarget
from app.domain.models import MockRouter
from app.store.contracts import DeviceRepository


class DeviceService:
    """Provides a stable interface for device-related operations."""

    def __init__(self, repository: DeviceRepository) -> None:
        self._repository = repository

    def list_devices(
        self,
        site: str | None = None,
        role: str | None = None,
        status: str | None = None,
        vendor: str | None = None,
    ) -> list[MockRouter]:
        devices = self._repository.list_devices()
        if site is not None:
            devices = [device for device in devices if device.site == site]
        if role is not None:
            devices = [device for device in devices if device.role == role]
        if status is not None:
            devices = [device for device in devices if device.status == status]
        if vendor is not None:
            devices = [device for device in devices if device.vendor.lower() == vendor.lower()]
        return devices

    def get_device(self, device_name: str) -> MockRouter:
        return self._repository.get_device(device_name)

    def resolve_devices(self, selector: DeviceSelector) -> DeviceSelectionResponse:
        devices = self.list_devices(
            site=selector.site,
            role=selector.role,
            status=selector.status,
            vendor=selector.vendor,
        )
        return DeviceSelectionResponse(
            total_devices=len(devices),
            devices=[
                ResolvedDeviceTarget(
                    name=device.name,
                    site=device.site,
                    role=device.role,
                    status=device.status,
                    vendor=device.vendor,
                    management_ip=device.management_ip,
                )
                for device in devices
            ],
        )
