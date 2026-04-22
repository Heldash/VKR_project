from nornir.core.task import Result, Task

from app.automation.execution_backends import NetmikoExecutionBackend
from app.automation.models import BaseConfigurationRequest
from app.services.automation_service import AutomationService
from app.store.mock_device_state import MockDeviceStateRepository
from app.store.mock_inventory import MockInventoryRepository


class ShowCommandRecorder:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, task: Task, command_string: str, **kwargs) -> Result:
        self.calls += 1
        suffix = "after" if self.calls > 1 else "before"
        output = "\n".join(
            [
                f"hostname {task.host.name}-{suffix}",
                "interface GigabitEthernet0/0",
                " ip address 192.0.2.1 255.255.255.0",
            ]
        )
        return Result(host=task.host, result=output, changed=False)


class SendConfigRecorder:
    def __init__(self) -> None:
        self.calls = 0
        self.last_commands: list[str] = []

    def __call__(self, task: Task, config_commands: list[str], **kwargs) -> Result:
        self.calls += 1
        self.last_commands = list(config_commands)
        return Result(host=task.host, result="\n".join(config_commands), changed=True)


def build_service(show_recorder: ShowCommandRecorder, send_recorder: SendConfigRecorder) -> AutomationService:
    repository = MockInventoryRepository()
    state_repository = MockDeviceStateRepository(repository.list_devices())
    execution_backend = NetmikoExecutionBackend(
        send_config_task=send_recorder,
        show_command_task=show_recorder,
        running_config_command="show running-config",
    )
    return AutomationService(
        repository=repository,
        state_repository=state_repository,
        execution_backend=execution_backend,
    )


def test_netmiko_backend_apply_uses_send_config_and_collects_running_config():
    show_recorder = ShowCommandRecorder()
    send_recorder = SendConfigRecorder()
    service = build_service(show_recorder, send_recorder)
    request = BaseConfigurationRequest(hostname="EDGE-R1", domain_name="edge.lab")

    result = service.deploy_base_configuration("lab-r1", request, dry_run=False)

    assert result.backend == "netmiko"
    assert result.changed is True
    assert result.would_change is True
    assert result.raw_output is not None
    assert "hostname EDGE-R1" in result.raw_output
    assert send_recorder.calls == 1
    assert show_recorder.calls == 2
    assert send_recorder.last_commands[0] == "hostname EDGE-R1"
    assert result.before[0] == "hostname lab-r1-before"
    assert result.after[0] == "hostname lab-r1-after"


def test_netmiko_backend_dry_run_skips_send_config():
    show_recorder = ShowCommandRecorder()
    send_recorder = SendConfigRecorder()
    service = build_service(show_recorder, send_recorder)
    request = BaseConfigurationRequest(hostname="DIST-R2", domain_name="dist.lab")

    result = service.deploy_base_configuration("lab-r2", request, dry_run=True)

    assert result.backend == "netmiko"
    assert result.dry_run is True
    assert result.changed is False
    assert result.would_change is True
    assert send_recorder.calls == 0
    assert show_recorder.calls == 1
    assert result.before == result.after


def test_netmiko_backend_running_config_uses_show_command_task():
    show_recorder = ShowCommandRecorder()
    send_recorder = SendConfigRecorder()
    service = build_service(show_recorder, send_recorder)

    lines = service.get_running_config("lab-r1")

    assert lines[0] == "hostname lab-r1-before"
    assert show_recorder.calls == 1
    assert send_recorder.calls == 0
