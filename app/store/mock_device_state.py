"""In-memory runtime state for mocked devices."""

import json
from pathlib import Path

from app.automation.models import (
    BaseConfigurationRequest,
    DeviceConfigSnapshot,
    DeviceSnapshotSummary,
    MockDeviceRuntimeState,
)
from app.domain.exceptions import DeviceNotFoundError
from app.domain.models import InterfaceSpec, MockRouter


class MockDeviceStateRepository:
    """Keeps simulated running configuration state per device."""

    def __init__(
        self,
        devices: list[MockRouter] | tuple[MockRouter, ...],
        storage_path: str | Path | None = None,
    ) -> None:
        self._storage_path = Path(storage_path) if storage_path else None
        self._baseline_states = {
            device.name: MockDeviceRuntimeState.from_router(device)
            for device in devices
        }
        self._states = {
            device_name: state.model_copy(deep=True)
            for device_name, state in self._baseline_states.items()
        }
        self._snapshots: dict[str, list[DeviceConfigSnapshot]] = {
            device.name: [] for device in devices
        }
        self._load()

    def get_state(self, device_name: str) -> MockDeviceRuntimeState:
        state = self._states.get(device_name)
        if state is None:
            raise DeviceNotFoundError(f"Mock device '{device_name}' not found")
        return state.model_copy(deep=True)

    def preview_base_configuration(
        self,
        device_name: str,
        request: BaseConfigurationRequest,
    ) -> MockDeviceRuntimeState:
        current_state = self.get_state(device_name)
        candidate = current_state.model_copy(deep=True)
        candidate.hostname = request.hostname
        candidate.domain_name = request.domain_name
        candidate.banner_motd = request.banner_motd
        if request.ntp_server is not None:
            candidate.ntp_server = request.ntp_server
        candidate.interfaces = self._merge_interfaces(
            current_state.interfaces,
            request.interfaces,
        )
        return candidate

    def create_snapshot(
        self,
        device_name: str,
        state: MockDeviceRuntimeState,
    ) -> DeviceSnapshotSummary:
        self.get_state(device_name)
        snapshot = DeviceConfigSnapshot(
            device_name=device_name,
            state=state.model_copy(deep=True),
        )
        self._snapshots[device_name].insert(0, snapshot)
        self._save()
        return self._to_snapshot_summary(snapshot)

    def list_snapshots(self, device_name: str) -> list[DeviceSnapshotSummary]:
        self.get_state(device_name)
        return [self._to_snapshot_summary(snapshot) for snapshot in self._snapshots[device_name]]

    def restore_snapshot(
        self,
        device_name: str,
        snapshot_id: str,
    ) -> MockDeviceRuntimeState:
        snapshot = self._get_snapshot(device_name, snapshot_id)
        restored_state = snapshot.state.model_copy(deep=True)
        self._states[device_name] = restored_state
        self._save()
        return restored_state.model_copy(deep=True)

    def commit_state(
        self,
        device_name: str,
        state: MockDeviceRuntimeState,
        commands: list[str],
    ) -> MockDeviceRuntimeState:
        self.get_state(device_name)
        committed = state.model_copy(deep=True)
        committed.last_deployed_commands = list(commands)
        self._states[device_name] = committed
        self._save()
        return committed.model_copy(deep=True)

    def reset(self) -> tuple[int, int]:
        devices_reset = len(self._states)
        snapshots_cleared = sum(len(snapshots) for snapshots in self._snapshots.values())
        self._states = {
            device_name: state.model_copy(deep=True)
            for device_name, state in self._baseline_states.items()
        }
        self._snapshots = {device_name: [] for device_name in self._baseline_states}
        self._save()
        return devices_reset, snapshots_cleared

    def _load(self) -> None:
        if self._storage_path is None or not self._storage_path.exists():
            return
        payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        for device_name, state_payload in payload.get("states", {}).items():
            if device_name in self._states:
                self._states[device_name] = MockDeviceRuntimeState.model_validate(state_payload)
        for device_name, snapshots_payload in payload.get("snapshots", {}).items():
            if device_name in self._snapshots:
                self._snapshots[device_name] = [
                    DeviceConfigSnapshot.model_validate(snapshot_payload)
                    for snapshot_payload in snapshots_payload
                ]

    def _save(self) -> None:
        if self._storage_path is None:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "states": {
                device_name: state.model_dump(mode="json")
                for device_name, state in self._states.items()
            },
            "snapshots": {
                device_name: [snapshot.model_dump(mode="json") for snapshot in snapshots]
                for device_name, snapshots in self._snapshots.items()
            },
        }
        self._storage_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    def _get_snapshot(self, device_name: str, snapshot_id: str) -> DeviceConfigSnapshot:
        self.get_state(device_name)
        for snapshot in self._snapshots[device_name]:
            if str(snapshot.snapshot_id) == snapshot_id:
                return snapshot.model_copy(deep=True)
        raise DeviceNotFoundError(
            f"Snapshot '{snapshot_id}' not found for device '{device_name}'"
        )

    @staticmethod
    def _to_snapshot_summary(snapshot: DeviceConfigSnapshot) -> DeviceSnapshotSummary:
        return DeviceSnapshotSummary(
            snapshot_id=snapshot.snapshot_id,
            created_at=snapshot.created_at,
            device_name=snapshot.device_name,
        )

    @staticmethod
    def _merge_interfaces(
        current: list[InterfaceSpec],
        requested: list[InterfaceSpec],
    ) -> list[InterfaceSpec]:
        merged = [interface.model_copy(deep=True) for interface in current]
        positions = {interface.name: index for index, interface in enumerate(merged)}

        for interface in requested:
            interface_copy = interface.model_copy(deep=True)
            if interface.name in positions:
                merged[positions[interface.name]] = interface_copy
            else:
                positions[interface.name] = len(merged)
                merged.append(interface_copy)
        return merged
