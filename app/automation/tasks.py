"""Nornir tasks used by the automation service."""

from typing import Any, Callable

from nornir.core.task import Result, Task

from app.automation.models import (
    BaseConfigurationExecutionResult,
    BaseConfigurationRequest,
)
from app.automation.renderer import BaseConfigRenderer
from app.domain.exceptions import DeviceUnavailableError
from app.store.mock_device_state import MockDeviceStateRepository

TaskCallable = Callable[..., Result]


def deploy_base_configuration_mock(
    task: Task,
    request: BaseConfigurationRequest,
    renderer: BaseConfigRenderer,
    state_repository: MockDeviceStateRepository,
    dry_run: bool = False,
) -> Result:
    """Generates and applies base configuration against a mocked device."""

    if task.host.get("status") != "reachable":
        raise DeviceUnavailableError(
            f"Mock device '{task.host.name}' is in maintenance mode"
        )

    platform = str(task.host.platform or "cisco_ios")
    commands = renderer.render_commands(request, platform=platform)
    before_state = state_repository.get_state(task.host.name)
    before = renderer.render_running_config(before_state, platform=platform)

    candidate_state = state_repository.preview_base_configuration(
        task.host.name,
        request,
    )
    planned_after = renderer.render_running_config(candidate_state, platform=platform)
    would_change = before != planned_after

    if dry_run:
        payload = BaseConfigurationExecutionResult(
            device_name=task.host.name,
            dry_run=True,
            changed=False,
            would_change=would_change,
            commands=commands,
            before=before,
            after=before,
            backend="mock",
        )
        return Result(host=task.host, result=payload.model_dump(), changed=False)

    snapshot_id = None
    if would_change:
        snapshot = state_repository.create_snapshot(task.host.name, before_state)
        snapshot_id = snapshot.snapshot_id

    committed_state = state_repository.commit_state(
        task.host.name,
        candidate_state,
        commands,
    )
    after = renderer.render_running_config(committed_state, platform=platform)
    payload = BaseConfigurationExecutionResult(
        device_name=task.host.name,
        dry_run=False,
        changed=would_change,
        would_change=would_change,
        commands=commands,
        before=before,
        after=after,
        backend="mock",
        snapshot_id=snapshot_id,
    )
    return Result(host=task.host, result=payload.model_dump(), changed=would_change)


def deploy_base_configuration_netmiko(
    task: Task,
    request: BaseConfigurationRequest,
    renderer: BaseConfigRenderer,
    send_config_task: TaskCallable,
    show_command_task: TaskCallable,
    running_config_command: str,
    dry_run: bool = False,
    send_config_kwargs: dict[str, Any] | None = None,
    show_command_kwargs: dict[str, Any] | None = None,
) -> Result:
    """Executes base configuration against a live device through Netmiko."""

    if task.host.get("status") != "reachable":
        raise DeviceUnavailableError(
            f"Mock device '{task.host.name}' is in maintenance mode"
        )

    commands = renderer.render_commands(request, platform=str(task.host.platform or "cisco_ios"))
    before = _collect_running_config(
        task,
        show_command_task,
        running_config_command,
        show_command_kwargs,
    )
    would_change = bool(commands)

    if dry_run:
        payload = BaseConfigurationExecutionResult(
            device_name=task.host.name,
            dry_run=True,
            changed=False,
            would_change=would_change,
            commands=commands,
            before=before,
            after=before,
            backend="netmiko",
        )
        return Result(host=task.host, result=payload.model_dump(), changed=False)

    send_result = task.run(
        task=send_config_task,
        config_commands=commands,
        name="netmiko_send_config",
        **(send_config_kwargs or {}),
    )
    after = _collect_running_config(
        task,
        show_command_task,
        running_config_command,
        show_command_kwargs,
    )
    payload = BaseConfigurationExecutionResult(
        device_name=task.host.name,
        dry_run=False,
        changed=would_change,
        would_change=would_change,
        commands=commands,
        before=before,
        after=after,
        backend="netmiko",
        raw_output=str(send_result.result),
    )
    return Result(host=task.host, result=payload.model_dump(), changed=would_change)


def collect_running_config_netmiko(
    task: Task,
    show_command_task: TaskCallable,
    running_config_command: str,
    show_command_kwargs: dict[str, Any] | None = None,
) -> Result:
    """Collects the running configuration from a live device through Netmiko."""

    lines = _collect_running_config(
        task,
        show_command_task,
        running_config_command,
        show_command_kwargs,
    )
    return Result(host=task.host, result=lines, changed=False)


def _collect_running_config(
    task: Task,
    show_command_task: TaskCallable,
    running_config_command: str,
    show_command_kwargs: dict[str, Any] | None,
) -> list[str]:
    show_result = task.run(
        task=show_command_task,
        command_string=running_config_command,
        name="netmiko_show_running_config",
        **(show_command_kwargs or {}),
    )
    return str(show_result.result).splitlines()
