from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import (
    get_automation_service,
    get_current_user,
    get_database_service,
    get_device_service,
    get_diagnostics_service,
    get_job_service,
    get_preflight_service,
    require_admin_role,
    require_automation_api_key,
    require_operator_role,
)
from app.automation.models import (
    BaseConfigurationComplianceReport,
    BaseConfigurationExecutionResult,
    BaseConfigurationOverrides,
    BaseConfigurationPreview,
    BaseConfigurationProfile,
    BaseConfigurationRequest,
    AutomationJobRequest,
    BatchBaseConfigurationRequest,
    BatchComplianceResponse,
    BatchExecutionResponse,
    BatchPreviewResponse,
    BatchProfileConfigurationRequest,
    DemoResetResponse,
    DeviceSelectionResponse,
    DeviceSelector,
    DeviceSnapshotSummary,
    DiagnosticsReport,
    OperationRecord,
    OperationSummary,
    PreflightReport,
    RollbackExecutionResult,
    RunningConfigResponse,
    SelectionBaseConfigurationRequest,
    SelectionProfileConfigurationRequest,
)
from app.db.models import AutomationJobRecord, DatabaseStatus, DatabaseUser
from app.domain.exceptions import (
    AutomationExecutionError,
    DeviceNotFoundError,
    DeviceUnavailableError,
)
from app.domain.models import MockRouter
from app.services.automation_service import AutomationService
from app.services.database_service import DatabaseService
from app.services.device_service import DeviceService
from app.services.diagnostics_service import DiagnosticsService
from app.services.job_service import JobService
from app.services.preflight_service import PreflightService

router = APIRouter()
OperationType = Literal["preview", "apply", "rollback", "compliance"]
OperationStatus = Literal["success", "failed"]
DeviceRole = Literal["edge", "distribution", "core"]
DeviceReachability = Literal["reachable", "maintenance", "unreachable"]


def raise_not_found(exc: DeviceNotFoundError) -> None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=str(exc),
    ) from exc


def raise_conflict(exc: DeviceUnavailableError) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=str(exc),
    ) from exc


def raise_execution_error(exc: AutomationExecutionError) -> None:
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=str(exc),
    ) from exc


@router.get("/health", tags=["system"], summary="Service health check")
async def health() -> dict:
    """Liveness probe for the API."""
    return {"status": "ok"}


@router.get("/system/database", tags=["system"], summary="Database status")
async def database_status(
    database_service: DatabaseService = Depends(get_database_service),
) -> DatabaseStatus:
    """Returns SQLite readiness and seeded RBAC table counters."""
    return database_service.get_status()


@router.get("/system/auth/me", tags=["system"], summary="Current RBAC user")
async def current_user_info(
    current_user: DatabaseUser = Depends(get_current_user),
) -> DatabaseUser:
    """Returns the currently authenticated RBAC user when RBAC is enabled."""
    return current_user


@router.get("/devices", tags=["devices"], summary="List mock routers")
async def list_devices(
    site: str | None = Query(default=None),
    role: DeviceRole | None = Query(default=None),
    status_filter: DeviceReachability | None = Query(default=None, alias="status"),
    vendor: str | None = Query(default=None),
    device_service: DeviceService = Depends(get_device_service),
) -> list[MockRouter]:
    """Returns the test inventory used during early MVP development."""
    return device_service.list_devices(
        site=site,
        role=role,
        status=status_filter,
        vendor=vendor,
    )


@router.get("/devices/{device_name}", tags=["devices"], summary="Get mock router")
async def get_device(
    device_name: str,
    device_service: DeviceService = Depends(get_device_service),
) -> MockRouter:
    """Returns a single mocked router definition."""
    try:
        return device_service.get_device(device_name)
    except DeviceNotFoundError as exc:
        raise_not_found(exc)


@router.post(
    "/automation/selection/resolve",
    tags=["automation"],
    summary="Resolve devices by inventory selector",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def resolve_device_targets(
    selector: DeviceSelector,
    device_service: DeviceService = Depends(get_device_service),
) -> DeviceSelectionResponse:
    """Returns devices that match the requested inventory selector."""
    return device_service.resolve_devices(selector)


@router.post(
    "/automation/preflight",
    tags=["automation"],
    summary="Run readiness checks for the current environment",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def preflight_environment(
    selector: DeviceSelector | None = None,
    preflight_service: PreflightService = Depends(get_preflight_service),
) -> PreflightReport:
    """Checks inventory, execution backend, and target readiness before automation runs."""
    return preflight_service.build_report(selector)


@router.post(
    "/automation/diagnostics",
    tags=["automation"],
    summary="Run active diagnostics for inventory and execution integrations",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def diagnostics_environment(
    selector: DeviceSelector | None = None,
    diagnostics_service: DiagnosticsService = Depends(get_diagnostics_service),
) -> DiagnosticsReport:
    """Actively probes external integrations before a real stand deployment."""
    return diagnostics_service.build_report(selector)


@router.post(
    "/automation/demo/reset",
    tags=["automation"],
    summary="Reset mock demo state and operation history",
    dependencies=[Depends(require_automation_api_key), Depends(require_admin_role)],
)
async def reset_demo_state(
    automation_service: AutomationService = Depends(get_automation_service),
) -> DemoResetResponse:
    """Clears mock running state, snapshots, and journal data before a repeated demo run."""
    try:
        return automation_service.reset_demo_state()
    except AutomationExecutionError as exc:
        raise_execution_error(exc)


@router.post(
    "/automation/jobs",
    tags=["automation"],
    summary="Create async automation job",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def create_automation_job(
    job_request: AutomationJobRequest,
    job_service: JobService = Depends(get_job_service),
) -> AutomationJobRecord:
    """Creates a queued automation job record for a future Celery worker."""
    try:
        return job_service.create_job(job_request)
    except DeviceNotFoundError as exc:
        raise_not_found(exc)


@router.get(
    "/automation/jobs",
    tags=["automation"],
    summary="List async automation jobs",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def list_automation_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    job_service: JobService = Depends(get_job_service),
) -> list[AutomationJobRecord]:
    """Returns the latest queued or processed automation jobs."""
    return job_service.list_jobs(limit=limit)


@router.get(
    "/automation/jobs/{job_id}",
    tags=["automation"],
    summary="Get async automation job",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def get_automation_job(
    job_id: str,
    job_service: JobService = Depends(get_job_service),
) -> AutomationJobRecord:
    """Returns one queued or processed automation job record."""
    try:
        return job_service.get_job(job_id)
    except DeviceNotFoundError as exc:
        raise_not_found(exc)


@router.post(
    "/automation/jobs/{job_id}/execute",
    tags=["automation"],
    summary="Execute database-backed automation job",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def execute_automation_job(
    job_id: str,
    job_service: JobService = Depends(get_job_service),
    automation_service: AutomationService = Depends(get_automation_service),
) -> AutomationJobRecord:
    """Executes one queued job immediately when database backend is used."""
    try:
        return job_service.execute_job(job_id, automation_service)
    except DeviceNotFoundError as exc:
        raise_not_found(exc)
    except AutomationExecutionError as exc:
        raise_execution_error(exc)


@router.post(
    "/automation/jobs/{job_id}/retry",
    tags=["automation"],
    summary="Retry automation job",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def retry_automation_job(
    job_id: str,
    job_service: JobService = Depends(get_job_service),
) -> AutomationJobRecord:
    """Retries a failed or queued automation job."""
    try:
        return job_service.retry_job(job_id)
    except DeviceNotFoundError as exc:
        raise_not_found(exc)
    except AutomationExecutionError as exc:
        raise_execution_error(exc)


@router.get(
    "/automation/profiles",
    tags=["automation"],
    summary="List configuration profiles",
)
async def list_profiles(
    automation_service: AutomationService = Depends(get_automation_service),
) -> list[BaseConfigurationProfile]:
    """Returns reusable baseline configuration profiles."""
    return automation_service.list_profiles()


@router.get(
    "/automation/profiles/{profile_name}",
    tags=["automation"],
    summary="Get configuration profile",
)
async def get_profile(
    profile_name: str,
    automation_service: AutomationService = Depends(get_automation_service),
) -> BaseConfigurationProfile:
    """Returns a single reusable configuration profile."""
    try:
        return automation_service.get_profile(profile_name)
    except DeviceNotFoundError as exc:
        raise_not_found(exc)


@router.post(
    "/automation/devices/{device_name}/base-config/preview",
    tags=["automation"],
    summary="Preview base configuration commands",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def preview_base_configuration(
    device_name: str,
    request: BaseConfigurationRequest,
    automation_service: AutomationService = Depends(get_automation_service),
) -> BaseConfigurationPreview:
    """Builds a base configuration preview for a mocked router."""
    try:
        return automation_service.generate_base_configuration(device_name, request)
    except DeviceNotFoundError as exc:
        raise_not_found(exc)


@router.post(
    "/automation/batch/base-config/preview",
    tags=["automation"],
    summary="Preview base configuration for multiple devices",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def preview_base_configuration_batch(
    batch_request: BatchBaseConfigurationRequest,
    automation_service: AutomationService = Depends(get_automation_service),
) -> BatchPreviewResponse:
    """Builds base configuration previews for multiple devices at once."""
    return automation_service.generate_base_configuration_batch(batch_request)


@router.post(
    "/automation/devices/{device_name}/base-config/profiles/{profile_name}/preview",
    tags=["automation"],
    summary="Preview base configuration from a profile",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def preview_base_configuration_from_profile(
    device_name: str,
    profile_name: str,
    overrides: BaseConfigurationOverrides,
    automation_service: AutomationService = Depends(get_automation_service),
) -> BaseConfigurationPreview:
    """Builds a base configuration preview from a reusable profile."""
    try:
        return automation_service.generate_base_configuration_from_profile(
            device_name,
            profile_name,
            overrides,
        )
    except DeviceNotFoundError as exc:
        raise_not_found(exc)


@router.post(
    "/automation/selection/base-config/preview",
    tags=["automation"],
    summary="Preview base configuration for selector-matched devices",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def preview_base_configuration_for_selection(
    selection_request: SelectionBaseConfigurationRequest,
    automation_service: AutomationService = Depends(get_automation_service),
) -> BatchPreviewResponse:
    """Resolves targets by selector and builds previews for all matched devices."""
    try:
        return automation_service.generate_base_configuration_for_selection(selection_request)
    except DeviceNotFoundError as exc:
        raise_not_found(exc)


@router.post(
    "/automation/selection/base-config/profiles/{profile_name}/preview",
    tags=["automation"],
    summary="Preview profile-based configuration for selector-matched devices",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def preview_base_configuration_from_profile_for_selection(
    profile_name: str,
    selection_request: SelectionProfileConfigurationRequest,
    automation_service: AutomationService = Depends(get_automation_service),
) -> BatchPreviewResponse:
    """Resolves targets by selector and builds profile-based previews for matches."""
    try:
        return automation_service.generate_base_configuration_from_profile_for_selection(
            profile_name,
            selection_request,
        )
    except DeviceNotFoundError as exc:
        raise_not_found(exc)


@router.post(
    "/automation/batch/base-config/profiles/{profile_name}/preview",
    tags=["automation"],
    summary="Preview profile-based configuration for multiple devices",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def preview_base_configuration_batch_from_profile(
    profile_name: str,
    batch_request: BatchProfileConfigurationRequest,
    automation_service: AutomationService = Depends(get_automation_service),
) -> BatchPreviewResponse:
    """Builds profile-based previews for multiple devices at once."""
    return automation_service.generate_base_configuration_batch_from_profile(
        profile_name,
        batch_request,
    )


@router.post(
    "/automation/devices/{device_name}/base-config/compliance",
    tags=["automation"],
    summary="Check configuration compliance against a desired base config",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def check_base_configuration_compliance(
    device_name: str,
    request: BaseConfigurationRequest,
    automation_service: AutomationService = Depends(get_automation_service),
) -> BaseConfigurationComplianceReport:
    """Compares current mock state with the desired base configuration."""
    try:
        return automation_service.check_base_configuration_compliance(
            device_name,
            request,
        )
    except DeviceNotFoundError as exc:
        raise_not_found(exc)
    except AutomationExecutionError as exc:
        raise_execution_error(exc)


@router.post(
    "/automation/devices/{device_name}/base-config/profiles/{profile_name}/compliance",
    tags=["automation"],
    summary="Check profile-based configuration compliance",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def check_base_configuration_compliance_from_profile(
    device_name: str,
    profile_name: str,
    overrides: BaseConfigurationOverrides,
    automation_service: AutomationService = Depends(get_automation_service),
) -> BaseConfigurationComplianceReport:
    """Compares current mock state with the desired profile-based configuration."""
    try:
        return automation_service.check_base_configuration_compliance_from_profile(
            device_name,
            profile_name,
            overrides,
        )
    except DeviceNotFoundError as exc:
        raise_not_found(exc)
    except AutomationExecutionError as exc:
        raise_execution_error(exc)


@router.post(
    "/automation/batch/base-config/compliance",
    tags=["automation"],
    summary="Check configuration compliance for multiple devices",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def check_base_configuration_compliance_batch(
    batch_request: BatchBaseConfigurationRequest,
    automation_service: AutomationService = Depends(get_automation_service),
) -> BatchComplianceResponse:
    """Compares current mock state with the desired base config for multiple devices."""
    return automation_service.check_base_configuration_compliance_batch(batch_request)


@router.post(
    "/automation/batch/base-config/profiles/{profile_name}/compliance",
    tags=["automation"],
    summary="Check profile-based compliance for multiple devices",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def check_base_configuration_compliance_batch_from_profile(
    profile_name: str,
    batch_request: BatchProfileConfigurationRequest,
    automation_service: AutomationService = Depends(get_automation_service),
) -> BatchComplianceResponse:
    """Compares current mock state with the desired profile-based config for multiple devices."""
    return automation_service.check_base_configuration_compliance_batch_from_profile(
        profile_name,
        batch_request,
    )


@router.post(
    "/automation/selection/base-config/compliance",
    tags=["automation"],
    summary="Check compliance for devices selected from inventory filters",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def check_base_configuration_compliance_for_selection(
    selection_request: SelectionBaseConfigurationRequest,
    automation_service: AutomationService = Depends(get_automation_service),
) -> BatchComplianceResponse:
    """Resolves targets by selector and checks compliance for all matched devices."""
    try:
        return automation_service.check_base_configuration_compliance_for_selection(
            selection_request,
        )
    except DeviceNotFoundError as exc:
        raise_not_found(exc)
    except AutomationExecutionError as exc:
        raise_execution_error(exc)


@router.post(
    "/automation/selection/base-config/profiles/{profile_name}/compliance",
    tags=["automation"],
    summary="Check profile-based compliance for selector-matched devices",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def check_base_configuration_compliance_from_profile_for_selection(
    profile_name: str,
    selection_request: SelectionProfileConfigurationRequest,
    automation_service: AutomationService = Depends(get_automation_service),
) -> BatchComplianceResponse:
    """Resolves targets by selector and checks profile-based compliance for matches."""
    try:
        return automation_service.check_base_configuration_compliance_from_profile_for_selection(
            profile_name,
            selection_request,
        )
    except DeviceNotFoundError as exc:
        raise_not_found(exc)
    except AutomationExecutionError as exc:
        raise_execution_error(exc)


@router.post(
    "/automation/devices/{device_name}/base-config/apply",
    tags=["automation"],
    summary="Apply base configuration to a mock router",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def apply_base_configuration(
    device_name: str,
    request: BaseConfigurationRequest,
    dry_run: bool = Query(default=False),
    automation_service: AutomationService = Depends(get_automation_service),
) -> BaseConfigurationExecutionResult:
    """Executes the selected workflow backend for configuration deployment."""
    try:
        return automation_service.deploy_base_configuration(
            device_name,
            request,
            dry_run=dry_run,
        )
    except DeviceNotFoundError as exc:
        raise_not_found(exc)
    except DeviceUnavailableError as exc:
        raise_conflict(exc)
    except AutomationExecutionError as exc:
        raise_execution_error(exc)


@router.post(
    "/automation/batch/base-config/apply",
    tags=["automation"],
    summary="Apply base configuration to multiple devices",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def apply_base_configuration_batch(
    batch_request: BatchBaseConfigurationRequest,
    dry_run: bool = Query(default=False),
    automation_service: AutomationService = Depends(get_automation_service),
) -> BatchExecutionResponse:
    """Executes configuration deployment for multiple devices at once."""
    return automation_service.deploy_base_configuration_batch(
        batch_request,
        dry_run=dry_run,
    )


@router.post(
    "/automation/devices/{device_name}/base-config/profiles/{profile_name}/apply",
    tags=["automation"],
    summary="Apply base configuration from a profile",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def apply_base_configuration_from_profile(
    device_name: str,
    profile_name: str,
    overrides: BaseConfigurationOverrides,
    dry_run: bool = Query(default=False),
    automation_service: AutomationService = Depends(get_automation_service),
) -> BaseConfigurationExecutionResult:
    """Executes configuration deployment using a reusable profile and overrides."""
    try:
        return automation_service.deploy_base_configuration_from_profile(
            device_name,
            profile_name,
            overrides,
            dry_run=dry_run,
        )
    except DeviceNotFoundError as exc:
        raise_not_found(exc)
    except DeviceUnavailableError as exc:
        raise_conflict(exc)
    except AutomationExecutionError as exc:
        raise_execution_error(exc)


@router.post(
    "/automation/batch/base-config/profiles/{profile_name}/apply",
    tags=["automation"],
    summary="Apply profile-based configuration to multiple devices",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def apply_base_configuration_batch_from_profile(
    profile_name: str,
    batch_request: BatchProfileConfigurationRequest,
    dry_run: bool = Query(default=False),
    automation_service: AutomationService = Depends(get_automation_service),
) -> BatchExecutionResponse:
    """Executes profile-based deployment for multiple devices at once."""
    return automation_service.deploy_base_configuration_batch_from_profile(
        profile_name,
        batch_request,
        dry_run=dry_run,
    )


@router.post(
    "/automation/selection/base-config/apply",
    tags=["automation"],
    summary="Apply base configuration for selector-matched devices",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def apply_base_configuration_for_selection(
    selection_request: SelectionBaseConfigurationRequest,
    dry_run: bool = Query(default=False),
    automation_service: AutomationService = Depends(get_automation_service),
) -> BatchExecutionResponse:
    """Resolves targets by selector and executes deployment for all matched devices."""
    try:
        return automation_service.deploy_base_configuration_for_selection(
            selection_request,
            dry_run=dry_run,
        )
    except DeviceNotFoundError as exc:
        raise_not_found(exc)


@router.post(
    "/automation/selection/base-config/profiles/{profile_name}/apply",
    tags=["automation"],
    summary="Apply profile-based configuration for selector-matched devices",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def apply_base_configuration_from_profile_for_selection(
    profile_name: str,
    selection_request: SelectionProfileConfigurationRequest,
    dry_run: bool = Query(default=False),
    automation_service: AutomationService = Depends(get_automation_service),
) -> BatchExecutionResponse:
    """Resolves targets by selector and executes profile-based deployment for matches."""
    try:
        return automation_service.deploy_base_configuration_from_profile_for_selection(
            profile_name,
            selection_request,
            dry_run=dry_run,
        )
    except DeviceNotFoundError as exc:
        raise_not_found(exc)


@router.get(
    "/automation/devices/{device_name}/running-config",
    tags=["automation"],
    summary="Get current running configuration",
)
async def get_running_config(
    device_name: str,
    automation_service: AutomationService = Depends(get_automation_service),
) -> RunningConfigResponse:
    """Returns the current running configuration from the selected backend."""
    try:
        return RunningConfigResponse(
            device_name=device_name,
            lines=automation_service.get_running_config(device_name),
        )
    except DeviceNotFoundError as exc:
        raise_not_found(exc)
    except AutomationExecutionError as exc:
        raise_execution_error(exc)


@router.get(
    "/automation/devices/{device_name}/snapshots",
    tags=["automation"],
    summary="List saved configuration snapshots",
)
async def list_snapshots(
    device_name: str,
    automation_service: AutomationService = Depends(get_automation_service),
) -> list[DeviceSnapshotSummary]:
    """Returns saved snapshots for a mock device."""
    try:
        return automation_service.list_snapshots(device_name)
    except DeviceNotFoundError as exc:
        raise_not_found(exc)


@router.post(
    "/automation/devices/{device_name}/rollback/{snapshot_id}",
    tags=["automation"],
    summary="Rollback device configuration to a saved snapshot",
    dependencies=[Depends(require_automation_api_key), Depends(require_operator_role)],
)
async def rollback_to_snapshot(
    device_name: str,
    snapshot_id: str,
    automation_service: AutomationService = Depends(get_automation_service),
) -> RollbackExecutionResult:
    """Restores a mock device running-config from a saved snapshot."""
    try:
        return automation_service.rollback_to_snapshot(device_name, snapshot_id)
    except DeviceNotFoundError as exc:
        raise_not_found(exc)
    except AutomationExecutionError as exc:
        raise_execution_error(exc)


@router.get(
    "/automation/operations",
    tags=["automation"],
    summary="List automation operation history",
)
async def list_operations(
    device_name: str | None = Query(default=None),
    operation: OperationType | None = Query(default=None),
    status_filter: OperationStatus | None = Query(default=None, alias="status"),
    request_id: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=500),
    automation_service: AutomationService = Depends(get_automation_service),
) -> list[OperationRecord]:
    """Returns recorded automation operations with optional filtering."""
    return automation_service.list_operations(
        device_name=device_name,
        operation=operation,
        status=status_filter,
        request_id=request_id,
        limit=limit,
    )


@router.get(
    "/automation/operations/summary",
    tags=["automation"],
    summary="Get aggregate automation operation counters",
)
async def summarize_operations(
    device_name: str | None = Query(default=None),
    operation: OperationType | None = Query(default=None),
    status_filter: OperationStatus | None = Query(default=None, alias="status"),
    request_id: str | None = Query(default=None),
    automation_service: AutomationService = Depends(get_automation_service),
) -> OperationSummary:
    """Returns aggregate counters for the filtered operation history."""
    return automation_service.summarize_operations(
        device_name=device_name,
        operation=operation,
        status=status_filter,
        request_id=request_id,
    )


@router.get(
    "/automation/operations/{operation_id}",
    tags=["automation"],
    summary="Get a single automation operation",
)
async def get_operation(
    operation_id: str,
    automation_service: AutomationService = Depends(get_automation_service),
) -> OperationRecord:
    """Returns one automation operation from the in-memory journal."""
    try:
        return automation_service.get_operation(operation_id)
    except DeviceNotFoundError as exc:
        raise_not_found(exc)


api_router = APIRouter()
api_router.include_router(router)
