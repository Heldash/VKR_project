"""Readiness checks for the MVP environment and external integrations."""

from app.automation.factory import build_execution_backend
from app.automation.models import DeviceSelector, PreflightCheck, PreflightReport
from app.core.config import settings
from app.domain.models import MockRouter
from app.store.factory import build_device_repository


class PreflightService:
    """Builds a readiness report for the current automation environment."""

    def build_report(self, selector: DeviceSelector | None = None) -> PreflightReport:
        effective_selector = selector or DeviceSelector()
        checks: list[PreflightCheck] = []
        devices: list[MockRouter] = []
        matched_devices: list[MockRouter] = []

        try:
            repository = build_device_repository()
            devices = repository.list_devices()
            checks.append(
                PreflightCheck(
                    name="inventory_backend",
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
                PreflightCheck(
                    name="inventory_backend",
                    status="failed",
                    detail=str(exc),
                    meta={"backend": settings.inventory_backend},
                )
            )

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
                        PreflightCheck(
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
                        PreflightCheck(
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

        reachable_devices = sum(1 for device in matched_devices if device.status == "reachable")
        maintenance_devices = sum(1 for device in matched_devices if device.status == "maintenance")
        checks.extend(self._build_execution_checks(reachable_devices, maintenance_devices))

        ready = all(check.status == "success" for check in checks)
        return PreflightReport(
            inventory_backend=settings.inventory_backend,
            execution_backend=settings.execution_backend,
            ready=ready,
            matched_devices=len(matched_devices),
            reachable_devices=reachable_devices,
            maintenance_devices=maintenance_devices,
            checks=checks,
        )

    def _build_execution_checks(
        self,
        reachable_devices: int,
        maintenance_devices: int,
    ) -> list[PreflightCheck]:
        checks: list[PreflightCheck] = []
        build_execution_backend()

        if settings.execution_backend == "mock":
            checks.append(
                PreflightCheck(
                    name="execution_backend",
                    status="success",
                    detail="Mock execution backend is enabled; no external device credentials required",
                    meta={"backend": "mock"},
                )
            )
        else:
            missing: list[str] = []
            if not settings.device_username:
                missing.append("NAA_DEVICE_USERNAME")
            if not settings.device_password:
                missing.append("NAA_DEVICE_PASSWORD")
            if missing:
                checks.append(
                    PreflightCheck(
                        name="execution_backend",
                        status="failed",
                        detail="Missing Netmiko credentials: " + ", ".join(missing),
                        meta={"backend": "netmiko", "missing_credentials": len(missing)},
                    )
                )
            else:
                checks.append(
                    PreflightCheck(
                        name="execution_backend",
                        status="success",
                        detail="Netmiko backend credentials are configured",
                        meta={
                            "backend": "netmiko",
                            "port": settings.device_port,
                            "has_secret": bool(settings.device_secret),
                        },
                    )
                )

        if reachable_devices > 0:
            checks.append(
                PreflightCheck(
                    name="target_reachability",
                    status="success",
                    detail=(
                        f"Resolved {reachable_devices} reachable device(s) and "
                        f"{maintenance_devices} maintenance device(s)"
                    ),
                    meta={
                        "reachable_devices": reachable_devices,
                        "maintenance_devices": maintenance_devices,
                    },
                )
            )
        else:
            checks.append(
                PreflightCheck(
                    name="target_reachability",
                    status="failed",
                    detail="No reachable devices are currently available for execution",
                    meta={
                        "reachable_devices": reachable_devices,
                        "maintenance_devices": maintenance_devices,
                    },
                )
            )
        return checks

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
