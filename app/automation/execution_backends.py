"""Execution backends for configuration deployment workflows."""

from typing import Protocol

from nornir.core import Nornir
from nornir_netmiko.tasks import netmiko_send_command, netmiko_send_config

from app.automation.models import BaseConfigurationExecutionResult, BaseConfigurationRequest
from app.automation.renderer import BaseConfigRenderer
from app.automation.tasks import (
    collect_running_config_netmiko,
    deploy_base_configuration_mock,
    deploy_base_configuration_netmiko,
)
from app.core.config import settings
from app.domain.exceptions import AutomationExecutionError
from app.store.mock_device_state import MockDeviceStateRepository


class ConfigExecutionBackend(Protocol):
    """Contract for executing configuration workflows."""

    backend_name: str

    def deploy_base_configuration(
        self,
        nornir: Nornir,
        device_name: str,
        request: BaseConfigurationRequest,
        renderer: BaseConfigRenderer,
        state_repository: MockDeviceStateRepository,
        dry_run: bool = False,
    ) -> BaseConfigurationExecutionResult:
        ...

    def get_running_config(
        self,
        nornir: Nornir,
        device_name: str,
        renderer: BaseConfigRenderer,
        state_repository: MockDeviceStateRepository,
    ) -> list[str]:
        ...


class MockExecutionBackend:
    """Executes configuration workflows against the in-memory device state."""

    backend_name = "mock"

    def deploy_base_configuration(
        self,
        nornir: Nornir,
        device_name: str,
        request: BaseConfigurationRequest,
        renderer: BaseConfigRenderer,
        state_repository: MockDeviceStateRepository,
        dry_run: bool = False,
    ) -> BaseConfigurationExecutionResult:
        try:
            results = nornir.filter(name=device_name).run(
                task=deploy_base_configuration_mock,
                request=request,
                renderer=renderer,
                state_repository=state_repository,
                dry_run=dry_run,
            )
            task_result = _unwrap_result(results, device_name)
        except Exception as exc:
            if isinstance(exc, (AutomationExecutionError,)):
                raise
            if exc.__class__.__name__ == "DeviceUnavailableError":
                raise
            raise AutomationExecutionError(
                f"Configuration deployment failed for device '{device_name}': {exc}"
            ) from exc
        return BaseConfigurationExecutionResult.model_validate(task_result.result)

    def get_running_config(
        self,
        nornir: Nornir,
        device_name: str,
        renderer: BaseConfigRenderer,
        state_repository: MockDeviceStateRepository,
    ) -> list[str]:
        state = state_repository.get_state(device_name)
        return renderer.render_running_config(state)


class NetmikoExecutionBackend:
    """Executes configuration workflows against real devices through Netmiko."""

    backend_name = "netmiko"

    def __init__(
        self,
        send_config_task=netmiko_send_config,
        show_command_task=netmiko_send_command,
        running_config_command: str | None = None,
    ) -> None:
        self._send_config_task = send_config_task
        self._show_command_task = show_command_task
        self._running_config_command = (
            running_config_command or settings.running_config_command
        )

    def deploy_base_configuration(
        self,
        nornir: Nornir,
        device_name: str,
        request: BaseConfigurationRequest,
        renderer: BaseConfigRenderer,
        state_repository: MockDeviceStateRepository,
        dry_run: bool = False,
    ) -> BaseConfigurationExecutionResult:
        try:
            results = nornir.filter(name=device_name).run(
                task=deploy_base_configuration_netmiko,
                request=request,
                renderer=renderer,
                send_config_task=self._send_config_task,
                show_command_task=self._show_command_task,
                running_config_command=self._running_config_command,
                dry_run=dry_run,
            )
            task_result = _unwrap_result(results, device_name)
        except Exception as exc:
            if isinstance(exc, (AutomationExecutionError,)):
                raise
            if exc.__class__.__name__ == "DeviceUnavailableError":
                raise
            raise AutomationExecutionError(
                f"Netmiko execution failed for device '{device_name}': {exc}"
            ) from exc
        return BaseConfigurationExecutionResult.model_validate(task_result.result)

    def get_running_config(
        self,
        nornir: Nornir,
        device_name: str,
        renderer: BaseConfigRenderer,
        state_repository: MockDeviceStateRepository,
    ) -> list[str]:
        try:
            results = nornir.filter(name=device_name).run(
                task=collect_running_config_netmiko,
                show_command_task=self._show_command_task,
                running_config_command=self._running_config_command,
            )
            task_result = _unwrap_result(results, device_name)
        except Exception as exc:
            raise AutomationExecutionError(
                f"Failed to collect running configuration from '{device_name}': {exc}"
            ) from exc
        return list(task_result.result)


def _unwrap_result(results, device_name: str):
    task_result = results[device_name][0]
    if task_result.failed:
        if task_result.exception is not None:
            raise task_result.exception
        raise AutomationExecutionError(str(task_result.result))
    return task_result
