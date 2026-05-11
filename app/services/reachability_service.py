"""Live reachability checks for inventory devices."""

from socket import create_connection
from time import monotonic
from typing import Any, Callable, Literal

from app.core.config import settings
from app.domain.models import MockRouter

DeviceReachability = Literal["reachable", "maintenance", "unreachable"]
SocketConnector = Callable[[tuple[str, int], float], Any]


class ReachabilityService:
    """Resolves real operational status for devices exposed by the API and UI."""

    def __init__(
        self,
        socket_connector: SocketConnector | None = None,
        timeout_seconds: float = 1.0,
        success_grace_seconds: float = 60.0,
    ) -> None:
        self._socket_connector = socket_connector or create_connection
        self._timeout_seconds = timeout_seconds
        self._success_grace_seconds = success_grace_seconds
        self._recent_success: dict[str, float] = {}

    def get_status(self, device: MockRouter) -> DeviceReachability:
        """Returns live status when real Netmiko execution is enabled."""
        if device.status == "maintenance":
            return "maintenance"
        if settings.execution_backend != "netmiko":
            return "reachable"
        try:
            connection = self._socket_connector(
                (device.management_ip, device.port),
                self._timeout_seconds,
            )
            close = getattr(connection, "close", None)
            if callable(close):
                close()
            self.mark_reachable(device.name)
        except OSError:
            if self._was_reachable_recently(device.name):
                return "reachable"
            return "unreachable"
        return "reachable"

    def annotate_device(self, device: MockRouter) -> MockRouter:
        """Returns a safe copy of the device with live reachability status."""
        return device.model_copy(update={"status": self.get_status(device)})

    def annotate_devices(self, devices: list[MockRouter]) -> list[MockRouter]:
        """Annotates all devices in one inventory slice."""
        return [self.annotate_device(device) for device in devices]

    def mark_reachable(self, device_name: str) -> None:
        """Remembers a recent successful interaction with a device."""
        self._recent_success[device_name] = monotonic()

    def _was_reachable_recently(self, device_name: str) -> bool:
        seen_at = self._recent_success.get(device_name)
        if seen_at is None:
            return False
        return (monotonic() - seen_at) <= self._success_grace_seconds
