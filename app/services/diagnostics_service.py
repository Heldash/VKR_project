"""Active diagnostics for inventory and execution integrations."""

from socket import create_connection
from typing import Any, Callable

import httpx

from app.automation.models import DiagnosticsCheck, DiagnosticsReport, DeviceSelector
from app.core.config import settings
from app.domain.models import MockRouter
from app.services.reachability_service import ReachabilityService
from app.store.factory import build_device_repository
from app.store.netbox_inventory import NetBoxInventoryRepository

DeviceLoader = Callable[[], list[MockRouter]]
NetBoxProbe = Callable[[str, str], tuple[bool, str, dict[str, str | int | bool | None]]]
SocketConnector = Callable[[tuple[str, int], float], Any]


class DiagnosticsService:
    """Runs active diagnostics against currently configured integrations."""

    def __init__(
        self,
        device_loader: DeviceLoader | None = None,
        netbox_probe: NetBoxProbe | None = None,
        socket_connector: SocketConnector | None = None,
        reachability_service: ReachabilityService | None = None,
    ) -> None:
        self._device_loader = device_loader or self._load_devices
        self._netbox_probe = netbox_probe or self._probe_netbox_api
        self._socket_connector = socket_connector or create_connection
        self._reachability_service = reachability_service or ReachabilityService(
            socket_connector=self._socket_connector
        )

    def build_report(self, selector: DeviceSelector | None = None) -> DiagnosticsReport:
        effective_selector = selector or DeviceSelector()
        checks: list[DiagnosticsCheck] = []
        devices: list[MockRouter] = []
        matched_devices: list[MockRouter] = []

        try:
            devices = self._reachability_service.annotate_devices(self._device_loader())
            checks.append(
                DiagnosticsCheck(
                    name="inventory_load",
                    status="success",
                    detail=(
                        f"Loaded {len(devices)} devices from the "
                        f"'{settings.inventory_backend}' inventory backend"
                    ),
                    meta={
                        "backend": settings.inventory_backend,
                        "loaded_devices": len(devices),
                    },
                )
            )
        except Exception as exc:
            checks.append(
                DiagnosticsCheck(
                    name="inventory_load",
                    status="failed",
                    detail=str(exc),
                    meta={"backend": settings.inventory_backend},
                )
            )

        checks.append(self._build_inventory_probe_check())

        if devices:
            matched_devices = self._select_devices(devices, effective_selector)
            selector_filters = {
                key: value
                for key, value in effective_selector.model_dump().items()
                if value is not None
            }
            if selector_filters:
                if matched_devices:
                    checks.append(
                        DiagnosticsCheck(
                            name="target_selector",
                            status="success",
                            detail=(
                                f"Selector matched {len(matched_devices)} device(s): "
                                + ", ".join(device.name for device in matched_devices)
                            ),
                            meta={
                                **selector_filters,
                                "matched_devices": len(matched_devices),
                            },
                        )
                    )
                else:
                    checks.append(
                        DiagnosticsCheck(
                            name="target_selector",
                            status="failed",
                            detail=(
                                "Selector did not match any devices: "
                                + ", ".join(f"{key}={value}" for key, value in selector_filters.items())
                            ),
                            meta=selector_filters,
                        )
                    )
            else:
                matched_devices = list(devices)

        reachable_devices = [device for device in matched_devices if device.status == "reachable"]
        maintenance_devices = [device for device in matched_devices if device.status == "maintenance"]
        unreachable_devices = [device for device in matched_devices if device.status == "unreachable"]
        checks.append(
            self._build_execution_probe_check(
                reachable_devices,
                maintenance_devices,
                unreachable_devices,
            )
        )

        ok = all(check.status == "success" for check in checks)
        return DiagnosticsReport(
            inventory_backend=settings.inventory_backend,
            execution_backend=settings.execution_backend,
            ok=ok,
            matched_devices=len(matched_devices),
            reachable_devices=len(reachable_devices),
            maintenance_devices=len(maintenance_devices),
            unreachable_devices=len(unreachable_devices),
            checks=checks,
        )

    @staticmethod
    def _load_devices() -> list[MockRouter]:
        return build_device_repository().list_devices()

    def _build_inventory_probe_check(self) -> DiagnosticsCheck:
        if settings.inventory_backend == "mock":
            return DiagnosticsCheck(
                name="inventory_probe",
                status="success",
                detail="Mock inventory backend does not require an external connectivity probe",
                meta={"backend": "mock"},
            )

        if not settings.netbox_url or not settings.netbox_token:
            return DiagnosticsCheck(
                name="inventory_probe",
                status="failed",
                detail="NetBox diagnostics require NAA_NETBOX_URL and NAA_NETBOX_TOKEN",
                meta={"backend": "netbox"},
            )

        ok, detail, meta = self._netbox_probe(settings.netbox_url, settings.netbox_token)
        return DiagnosticsCheck(
            name="inventory_probe",
            status="success" if ok else "failed",
            detail=detail,
            meta={"backend": "netbox", **meta},
        )

    def _build_execution_probe_check(
        self,
        reachable_devices: list[MockRouter],
        maintenance_devices: list[MockRouter],
        unreachable_devices: list[MockRouter],
    ) -> DiagnosticsCheck:
        if settings.execution_backend == "mock":
            return DiagnosticsCheck(
                name="execution_probe",
                status="success",
                detail="Mock execution backend does not require a live TCP connectivity probe",
                meta={
                    "backend": "mock",
                    "reachable_devices": len(reachable_devices),
                    "maintenance_devices": len(maintenance_devices),
                    "unreachable_devices": len(unreachable_devices),
                },
            )

        missing: list[str] = []
        if not settings.device_username:
            missing.append("NAA_DEVICE_USERNAME")
        if not settings.device_password:
            missing.append("NAA_DEVICE_PASSWORD")
        if missing:
            return DiagnosticsCheck(
                name="execution_probe",
                status="failed",
                detail="Netmiko diagnostics require credentials: " + ", ".join(missing),
                meta={"backend": "netmiko", "missing_credentials": len(missing)},
            )

        if not reachable_devices:
            return DiagnosticsCheck(
                name="execution_probe",
                status="failed",
                detail="No reachable devices are available for a Netmiko TCP probe",
                meta={
                    "backend": "netmiko",
                    "reachable_devices": 0,
                    "maintenance_devices": len(maintenance_devices),
                    "unreachable_devices": len(unreachable_devices),
                },
            )

        target = reachable_devices[0]
        endpoint = (target.management_ip, settings.device_port)
        try:
            connection = self._socket_connector(endpoint, 3.0)
            close = getattr(connection, "close", None)
            if callable(close):
                close()
        except OSError as exc:
            return DiagnosticsCheck(
                name="execution_probe",
                status="failed",
                detail=(
                    f"Netmiko TCP probe failed for {target.name} at "
                    f"{target.management_ip}:{settings.device_port}: {exc}"
                ),
                meta={
                    "backend": "netmiko",
                    "device_name": target.name,
                    "management_ip": target.management_ip,
                    "port": settings.device_port,
                },
            )

        return DiagnosticsCheck(
            name="execution_probe",
            status="success",
            detail=(
                f"Netmiko TCP probe succeeded for {target.name} at "
                f"{target.management_ip}:{settings.device_port}"
            ),
            meta={
                "backend": "netmiko",
                "device_name": target.name,
                "management_ip": target.management_ip,
                "port": settings.device_port,
                "has_secret": bool(settings.device_secret),
            },
        )

    @staticmethod
    def _probe_netbox_api(
        base_url: str,
        token: str,
    ) -> tuple[bool, str, dict[str, str | int | bool | None]]:
        client = httpx.Client(
            base_url=NetBoxInventoryRepository._normalize_api_root(base_url),
            headers={
                "Authorization": f"Token {token}",
                "Accept": "application/json",
            },
            timeout=settings.netbox_timeout,
        )
        try:
            response = client.get("/")
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            return (
                False,
                f"NetBox diagnostics returned HTTP {exc.response.status_code} for {exc.request.url}",
                {"base_url": base_url},
            )
        except httpx.HTTPError as exc:
            return False, f"NetBox diagnostics request failed: {exc}", {"base_url": base_url}
        finally:
            client.close()

        return True, "NetBox API root responded successfully", {"base_url": base_url}

    @staticmethod
    def _select_devices(devices: list[MockRouter], selector: DeviceSelector) -> list[MockRouter]:
        filtered = list(devices)
        if selector.site is not None:
            filtered = [device for device in filtered if device.site == selector.site]
        if selector.role is not None:
            filtered = [device for device in filtered if device.role == selector.role]
        if selector.status is not None:
            filtered = [device for device in filtered if device.status == selector.status]
        if selector.vendor is not None:
            filtered = [device for device in filtered if device.vendor.lower() == selector.vendor.lower()]
        return filtered
