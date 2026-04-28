"""Service layer for Nornir-backed automation workflows."""

from app.automation.execution_backends import ConfigExecutionBackend, MockExecutionBackend
from app.automation.models import (
    BaseConfigurationComplianceReport,
    BatchComplianceItem,
    BatchComplianceResponse,
    BatchComplianceSummary,
    BaseConfigurationExecutionResult,
    BaseConfigurationOverrides,
    BaseConfigurationPreview,
    BaseConfigurationProfile,
    BaseConfigurationRequest,
    BatchBaseConfigurationItemRequest,
    BatchBaseConfigurationRequest,
    BatchExecutionItem,
    BatchExecutionResponse,
    BatchExecutionSummary,
    BatchPreviewItem,
    BatchPreviewResponse,
    BatchPreviewSummary,
    BatchProfileConfigurationItemRequest,
    BatchProfileConfigurationRequest,
    ConfigurationDriftItem,
    DemoResetResponse,
    DeviceSelectionResponse,
    DeviceSelector,
    DeviceSnapshotSummary,
    MockDeviceRuntimeState,
    OperationRecord,
    OperationSummary,
    ResolvedDeviceTarget,
    RollbackExecutionResult,
    RunningConfigResponse,
    SelectionBaseConfigurationRequest,
    SelectionProfileConfigurationRequest,
)
from app.automation.nornir_factory import build_nornir
from app.automation.renderer import BaseConfigRenderer
from app.core.config import settings
from app.core.request_context import get_request_id
from app.domain.exceptions import AutomationExecutionError, DeviceNotFoundError, DeviceUnavailableError
from app.domain.models import InterfaceSpec, MockRouter
from app.store.config_profiles import ConfigurationProfileRepository
from app.store.contracts import DeviceRepository
from app.store.mock_device_state import MockDeviceStateRepository
from app.store.operation_journal import OperationJournalRepository
from app.services.reachability_service import ReachabilityService


class AutomationService:
    """Coordinates config generation and deployment through Nornir."""

    def __init__(
        self,
        repository: DeviceRepository,
        state_repository: MockDeviceStateRepository,
        renderer: BaseConfigRenderer | None = None,
        execution_backend: ConfigExecutionBackend | None = None,
        journal_repository: OperationJournalRepository | None = None,
        profile_repository: ConfigurationProfileRepository | None = None,
        reachability_service: ReachabilityService | None = None,
    ) -> None:
        self._repository = repository
        self._state_repository = state_repository
        self._renderer = renderer or BaseConfigRenderer()
        self._execution_backend = execution_backend or MockExecutionBackend()
        self._journal_repository = journal_repository or OperationJournalRepository()
        self._profile_repository = profile_repository or ConfigurationProfileRepository()
        self._reachability_service = reachability_service or ReachabilityService()
        self._running_config_cache: dict[str, list[str]] = {}
        self._nornir = build_nornir(self._repository.list_devices())

    def list_profiles(self) -> list[BaseConfigurationProfile]:
        return self._profile_repository.list_profiles()

    def get_profile(self, profile_name: str) -> BaseConfigurationProfile:
        return self._profile_repository.get_profile(profile_name)

    def generate_base_configuration(
        self,
        device_name: str,
        request: BaseConfigurationRequest,
    ) -> BaseConfigurationPreview:
        self._repository.get_device(device_name)
        preview = BaseConfigurationPreview(
            device_name=device_name,
            commands=self._renderer.render_commands(request),
        )
        self._journal_repository.add(
            OperationRecord(
                operation="preview",
                device_name=device_name,
                request_id=get_request_id(),
                backend=self._execution_backend.backend_name,
                status="success",
                request=request,
                commands=preview.commands,
                would_change=bool(preview.commands),
            )
        )
        return preview

    def generate_base_configuration_from_profile(
        self,
        device_name: str,
        profile_name: str,
        overrides: BaseConfigurationOverrides,
    ) -> BaseConfigurationPreview:
        request = self._profile_repository.build_request(profile_name, overrides)
        return self.generate_base_configuration(device_name, request)

    def generate_base_configuration_batch(
        self,
        batch_request: BatchBaseConfigurationRequest,
    ) -> BatchPreviewResponse:
        items: list[BatchPreviewItem] = []
        for item in batch_request.items:
            try:
                preview = self.generate_base_configuration(item.device_name, item.request)
                items.append(
                    BatchPreviewItem(
                        device_name=item.device_name,
                        status="success",
                        preview=preview,
                    )
                )
            except DeviceNotFoundError as exc:
                items.append(
                    BatchPreviewItem(
                        device_name=item.device_name,
                        status="failed",
                        detail=str(exc),
                    )
                )
        return BatchPreviewResponse(items=items, summary=self._build_preview_summary(items))

    def generate_base_configuration_batch_from_profile(
        self,
        profile_name: str,
        batch_request: BatchProfileConfigurationRequest,
    ) -> BatchPreviewResponse:
        items: list[BatchPreviewItem] = []
        for item in batch_request.items:
            try:
                preview = self.generate_base_configuration_from_profile(
                    item.device_name,
                    profile_name,
                    item.overrides,
                )
                items.append(
                    BatchPreviewItem(
                        device_name=item.device_name,
                        status="success",
                        preview=preview,
                    )
                )
            except DeviceNotFoundError as exc:
                items.append(
                    BatchPreviewItem(
                        device_name=item.device_name,
                        status="failed",
                        detail=str(exc),
                    )
                )
        return BatchPreviewResponse(items=items, summary=self._build_preview_summary(items))

    def resolve_device_targets(self, selector: DeviceSelector) -> DeviceSelectionResponse:
        devices = self._select_devices(selector)
        return DeviceSelectionResponse(
            total_devices=len(devices),
            devices=[self._to_resolved_target(device) for device in devices],
        )

    def generate_base_configuration_for_selection(
        self,
        selection_request: SelectionBaseConfigurationRequest,
    ) -> BatchPreviewResponse:
        matched_devices = self._select_devices(selection_request.selector)
        self._ensure_devices_matched(matched_devices, selection_request.selector)
        return self.generate_base_configuration_batch(
            BatchBaseConfigurationRequest(
                items=[
                    BatchBaseConfigurationItemRequest(
                        device_name=device.name,
                        request=selection_request.request,
                    )
                    for device in matched_devices
                ]
            )
        )

    def generate_base_configuration_from_profile_for_selection(
        self,
        profile_name: str,
        selection_request: SelectionProfileConfigurationRequest,
    ) -> BatchPreviewResponse:
        matched_devices = self._select_devices(selection_request.selector)
        self._ensure_devices_matched(matched_devices, selection_request.selector)
        return self.generate_base_configuration_batch_from_profile(
            profile_name,
            BatchProfileConfigurationRequest(
                items=[
                    BatchProfileConfigurationItemRequest(
                        device_name=device.name,
                        overrides=selection_request.overrides,
                    )
                    for device in matched_devices
                ]
            )
        )

    def check_base_configuration_compliance(
        self,
        device_name: str,
        request: BaseConfigurationRequest,
    ) -> BaseConfigurationComplianceReport:
        self._repository.get_device(device_name)
        try:
            self._ensure_mock_compliance_supported()
            current_state = self._state_repository.get_state(device_name)
            expected_state = self._state_repository.preview_base_configuration(
                device_name,
                request,
            )
        except AutomationExecutionError as exc:
            self._journal_repository.add(
                OperationRecord(
                    operation="compliance",
                    device_name=device_name,
                    request_id=get_request_id(),
                    backend=self._execution_backend.backend_name,
                    status="failed",
                    request=request,
                    commands=self._renderer.render_commands(request),
                    detail=str(exc),
                )
            )
            raise

        report = BaseConfigurationComplianceReport(
            device_name=device_name,
            compliant=False,
            drift=self._build_drift(current_state, expected_state),
            current_lines=self._renderer.render_running_config(current_state),
            expected_lines=self._renderer.render_running_config(expected_state),
            backend="mock",
        )
        report.compliant = len(report.drift) == 0

        self._journal_repository.add(
            OperationRecord(
                operation="compliance",
                device_name=device_name,
                request_id=get_request_id(),
                backend="mock",
                status="success",
                request=request,
                commands=self._renderer.render_commands(request),
                changed=not report.compliant,
                would_change=not report.compliant,
                detail=(
                    "Configuration is compliant"
                    if report.compliant
                    else f"Detected {len(report.drift)} drift item(s)"
                ),
            )
        )
        return report

    def check_base_configuration_compliance_from_profile(
        self,
        device_name: str,
        profile_name: str,
        overrides: BaseConfigurationOverrides,
    ) -> BaseConfigurationComplianceReport:
        request = self._profile_repository.build_request(profile_name, overrides)
        return self.check_base_configuration_compliance(device_name, request)

    def check_base_configuration_compliance_batch(
        self,
        batch_request: BatchBaseConfigurationRequest,
    ) -> BatchComplianceResponse:
        items: list[BatchComplianceItem] = []
        for item in batch_request.items:
            try:
                report = self.check_base_configuration_compliance(
                    item.device_name,
                    item.request,
                )
                items.append(
                    BatchComplianceItem(
                        device_name=item.device_name,
                        status="success",
                        report=report,
                    )
                )
            except (DeviceNotFoundError, AutomationExecutionError) as exc:
                items.append(
                    BatchComplianceItem(
                        device_name=item.device_name,
                        status="failed",
                        detail=str(exc),
                    )
                )
        return BatchComplianceResponse(items=items, summary=self._build_compliance_summary(items))

    def check_base_configuration_compliance_batch_from_profile(
        self,
        profile_name: str,
        batch_request: BatchProfileConfigurationRequest,
    ) -> BatchComplianceResponse:
        items: list[BatchComplianceItem] = []
        for item in batch_request.items:
            try:
                report = self.check_base_configuration_compliance_from_profile(
                    item.device_name,
                    profile_name,
                    item.overrides,
                )
                items.append(
                    BatchComplianceItem(
                        device_name=item.device_name,
                        status="success",
                        report=report,
                    )
                )
            except (DeviceNotFoundError, AutomationExecutionError) as exc:
                items.append(
                    BatchComplianceItem(
                        device_name=item.device_name,
                        status="failed",
                        detail=str(exc),
                    )
                )
        return BatchComplianceResponse(items=items, summary=self._build_compliance_summary(items))

    def check_base_configuration_compliance_for_selection(
        self,
        selection_request: SelectionBaseConfigurationRequest,
    ) -> BatchComplianceResponse:
        matched_devices = self._select_devices(selection_request.selector)
        self._ensure_devices_matched(matched_devices, selection_request.selector)
        return self.check_base_configuration_compliance_batch(
            BatchBaseConfigurationRequest(
                items=[
                    BatchBaseConfigurationItemRequest(
                        device_name=device.name,
                        request=selection_request.request,
                    )
                    for device in matched_devices
                ]
            )
        )

    def check_base_configuration_compliance_from_profile_for_selection(
        self,
        profile_name: str,
        selection_request: SelectionProfileConfigurationRequest,
    ) -> BatchComplianceResponse:
        matched_devices = self._select_devices(selection_request.selector)
        self._ensure_devices_matched(matched_devices, selection_request.selector)
        return self.check_base_configuration_compliance_batch_from_profile(
            profile_name,
            BatchProfileConfigurationRequest(
                items=[
                    BatchProfileConfigurationItemRequest(
                        device_name=device.name,
                        overrides=selection_request.overrides,
                    )
                    for device in matched_devices
                ]
            )
        )

    def deploy_base_configuration(
        self,
        device_name: str,
        request: BaseConfigurationRequest,
        dry_run: bool = False,
    ) -> BaseConfigurationExecutionResult:
        self._repository.get_device(device_name)
        runtime_nornir = self._build_runtime_nornir(device_name)
        try:
            result = self._execution_backend.deploy_base_configuration(
                nornir=runtime_nornir,
                device_name=device_name,
                request=request,
                renderer=self._renderer,
                state_repository=self._state_repository,
                dry_run=dry_run,
            )
        except (AutomationExecutionError, DeviceUnavailableError) as exc:
            self._journal_repository.add(
                OperationRecord(
                    operation="apply",
                    device_name=device_name,
                    request_id=get_request_id(),
                    dry_run=dry_run,
                    backend=self._execution_backend.backend_name,
                    status="failed",
                    request=request,
                    commands=self._renderer.render_commands(request),
                    detail=str(exc),
                )
            )
            raise

        self._journal_repository.add(
            OperationRecord(
                operation="apply",
                device_name=device_name,
                request_id=get_request_id(),
                dry_run=dry_run,
                backend=result.backend,
                status="success",
                request=request,
                commands=result.commands,
                changed=result.changed,
                would_change=result.would_change,
                snapshot_id=result.snapshot_id,
            )
        )
        self._reachability_service.mark_reachable(device_name)
        self._running_config_cache[device_name] = list(result.after)
        return result

    def deploy_base_configuration_from_profile(
        self,
        device_name: str,
        profile_name: str,
        overrides: BaseConfigurationOverrides,
        dry_run: bool = False,
    ) -> BaseConfigurationExecutionResult:
        request = self._profile_repository.build_request(profile_name, overrides)
        return self.deploy_base_configuration(device_name, request, dry_run=dry_run)

    def deploy_base_configuration_batch(
        self,
        batch_request: BatchBaseConfigurationRequest,
        dry_run: bool = False,
    ) -> BatchExecutionResponse:
        items: list[BatchExecutionItem] = []
        for item in batch_request.items:
            try:
                result = self.deploy_base_configuration(
                    item.device_name,
                    item.request,
                    dry_run=dry_run,
                )
                items.append(
                    BatchExecutionItem(
                        device_name=item.device_name,
                        status="success",
                        result=result,
                    )
                )
            except (DeviceNotFoundError, DeviceUnavailableError, AutomationExecutionError) as exc:
                items.append(
                    BatchExecutionItem(
                        device_name=item.device_name,
                        status="failed",
                        detail=str(exc),
                    )
                )
        return BatchExecutionResponse(items=items, summary=self._build_execution_summary(items))

    def deploy_base_configuration_batch_from_profile(
        self,
        profile_name: str,
        batch_request: BatchProfileConfigurationRequest,
        dry_run: bool = False,
    ) -> BatchExecutionResponse:
        items: list[BatchExecutionItem] = []
        for item in batch_request.items:
            try:
                result = self.deploy_base_configuration_from_profile(
                    item.device_name,
                    profile_name,
                    item.overrides,
                    dry_run=dry_run,
                )
                items.append(
                    BatchExecutionItem(
                        device_name=item.device_name,
                        status="success",
                        result=result,
                    )
                )
            except (DeviceNotFoundError, DeviceUnavailableError, AutomationExecutionError) as exc:
                items.append(
                    BatchExecutionItem(
                        device_name=item.device_name,
                        status="failed",
                        detail=str(exc),
                    )
                )
        return BatchExecutionResponse(items=items, summary=self._build_execution_summary(items))

    def deploy_base_configuration_for_selection(
        self,
        selection_request: SelectionBaseConfigurationRequest,
        dry_run: bool = False,
    ) -> BatchExecutionResponse:
        matched_devices = self._select_devices(selection_request.selector)
        self._ensure_devices_matched(matched_devices, selection_request.selector)
        return self.deploy_base_configuration_batch(
            BatchBaseConfigurationRequest(
                items=[
                    BatchBaseConfigurationItemRequest(
                        device_name=device.name,
                        request=selection_request.request,
                    )
                    for device in matched_devices
                ]
            ),
            dry_run=dry_run,
        )

    def deploy_base_configuration_from_profile_for_selection(
        self,
        profile_name: str,
        selection_request: SelectionProfileConfigurationRequest,
        dry_run: bool = False,
    ) -> BatchExecutionResponse:
        matched_devices = self._select_devices(selection_request.selector)
        self._ensure_devices_matched(matched_devices, selection_request.selector)
        return self.deploy_base_configuration_batch_from_profile(
            profile_name,
            BatchProfileConfigurationRequest(
                items=[
                    BatchProfileConfigurationItemRequest(
                        device_name=device.name,
                        overrides=selection_request.overrides,
                    )
                    for device in matched_devices
                ]
            ),
            dry_run=dry_run,
        )

    def get_running_config_response(self, device_name: str) -> RunningConfigResponse:
        self._repository.get_device(device_name)
        runtime_nornir = self._build_runtime_nornir(device_name)
        try:
            lines = self._execution_backend.get_running_config(
                nornir=runtime_nornir,
                device_name=device_name,
                renderer=self._renderer,
                state_repository=self._state_repository,
            )
        except AutomationExecutionError as exc:
            cached_lines = self._running_config_cache.get(device_name)
            if cached_lines is not None:
                return RunningConfigResponse(
                    device_name=device_name,
                    lines=list(cached_lines),
                    cached=True,
                    collection_error=str(exc),
                )
            raise

        self._reachability_service.mark_reachable(device_name)
        self._running_config_cache[device_name] = list(lines)
        return RunningConfigResponse(device_name=device_name, lines=list(lines))

    def get_running_config(self, device_name: str) -> list[str]:
        return self.get_running_config_response(device_name).lines

    def list_snapshots(self, device_name: str) -> list[DeviceSnapshotSummary]:
        self._repository.get_device(device_name)
        return self._state_repository.list_snapshots(device_name)

    def rollback_to_snapshot(
        self,
        device_name: str,
        snapshot_id: str,
    ) -> RollbackExecutionResult:
        self._repository.get_device(device_name)
        if self._execution_backend.backend_name != "mock":
            raise AutomationExecutionError(
                "Rollback is supported only for the mock execution backend in the MVP"
            )

        before_state = self._state_repository.get_state(device_name)
        before = self._renderer.render_running_config(before_state)

        try:
            restored_state = self._state_repository.restore_snapshot(device_name, snapshot_id)
        except DeviceNotFoundError as exc:
            self._journal_repository.add(
                OperationRecord(
                    operation="rollback",
                    device_name=device_name,
                    request_id=get_request_id(),
                    backend="mock",
                    status="failed",
                    detail=str(exc),
                )
            )
            raise

        after = self._renderer.render_running_config(restored_state)
        result = RollbackExecutionResult(
            device_name=device_name,
            snapshot_id=snapshot_id,
            changed=before != after,
            before=before,
            after=after,
            backend="mock",
        )
        self._journal_repository.add(
            OperationRecord(
                operation="rollback",
                device_name=device_name,
                request_id=get_request_id(),
                backend="mock",
                status="success",
                changed=result.changed,
                detail=f"Restored snapshot {snapshot_id}",
                snapshot_id=snapshot_id,
            )
        )
        return result

    def list_operations(
        self,
        device_name: str | None = None,
        operation: str | None = None,
        status: str | None = None,
        request_id: str | None = None,
        limit: int | None = None,
    ) -> list[OperationRecord]:
        return self._journal_repository.list_records(
            device_name=device_name,
            operation=operation,
            status=status,
            request_id=request_id,
            limit=limit,
        )

    def summarize_operations(
        self,
        device_name: str | None = None,
        operation: str | None = None,
        status: str | None = None,
        request_id: str | None = None,
    ) -> OperationSummary:
        return self._journal_repository.build_summary(
            device_name=device_name,
            operation=operation,
            status=status,
            request_id=request_id,
        )

    def reset_demo_state(self) -> DemoResetResponse:
        if self._execution_backend.backend_name != "mock":
            raise AutomationExecutionError(
                "Demo reset is supported only for the mock execution backend in the MVP"
            )

        devices_reset, snapshots_cleared = self._state_repository.reset()
        operations_cleared = self._journal_repository.reset()
        return DemoResetResponse(
            execution_backend=self._execution_backend.backend_name,
            inventory_backend=settings.inventory_backend,
            devices_reset=devices_reset,
            snapshots_cleared=snapshots_cleared,
            operations_cleared=operations_cleared,
        )

    def get_operation(self, operation_id: str) -> OperationRecord:
        return self._journal_repository.get_record(operation_id)

    def _ensure_mock_compliance_supported(self) -> None:
        if self._execution_backend.backend_name != "mock":
            raise AutomationExecutionError(
                "Compliance checks are supported only for the mock execution backend in the MVP"
            )

    def _build_runtime_nornir(self, device_name: str):
        self._nornir = build_nornir(self._repository.list_devices())
        if device_name not in self._nornir.inventory.hosts:
            raise AutomationExecutionError(
                f"Device '{device_name}' is not present in the active Nornir inventory"
            )
        return self._nornir

    def _select_devices(self, selector: DeviceSelector) -> list[MockRouter]:
        devices = self._reachability_service.annotate_devices(self._repository.list_devices())
        if selector.site is not None:
            devices = [device for device in devices if device.site == selector.site]
        if selector.role is not None:
            devices = [device for device in devices if device.role == selector.role]
        if selector.status is not None:
            devices = [device for device in devices if device.status == selector.status]
        if selector.vendor is not None:
            devices = [device for device in devices if device.vendor.lower() == selector.vendor.lower()]
        return devices

    def _ensure_devices_matched(
        self,
        devices: list[MockRouter],
        selector: DeviceSelector,
    ) -> None:
        if devices:
            return
        filters = {
            key: value
            for key, value in selector.model_dump().items()
            if value is not None
        }
        if not filters:
            raise DeviceNotFoundError("No devices matched the empty selector")
        rendered_filters = ", ".join(f"{key}={value}" for key, value in filters.items())
        raise DeviceNotFoundError(f"No devices matched selector: {rendered_filters}")

    @staticmethod
    def _to_resolved_target(device: MockRouter) -> ResolvedDeviceTarget:
        return ResolvedDeviceTarget(
            name=device.name,
            site=device.site,
            role=device.role,
            status=device.status,
            vendor=device.vendor,
            management_ip=device.management_ip,
        )

    def _build_drift(
        self,
        current_state: MockDeviceRuntimeState,
        expected_state: MockDeviceRuntimeState,
    ) -> list[ConfigurationDriftItem]:
        drift: list[ConfigurationDriftItem] = []

        self._append_drift(drift, "hostname", current_state.hostname, expected_state.hostname)
        self._append_drift(
            drift,
            "domain_name",
            current_state.domain_name,
            expected_state.domain_name,
        )
        self._append_drift(
            drift,
            "banner_motd",
            current_state.banner_motd,
            expected_state.banner_motd,
        )
        self._append_drift(
            drift,
            "ntp_server",
            current_state.ntp_server,
            expected_state.ntp_server,
        )

        current_interfaces = {interface.name.lower(): interface for interface in current_state.interfaces}
        expected_interfaces = {interface.name.lower(): interface for interface in expected_state.interfaces}
        interface_names = list(dict.fromkeys([*expected_interfaces.keys(), *current_interfaces.keys()]))

        for interface_name in interface_names:
            current_interface = current_interfaces.get(interface_name)
            expected_interface = expected_interfaces.get(interface_name)
            display_name = (
                expected_interface.name
                if expected_interface is not None
                else current_interface.name
            )
            if current_interface is None:
                drift.append(
                    ConfigurationDriftItem(
                        path=f"interfaces.{display_name}",
                        current="absent",
                        desired="present",
                    )
                )
                continue
            if expected_interface is None:
                drift.append(
                    ConfigurationDriftItem(
                        path=f"interfaces.{display_name}",
                        current="present",
                        desired="absent",
                    )
                )
                continue
            self._append_interface_drift(drift, display_name, current_interface, expected_interface)

        return drift

    @staticmethod
    def _append_interface_drift(
        drift: list[ConfigurationDriftItem],
        interface_name: str,
        current_interface: InterfaceSpec,
        expected_interface: InterfaceSpec,
    ) -> None:
        AutomationService._append_drift(
            drift,
            f"interfaces.{interface_name}.description",
            current_interface.description,
            expected_interface.description,
        )
        AutomationService._append_drift(
            drift,
            f"interfaces.{interface_name}.ipv4_address",
            current_interface.ipv4_address,
            expected_interface.ipv4_address,
        )
        AutomationService._append_drift(
            drift,
            f"interfaces.{interface_name}.enabled",
            current_interface.enabled,
            expected_interface.enabled,
        )

    @staticmethod
    def _build_preview_summary(items: list[BatchPreviewItem]) -> BatchPreviewSummary:
        return BatchPreviewSummary(
            total_items=len(items),
            successful_items=sum(1 for item in items if item.status == "success"),
            failed_items=sum(1 for item in items if item.status == "failed"),
        )

    @staticmethod
    def _build_compliance_summary(items: list[BatchComplianceItem]) -> BatchComplianceSummary:
        successful_items = [item for item in items if item.status == "success" and item.report is not None]
        return BatchComplianceSummary(
            total_items=len(items),
            successful_items=len(successful_items),
            failed_items=sum(1 for item in items if item.status == "failed"),
            compliant_items=sum(1 for item in successful_items if item.report.compliant),
            drifted_items=sum(1 for item in successful_items if not item.report.compliant),
        )

    @staticmethod
    def _build_execution_summary(items: list[BatchExecutionItem]) -> BatchExecutionSummary:
        successful_items = [item for item in items if item.status == "success" and item.result is not None]
        return BatchExecutionSummary(
            total_items=len(items),
            successful_items=len(successful_items),
            failed_items=sum(1 for item in items if item.status == "failed"),
            changed_items=sum(1 for item in successful_items if item.result.changed),
            unchanged_items=sum(1 for item in successful_items if not item.result.changed),
        )

    @staticmethod
    def _append_drift(
        drift: list[ConfigurationDriftItem],
        path: str,
        current: str | bool | None,
        desired: str | bool | None,
    ) -> None:
        if current == desired:
            return
        drift.append(
            ConfigurationDriftItem(
                path=path,
                current=current,
                desired=desired,
            )
        )
