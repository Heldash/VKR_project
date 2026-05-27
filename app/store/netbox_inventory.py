"""NetBox-backed inventory adapter."""

from ipaddress import ip_interface
from typing import Any

import httpx

from app.core.config import settings
from app.domain.exceptions import DeviceNotFoundError, InventoryBackendError
from app.domain.models import InterfaceSpec, MockRouter


class NetBoxInventoryRepository:
    """Loads device inventory from NetBox using its REST API."""

    def __init__(
        self,
        base_url: str | None,
        token: str | None,
        client: httpx.Client | None = None,
    ) -> None:
        self._owns_client = False
        if not base_url or not token:
            raise InventoryBackendError(
                "NetBox backend requires NAA_NETBOX_URL and NAA_NETBOX_TOKEN"
            )
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=self._normalize_api_root(base_url),
            headers={
                "Authorization": f"Token {token}",
                "Accept": "application/json",
            },
            timeout=settings.netbox_timeout,
        )

    def __del__(self) -> None:
        if getattr(self, "_owns_client", False):
            self._client.close()

    def list_devices(self) -> list[MockRouter]:
        devices = self._paginate("/dcim/devices/", params={"limit": 100})
        return [self._to_router(device) for device in devices]

    def get_device(self, device_name: str) -> MockRouter:
        devices = self._paginate(
            "/dcim/devices/",
            params={"name": device_name, "limit": 2},
        )
        for device in devices:
            if device.get("name") == device_name:
                return self._to_router(device)
        if devices:
            return self._to_router(devices[0])
        raise DeviceNotFoundError(f"Mock device '{device_name}' not found")

    def _to_router(self, device: dict[str, Any]) -> MockRouter:
        device_id = device.get("id")
        if device_id is None:
            raise InventoryBackendError("NetBox response did not include device id")

        return MockRouter(
            name=device.get("name") or f"device-{device_id}",
            hostname=device.get("name") or f"device-{device_id}",
            platform=self._extract_platform(device),
            vendor=self._extract_vendor(device),
            role=self._extract_role(device),
            site=self._extract_site(device),
            management_ip=self._extract_management_ip(device),
            status=self._extract_status(device),
            interfaces=self._get_interfaces(device_id),
        )

    def _get_interfaces(self, device_id: int) -> list[InterfaceSpec]:
        interfaces = self._paginate(
            "/dcim/interfaces/",
            params={"device_id": device_id, "limit": 100},
        )
        return [
            InterfaceSpec(
                name=interface.get("name") or "unknown",
                description=interface.get("description") or "",
                enabled=bool(interface.get("enabled", True)),
            )
            for interface in interfaces
        ]

    def _paginate(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        next_url: str | None = path
        next_params = params

        while next_url:
            payload = self._request_json(next_url, params=next_params)
            items = payload.get("results")
            if not isinstance(items, list):
                raise InventoryBackendError(
                    "Unexpected NetBox response format: 'results' list is missing"
                )
            results.extend(items)
            next_url = payload.get("next")
            next_params = None
        return results

    def _request_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise InventoryBackendError(
                f"NetBox API returned HTTP {exc.response.status_code} for {exc.request.url}"
            ) from exc
        except httpx.HTTPError as exc:
            raise InventoryBackendError(f"NetBox API request failed: {exc}") from exc

        payload = response.json()
        if not isinstance(payload, dict):
            raise InventoryBackendError("Unexpected NetBox response payload")
        return payload

    @staticmethod
    def _normalize_api_root(base_url: str) -> str:
        normalized = base_url.rstrip("/")
        if not normalized.endswith("/api"):
            normalized = f"{normalized}/api"
        return f"{normalized}/"

    @staticmethod
    def _extract_platform(device: dict[str, Any]) -> str:
        platform = device.get("platform") or {}
        return (
            platform.get("slug")
            or platform.get("name")
            or platform.get("display")
            or "unknown"
        )

    @staticmethod
    def _extract_vendor(device: dict[str, Any]) -> str:
        device_type = device.get("device_type") or {}
        manufacturer = device_type.get("manufacturer") or device.get("manufacturer") or {}
        return (
            manufacturer.get("name")
            or manufacturer.get("display")
            or manufacturer.get("slug")
            or "unknown"
        )

    @staticmethod
    def _extract_role(device: dict[str, Any]) -> str:
        role = device.get("role") or {}
        role_value = " ".join(
            str(value)
            for value in (
                role.get("slug"),
                role.get("name"),
                role.get("display"),
                role.get("label"),
            )
            if value
        ).lower()
        if "core" in role_value:
            return "core"
        if "distribution" in role_value or "dist" in role_value:
            return "distribution"
        return "edge"

    @staticmethod
    def _extract_site(device: dict[str, Any]) -> str:
        site = device.get("site") or {}
        return site.get("slug") or site.get("name") or site.get("display") or "default"

    @staticmethod
    def _extract_management_ip(device: dict[str, Any]) -> str:
        primary = device.get("primary_ip4") or device.get("primary_ip") or device.get("primary_ip6")
        address = (primary or {}).get("address")
        if isinstance(address, str):
            return str(ip_interface(address).ip)
        return device.get("name") or "0.0.0.0"

    @staticmethod
    def _extract_status(device: dict[str, Any]) -> str:
        status = device.get("status") or {}
        value = str(status.get("value") or status.get("label") or status).lower()
        if value in {"active", "online"}:
            return "reachable"
        return "maintenance"
