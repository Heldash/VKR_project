import pytest
from pydantic import ValidationError

from app.automation.models import (
    AutomationJobRequest,
    BaseConfigurationOverrides,
    BaseConfigurationRequest,
    BatchBaseConfigurationItemRequest,
    BatchBaseConfigurationRequest,
    BatchProfileConfigurationItemRequest,
    BatchProfileConfigurationRequest,
    DeviceSelector,
    SelectionBaseConfigurationRequest,
    SelectionProfileConfigurationRequest,
)
from app.core.config import settings
from app.domain.exceptions import DeviceNotFoundError, DeviceUnavailableError
from app.domain.models import InterfaceSpec
from app.services.automation_service import AutomationService
from app.services.diagnostics_service import DiagnosticsService
from app.services.job_service import JobService
from app.services.preflight_service import PreflightService
from app.db.sqlite import SQLiteDatabase
from app.store.mock_device_state import MockDeviceStateRepository
from app.store.mock_inventory import MockInventoryRepository


def build_service() -> AutomationService:
    repository = MockInventoryRepository()
    state_repository = MockDeviceStateRepository(repository.list_devices())
    return AutomationService(
        repository=repository,
        state_repository=state_repository,
    )


def test_generate_base_configuration_preview():
    service = build_service()
    request = BaseConfigurationRequest(
        hostname="BRANCH-R1",
        domain_name="branch.lab",
        banner_motd="Authorized access only",
        ntp_server="192.0.2.200",
        interfaces=[
            InterfaceSpec(
                name="Loopback0",
                description="Automation loopback",
                ipv4_address="10.255.0.1/32",
            )
        ],
    )

    preview = service.generate_base_configuration("lab-r1", request)

    assert preview.device_name == "lab-r1"
    assert preview.commands[0] == "hostname BRANCH-R1"
    assert "ip domain-name branch.lab" in preview.commands
    assert "ntp server 192.0.2.200" in preview.commands
    assert "interface Loopback0" in preview.commands


def test_base_configuration_request_rejects_invalid_ntp_and_duplicate_interfaces():
    with pytest.raises(ValidationError) as exc_info:
        BaseConfigurationRequest(
            hostname="EDGE-R1",
            ntp_server="not-an-ip",
            interfaces=[
                InterfaceSpec(name="Loopback0", description="Primary", ipv4_address="10.255.0.1/32"),
                InterfaceSpec(name="loopback0", description="Duplicate", ipv4_address="10.255.0.2/32"),
            ],
        )

    message = str(exc_info.value)
    assert "ntp_server" in message or "Interface names must be unique" in message


def test_batch_request_rejects_duplicate_device_names():
    with pytest.raises(ValidationError, match="must be unique"):
        BatchBaseConfigurationRequest(
            items=[
                BatchBaseConfigurationItemRequest(
                    device_name="lab-r1",
                    request=BaseConfigurationRequest(hostname="EDGE-R1"),
                ),
                BatchBaseConfigurationItemRequest(
                    device_name="LAB-R1",
                    request=BaseConfigurationRequest(hostname="EDGE-R1-B"),
                ),
            ]
        )


def test_generate_base_configuration_from_profile_merges_overrides():
    service = build_service()
    overrides = BaseConfigurationOverrides(
        hostname="EDGE-R1",
        banner_motd="Branch edge override",
        interfaces=[
            InterfaceSpec(
                name="GigabitEthernet0/0",
                description="Primary ISP uplink",
                ipv4_address="198.51.100.1/30",
            )
        ],
    )

    preview = service.generate_base_configuration_from_profile(
        "lab-r1",
        "branch-edge",
        overrides,
    )

    assert preview.device_name == "lab-r1"
    assert "hostname EDGE-R1" in preview.commands
    assert "ip domain-name branch.lab" in preview.commands
    assert "banner motd ^Branch edge override^" in preview.commands
    assert "ntp server 192.0.2.200" in preview.commands
    assert " description Primary ISP uplink" in preview.commands


def test_generate_base_configuration_batch_returns_mixed_statuses():
    service = build_service()
    batch_request = BatchBaseConfigurationRequest(
        items=[
            BatchBaseConfigurationItemRequest(
                device_name="lab-r1",
                request=BaseConfigurationRequest(hostname="EDGE-R1"),
            ),
            BatchBaseConfigurationItemRequest(
                device_name="lab-r99",
                request=BaseConfigurationRequest(hostname="MISSING-R99"),
            ),
        ]
    )

    response = service.generate_base_configuration_batch(batch_request)

    assert len(response.items) == 2
    assert response.summary.total_items == 2
    assert response.summary.successful_items == 1
    assert response.summary.failed_items == 1
    assert response.items[0].status == "success"
    assert response.items[0].preview is not None
    assert "hostname EDGE-R1" in response.items[0].preview.commands
    assert response.items[1].status == "failed"
    assert response.items[1].preview is None
    assert "lab-r99" in response.items[1].detail


def test_resolve_device_targets_returns_inventory_matches_for_selector():
    service = build_service()

    response = service.resolve_device_targets(
        DeviceSelector(site="msk-lab", status="reachable"),
    )

    assert response.total_devices == 2
    assert [device.name for device in response.devices] == ["lab-r1", "lab-r2"]


def test_preflight_service_reports_ready_mock_environment():
    report = PreflightService().build_report()

    assert report.ready is True
    assert report.inventory_backend == "mock"
    assert report.execution_backend == "mock"
    assert report.matched_devices == 3
    assert report.reachable_devices == 2
    assert report.maintenance_devices == 1
    assert all(check.status == "success" for check in report.checks)



def test_preflight_service_reports_failed_selector_match():
    report = PreflightService().build_report(DeviceSelector(site="unknown-site"))

    assert report.ready is False
    assert report.matched_devices == 0
    assert any(check.name == "target_selector" and check.status == "failed" for check in report.checks)


def test_check_base_configuration_compliance_reports_drift_and_becomes_compliant_after_apply():
    service = build_service()
    request = BaseConfigurationRequest(
        hostname="EDGE-R1",
        domain_name="branch.lab",
        banner_motd="Managed by automation",
        interfaces=[
            InterfaceSpec(
                name="GigabitEthernet0/1",
                description="Users VLAN gateway",
                ipv4_address="10.30.0.1/24",
            )
        ],
    )

    before_report = service.check_base_configuration_compliance("lab-r1", request)
    service.deploy_base_configuration("lab-r1", request, dry_run=False)
    after_report = service.check_base_configuration_compliance("lab-r1", request)

    assert before_report.compliant is False
    assert any(item.path == "hostname" for item in before_report.drift)
    assert any(item.path == "interfaces.GigabitEthernet0/1.description" for item in before_report.drift)
    assert after_report.compliant is True
    assert after_report.drift == []
    assert after_report.current_lines == after_report.expected_lines


def test_check_base_configuration_compliance_batch_returns_partial_results():
    service = build_service()
    batch_request = BatchBaseConfigurationRequest(
        items=[
            BatchBaseConfigurationItemRequest(
                device_name="lab-r1",
                request=BaseConfigurationRequest(hostname="EDGE-R1"),
            ),
            BatchBaseConfigurationItemRequest(
                device_name="lab-r99",
                request=BaseConfigurationRequest(hostname="MISSING-R99"),
            ),
        ]
    )

    response = service.check_base_configuration_compliance_batch(batch_request)

    assert len(response.items) == 2
    assert response.summary.total_items == 2
    assert response.summary.successful_items == 1
    assert response.summary.failed_items == 1
    assert response.summary.compliant_items == 0
    assert response.summary.drifted_items == 1
    assert response.items[0].status == "success"
    assert response.items[0].report is not None
    assert response.items[0].report.compliant is False
    assert response.items[1].status == "failed"
    assert response.items[1].report is None
    assert "lab-r99" in response.items[1].detail


def test_check_base_configuration_compliance_for_selection_filters_targets():
    service = build_service()
    selection_request = SelectionBaseConfigurationRequest(
        selector=DeviceSelector(site="msk-lab", status="reachable"),
        request=BaseConfigurationRequest(hostname="EDGE-R1"),
    )

    response = service.check_base_configuration_compliance_for_selection(selection_request)

    assert len(response.items) == 2
    assert all(item.status == "success" for item in response.items)
    assert [item.device_name for item in response.items] == ["lab-r1", "lab-r2"]


def test_check_base_configuration_compliance_for_selection_rejects_empty_match():
    service = build_service()
    selection_request = SelectionBaseConfigurationRequest(
        selector=DeviceSelector(site="unknown-site"),
        request=BaseConfigurationRequest(hostname="EDGE-R1"),
    )

    with pytest.raises(DeviceNotFoundError, match="unknown-site"):
        service.check_base_configuration_compliance_for_selection(selection_request)


def test_generate_base_configuration_for_selection_returns_previews_for_matched_devices():
    service = build_service()
    selection_request = SelectionBaseConfigurationRequest(
        selector=DeviceSelector(site="msk-lab", status="reachable"),
        request=BaseConfigurationRequest(hostname="EDGE-R1"),
    )

    response = service.generate_base_configuration_for_selection(selection_request)

    assert len(response.items) == 2
    assert [item.device_name for item in response.items] == ["lab-r1", "lab-r2"]
    assert all(item.status == "success" for item in response.items)
    assert all(item.preview is not None for item in response.items)



def test_deploy_base_configuration_from_profile_for_selection_handles_maintenance_devices():
    service = build_service()
    selection_request = SelectionProfileConfigurationRequest(
        selector=DeviceSelector(site="spb-lab"),
        overrides=BaseConfigurationOverrides(hostname="CORE-R3"),
    )

    response = service.deploy_base_configuration_from_profile_for_selection(
        "branch-edge",
        selection_request,
        dry_run=False,
    )

    assert len(response.items) == 1
    assert response.items[0].device_name == "lab-r3"
    assert response.items[0].status == "failed"
    assert response.items[0].result is None
    assert "maintenance mode" in response.items[0].detail


def test_apply_base_configuration_updates_mock_running_state_and_creates_snapshot():
    service = build_service()
    request = BaseConfigurationRequest(
        hostname="EDGE-R1",
        domain_name="edge.lab",
        banner_motd="Managed by automation",
        interfaces=[
            InterfaceSpec(
                name="GigabitEthernet0/1",
                description="Users VLAN gateway",
                ipv4_address="10.30.0.1/24",
            )
        ],
    )

    result = service.deploy_base_configuration("lab-r1", request, dry_run=False)
    running_config = service.get_running_config("lab-r1")
    snapshots = service.list_snapshots("lab-r1")

    assert result.changed is True
    assert result.would_change is True
    assert result.snapshot_id is not None
    assert len(snapshots) == 1
    assert str(snapshots[0].snapshot_id) == str(result.snapshot_id)
    assert "hostname EDGE-R1" in result.after
    assert "ip domain-name edge.lab" in running_config
    assert " description Users VLAN gateway" in running_config
    assert " ip address 10.30.0.1/24" in running_config


def test_rollback_to_snapshot_restores_previous_running_state():
    service = build_service()
    before = service.get_running_config("lab-r1")

    apply_result = service.deploy_base_configuration(
        "lab-r1",
        BaseConfigurationRequest(
            hostname="EDGE-R1",
            domain_name="edge.lab",
            banner_motd="Managed by automation",
        ),
        dry_run=False,
    )
    changed_config = service.get_running_config("lab-r1")
    rollback_result = service.rollback_to_snapshot("lab-r1", str(apply_result.snapshot_id))
    restored_config = service.get_running_config("lab-r1")

    assert apply_result.snapshot_id is not None
    assert before != changed_config
    assert rollback_result.changed is True
    assert rollback_result.before == changed_config
    assert rollback_result.after == before
    assert restored_config == before


def test_dry_run_keeps_mock_running_state_unchanged():
    service = build_service()
    before = service.get_running_config("lab-r2")
    request = BaseConfigurationRequest(
        hostname="DIST-R2",
        domain_name="dist.lab",
        banner_motd="Preview only",
    )

    result = service.deploy_base_configuration("lab-r2", request, dry_run=True)
    after = service.get_running_config("lab-r2")
    snapshots = service.list_snapshots("lab-r2")

    assert result.changed is False
    assert result.would_change is True
    assert result.before == before
    assert after == before
    assert snapshots == []


def test_deploy_base_configuration_batch_from_profile_handles_partial_failure():
    service = build_service()
    batch_request = BatchProfileConfigurationRequest(
        items=[
            BatchProfileConfigurationItemRequest(
                device_name="lab-r1",
                overrides=BaseConfigurationOverrides(hostname="EDGE-R1"),
            ),
            BatchProfileConfigurationItemRequest(
                device_name="lab-r3",
                overrides=BaseConfigurationOverrides(hostname="CORE-R3"),
            ),
        ]
    )

    response = service.deploy_base_configuration_batch_from_profile(
        "branch-edge",
        batch_request,
        dry_run=False,
    )
    running_config = service.get_running_config("lab-r1")

    assert len(response.items) == 2
    assert response.summary.total_items == 2
    assert response.summary.successful_items == 1
    assert response.summary.failed_items == 1
    assert response.summary.changed_items == 1
    assert response.summary.unchanged_items == 0
    assert response.items[0].status == "success"
    assert response.items[0].result is not None
    assert response.items[0].result.changed is True
    assert response.items[0].result.backend == "mock"
    assert response.items[0].result.snapshot_id is not None
    assert "hostname EDGE-R1" in running_config
    assert response.items[1].status == "failed"
    assert response.items[1].result is None
    assert "maintenance mode" in response.items[1].detail


def test_apply_base_configuration_rejects_maintenance_device():
    service = build_service()
    request = BaseConfigurationRequest(hostname="CORE-R3")

    with pytest.raises(DeviceUnavailableError, match="maintenance mode"):
        service.deploy_base_configuration("lab-r3", request)

def test_preflight_service_reports_ready_for_mock_environment():
    report = PreflightService().build_report()

    assert report.ready is True
    assert report.inventory_backend == "mock"
    assert report.execution_backend == "mock"
    assert report.matched_devices == 3
    assert report.reachable_devices == 2
    assert report.maintenance_devices == 1
    assert any(
        check.name == "inventory_backend" and check.status == "success"
        for check in report.checks
    )
    assert any(
        check.name == "execution_backend" and check.status == "success"
        for check in report.checks
    )
    assert any(
        check.name == "target_reachability" and check.status == "success"
        for check in report.checks
    )


def test_preflight_service_reports_failed_selector_when_no_devices_match():
    report = PreflightService().build_report(DeviceSelector(site="unknown-site"))

    assert report.ready is False
    assert report.matched_devices == 0
    assert report.reachable_devices == 0
    assert report.maintenance_devices == 0
    assert any(
        check.name == "target_selector" and check.status == "failed"
        for check in report.checks
    )

class _FakeSocketConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_diagnostics_service_reports_mock_environment_ok():
    report = DiagnosticsService().build_report()

    assert report.ok is True
    assert report.inventory_backend == "mock"
    assert report.execution_backend == "mock"
    assert report.matched_devices == 3
    assert report.reachable_devices == 2
    assert any(
        check.name == "inventory_probe" and check.status == "success"
        for check in report.checks
    )
    assert any(
        check.name == "execution_probe" and check.status == "success"
        for check in report.checks
    )


def test_diagnostics_service_probes_netmiko_tcp_connectivity():
    original_execution_backend = settings.execution_backend
    original_device_username = settings.device_username
    original_device_password = settings.device_password

    calls: list[tuple[tuple[str, int], float]] = []

    def fake_socket_connector(endpoint: tuple[str, int], timeout: float):
        calls.append((endpoint, timeout))
        return _FakeSocketConnection()

    settings.execution_backend = "netmiko"
    settings.device_username = "admin"
    settings.device_password = "admin"

    try:
        report = DiagnosticsService(
            socket_connector=fake_socket_connector,
        ).build_report(DeviceSelector(site="msk-lab", status="reachable"))
    finally:
        settings.execution_backend = original_execution_backend
        settings.device_username = original_device_username
        settings.device_password = original_device_password

    assert report.ok is True
    assert calls == [(("192.0.2.11", 22), 3.0)]
    assert any(
        check.name == "execution_probe" and check.status == "success"
        for check in report.checks
    )

def test_reset_demo_state_restores_mock_baseline_and_clears_history():
    service = build_service()
    request = BaseConfigurationRequest(
        hostname="EDGE-R1",
        domain_name="branch.lab",
        banner_motd="Reset test",
    )

    apply_result = service.deploy_base_configuration("lab-r1", request)
    assert apply_result.changed is True
    assert apply_result.snapshot_id is not None
    assert service.list_operations()
    assert service.list_snapshots("lab-r1")

    reset_result = service.reset_demo_state()

    assert reset_result.execution_backend == "mock"
    assert reset_result.devices_reset == 3
    assert reset_result.snapshots_cleared >= 1
    assert reset_result.operations_cleared >= 1
    assert service.list_operations() == []
    assert service.list_snapshots("lab-r1") == []
    assert service.get_running_config("lab-r1")[0] == "hostname R1"


def test_job_service_executes_job_and_persists_succeeded_status():
    repository = MockInventoryRepository()
    state_repository = MockDeviceStateRepository(repository.list_devices())
    automation_service = AutomationService(
        repository=repository,
        state_repository=state_repository,
    )
    job_service = JobService(
        database=SQLiteDatabase(settings.database_path),
        repository=repository,
    )
    job = job_service.create_job(
        AutomationJobRequest(
            operation="apply",
            device_name="lab-r1",
            request=BaseConfigurationRequest(hostname="EDGE-R1"),
            dry_run=True,
        )
    )

    updated = job_service.execute_job(job.job_id, automation_service)

    assert updated.status == "succeeded"
    assert updated.result is not None
    assert updated.result["device_name"] == "lab-r1"
    assert updated.result["dry_run"] is True


def test_job_service_dispatches_to_celery_backend_via_dispatcher():
    original_task_queue_backend = settings.task_queue_backend
    repository = MockInventoryRepository()
    dispatched: list[str] = []

    def fake_dispatcher(job_id: str) -> str:
        dispatched.append(job_id)
        return "broker-task-123"

    settings.task_queue_backend = "celery"
    try:
        job_service = JobService(
            database=SQLiteDatabase(settings.database_path),
            repository=repository,
            celery_dispatcher=fake_dispatcher,
        )
        job = job_service.create_job(
            AutomationJobRequest(
                operation="compliance",
                device_name="lab-r1",
                request=BaseConfigurationRequest(hostname="EDGE-R1"),
            )
        )
    finally:
        settings.task_queue_backend = original_task_queue_backend

    assert dispatched == [job.job_id]
    assert job.status == "queued"
    assert job.queue_backend == "celery"
    assert job.result == {"broker_task_id": "broker-task-123"}


def test_job_service_retries_failed_database_job():
    original_task_queue_backend = settings.task_queue_backend
    repository = MockInventoryRepository()
    state_repository = MockDeviceStateRepository(repository.list_devices())
    automation_service = AutomationService(
        repository=repository,
        state_repository=state_repository,
    )
    job_service = JobService(
        database=SQLiteDatabase(settings.database_path),
        repository=repository,
    )

    settings.task_queue_backend = "database"
    try:
        job = job_service.create_job(
            AutomationJobRequest(
                operation="apply",
                device_name="lab-r3",
                request=BaseConfigurationRequest(hostname="EDGE-R3"),
            )
        )
        failed = job_service.execute_job(job.job_id, automation_service)
        retried = job_service.retry_job(job.job_id)
    finally:
        settings.task_queue_backend = original_task_queue_backend

    assert failed.status == "failed"
    assert failed.error is not None
    assert retried.status == "queued"
    assert retried.error is None
    assert retried.result is None

