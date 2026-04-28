"""DTOs used by network automation workflows."""

import re
from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.models import InterfaceSpec, MockRouter

HOSTNAME_PATTERN = re.compile(
    r"^(?=.{1,63}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
DOMAIN_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*$"
)


def _validate_hostname(value: str) -> str:
    normalized = value.strip()
    if not HOSTNAME_PATTERN.fullmatch(normalized):
        raise ValueError(
            "Hostname must be 1-63 chars, use letters, digits, and hyphens, and must not start or end with a hyphen"
        )
    return normalized


def _validate_optional_domain_name(value: str | None) -> str | None:
    if value is None:
        return value
    normalized = value.strip()
    if not DOMAIN_PATTERN.fullmatch(normalized):
        raise ValueError("Domain name must be a valid DNS-style name")
    return normalized


def _validate_optional_ntp_server(value: str | None) -> str | None:
    if value is None:
        return value
    ip_address(value)
    return value


def _ensure_unique_interface_names(interfaces: list[InterfaceSpec]) -> list[InterfaceSpec]:
    seen: set[str] = set()
    for interface in interfaces:
        normalized_name = interface.name.lower()
        if normalized_name in seen:
            raise ValueError("Interface names must be unique within one configuration request")
        seen.add(normalized_name)
    return interfaces


def _validate_optional_filter(value: str | None) -> str | None:
    if value is None:
        return value
    normalized = value.strip()
    if not normalized:
        raise ValueError("Filter value must not be empty")
    return normalized


class BaseConfigurationRequest(BaseModel):
    """Input for generating or deploying a minimal router configuration."""

    hostname: str
    domain_name: str = "lab.local"
    banner_motd: str = "Managed by NetAuto"
    ntp_server: str | None = None
    interfaces: list[InterfaceSpec] = Field(default_factory=list)

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, value: str) -> str:
        return _validate_hostname(value)

    @field_validator("domain_name")
    @classmethod
    def validate_domain_name(cls, value: str) -> str:
        validated = _validate_optional_domain_name(value)
        assert validated is not None
        return validated

    @field_validator("banner_motd")
    @classmethod
    def validate_banner_motd(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Banner MOTD must not be empty")
        return normalized

    @field_validator("ntp_server")
    @classmethod
    def validate_ntp_server(cls, value: str | None) -> str | None:
        return _validate_optional_ntp_server(value)

    @field_validator("interfaces")
    @classmethod
    def validate_interfaces(cls, value: list[InterfaceSpec]) -> list[InterfaceSpec]:
        return _ensure_unique_interface_names(value)


class BaseConfigurationOverrides(BaseModel):
    """Profile overrides merged into a final configuration request."""

    hostname: str
    domain_name: str | None = None
    banner_motd: str | None = None
    ntp_server: str | None = None
    interfaces: list[InterfaceSpec] = Field(default_factory=list)

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, value: str) -> str:
        return _validate_hostname(value)

    @field_validator("domain_name")
    @classmethod
    def validate_domain_name(cls, value: str | None) -> str | None:
        return _validate_optional_domain_name(value)

    @field_validator("banner_motd")
    @classmethod
    def validate_banner_motd(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("Banner MOTD must not be empty")
        return normalized

    @field_validator("ntp_server")
    @classmethod
    def validate_ntp_server(cls, value: str | None) -> str | None:
        return _validate_optional_ntp_server(value)

    @field_validator("interfaces")
    @classmethod
    def validate_interfaces(cls, value: list[InterfaceSpec]) -> list[InterfaceSpec]:
        return _ensure_unique_interface_names(value)


class BaseConfigurationProfile(BaseModel):
    """Reusable baseline profile for standardized device configuration."""

    name: str
    description: str
    domain_name: str
    banner_motd: str
    ntp_server: str | None = None
    interfaces: list[InterfaceSpec] = Field(default_factory=list)

    @field_validator("domain_name")
    @classmethod
    def validate_domain_name(cls, value: str) -> str:
        validated = _validate_optional_domain_name(value)
        assert validated is not None
        return validated

    @field_validator("banner_motd")
    @classmethod
    def validate_banner_motd(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Banner MOTD must not be empty")
        return normalized

    @field_validator("ntp_server")
    @classmethod
    def validate_ntp_server(cls, value: str | None) -> str | None:
        return _validate_optional_ntp_server(value)

    @field_validator("interfaces")
    @classmethod
    def validate_interfaces(cls, value: list[InterfaceSpec]) -> list[InterfaceSpec]:
        return _ensure_unique_interface_names(value)


class BaseConfigurationPreview(BaseModel):
    """Generated command preview before execution."""

    device_name: str
    commands: list[str]


class BatchBaseConfigurationItemRequest(BaseModel):
    """One device entry for a batch raw configuration operation."""

    device_name: str
    request: BaseConfigurationRequest

    @field_validator("device_name")
    @classmethod
    def validate_device_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Device name must not be empty")
        return normalized


class BatchProfileConfigurationItemRequest(BaseModel):
    """One device entry for a batch profile-based configuration operation."""

    device_name: str
    overrides: BaseConfigurationOverrides

    @field_validator("device_name")
    @classmethod
    def validate_device_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Device name must not be empty")
        return normalized


class BatchBaseConfigurationRequest(BaseModel):
    """Batch payload for raw configuration preview or apply."""

    items: list[BatchBaseConfigurationItemRequest] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_items(self) -> "BatchBaseConfigurationRequest":
        if not self.items:
            raise ValueError("Batch request must contain at least one device")
        device_names = [item.device_name.lower() for item in self.items]
        if len(device_names) != len(set(device_names)):
            raise ValueError("Device names in a batch request must be unique")
        return self


class BatchProfileConfigurationRequest(BaseModel):
    """Batch payload for profile-based configuration preview or apply."""

    items: list[BatchProfileConfigurationItemRequest] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_items(self) -> "BatchProfileConfigurationRequest":
        if not self.items:
            raise ValueError("Batch request must contain at least one device")
        device_names = [item.device_name.lower() for item in self.items]
        if len(device_names) != len(set(device_names)):
            raise ValueError("Device names in a batch request must be unique")
        return self


class DeviceSelector(BaseModel):
    """Filter set used to resolve target devices from inventory."""

    site: str | None = None
    role: Literal["edge", "distribution", "core"] | None = None
    status: Literal["reachable", "maintenance", "unreachable"] | None = None
    vendor: str | None = None

    @field_validator("site", "vendor")
    @classmethod
    def validate_optional_filter(cls, value: str | None) -> str | None:
        return _validate_optional_filter(value)


class ResolvedDeviceTarget(BaseModel):
    """Public-safe representation of a resolved device target."""

    name: str
    site: str
    role: Literal["edge", "distribution", "core"]
    status: Literal["reachable", "maintenance", "unreachable"]
    vendor: str
    management_ip: str


class DeviceSelectionResponse(BaseModel):
    """Resolved set of devices that match a selector."""

    total_devices: int
    devices: list[ResolvedDeviceTarget] = Field(default_factory=list)


class SelectionBaseConfigurationRequest(BaseModel):
    """Selection-based request for raw base-config automation."""

    selector: DeviceSelector
    request: BaseConfigurationRequest


class SelectionProfileConfigurationRequest(BaseModel):
    """Selection-based request for profile-based automation."""

    selector: DeviceSelector
    overrides: BaseConfigurationOverrides


class PreflightCheck(BaseModel):
    """One readiness/preflight check result."""

    name: str
    status: Literal["success", "failed"]
    detail: str
    meta: dict[str, str | int | bool | None] = Field(default_factory=dict)


class PreflightReport(BaseModel):
    """Aggregated readiness report for the current MVP environment."""

    inventory_backend: Literal["mock", "netbox"]
    execution_backend: Literal["mock", "netmiko"]
    ready: bool
    matched_devices: int
    reachable_devices: int
    maintenance_devices: int
    unreachable_devices: int
    checks: list[PreflightCheck] = Field(default_factory=list)


class DiagnosticsCheck(BaseModel):
    """One active diagnostics probe result."""

    name: str
    status: Literal["success", "failed"]
    detail: str
    meta: dict[str, str | int | bool | None] = Field(default_factory=dict)


class DiagnosticsReport(BaseModel):
    """Aggregated diagnostics report for external integrations."""

    inventory_backend: Literal["mock", "netbox"]
    execution_backend: Literal["mock", "netmiko"]
    ok: bool
    matched_devices: int
    reachable_devices: int
    maintenance_devices: int
    unreachable_devices: int
    checks: list[DiagnosticsCheck] = Field(default_factory=list)


class BatchPreviewItem(BaseModel):
    """One batch preview result entry."""

    device_name: str
    status: Literal["success", "failed"]
    preview: BaseConfigurationPreview | None = None
    detail: str | None = None


class BatchPreviewSummary(BaseModel):
    """Aggregate counters for batch preview results."""

    total_items: int
    successful_items: int
    failed_items: int


class BatchPreviewResponse(BaseModel):
    """Collection of batch preview results."""

    items: list[BatchPreviewItem] = Field(default_factory=list)
    summary: BatchPreviewSummary


class MockDeviceRuntimeState(BaseModel):
    """Current mocked running state of a network device."""

    device_name: str
    hostname: str
    domain_name: str = "lab.local"
    banner_motd: str | None = None
    ntp_server: str | None = None
    interfaces: list[InterfaceSpec] = Field(default_factory=list)
    last_deployed_commands: list[str] = Field(default_factory=list)

    @classmethod
    def from_router(cls, device: MockRouter) -> "MockDeviceRuntimeState":
        return cls(
            device_name=device.name,
            hostname=device.hostname,
            interfaces=[interface.model_copy(deep=True) for interface in device.interfaces],
        )


class DeviceConfigSnapshot(BaseModel):
    """Full saved copy of a device state before a configuration change."""

    snapshot_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    device_name: str
    state: MockDeviceRuntimeState


class DeviceSnapshotSummary(BaseModel):
    """Snapshot metadata returned by the API."""

    snapshot_id: UUID
    created_at: datetime
    device_name: str


class BaseConfigurationExecutionResult(BaseModel):
    """Result of a configuration deployment attempt."""

    device_name: str
    dry_run: bool
    changed: bool
    would_change: bool
    commands: list[str]
    before: list[str]
    after: list[str]
    backend: Literal["mock", "netmiko"] = "mock"
    raw_output: str | None = None
    snapshot_id: UUID | None = None


class ConfigurationDriftItem(BaseModel):
    """One difference between current and desired configuration state."""

    path: str
    current: str | bool | None = None
    desired: str | bool | None = None


class BaseConfigurationComplianceReport(BaseModel):
    """Result of checking current device state against a desired base config."""

    device_name: str
    compliant: bool
    drift: list[ConfigurationDriftItem] = Field(default_factory=list)
    current_lines: list[str] = Field(default_factory=list)
    expected_lines: list[str] = Field(default_factory=list)
    backend: Literal["mock"] = "mock"


class BatchComplianceItem(BaseModel):
    """One batch compliance result entry."""

    device_name: str
    status: Literal["success", "failed"]
    report: BaseConfigurationComplianceReport | None = None
    detail: str | None = None


class BatchComplianceSummary(BaseModel):
    """Aggregate counters for batch compliance results."""

    total_items: int
    successful_items: int
    failed_items: int
    compliant_items: int
    drifted_items: int


class BatchComplianceResponse(BaseModel):
    """Collection of batch compliance results."""

    items: list[BatchComplianceItem] = Field(default_factory=list)
    summary: BatchComplianceSummary


class RollbackExecutionResult(BaseModel):
    """Result of restoring a previously saved snapshot."""

    device_name: str
    snapshot_id: UUID
    changed: bool
    before: list[str]
    after: list[str]
    backend: Literal["mock"] = "mock"


class BatchExecutionItem(BaseModel):
    """One batch execution result entry."""

    device_name: str
    status: Literal["success", "failed"]
    result: BaseConfigurationExecutionResult | None = None
    detail: str | None = None


class BatchExecutionSummary(BaseModel):
    """Aggregate counters for batch execution results."""

    total_items: int
    successful_items: int
    failed_items: int
    changed_items: int
    unchanged_items: int


class BatchExecutionResponse(BaseModel):
    """Collection of batch execution results."""

    items: list[BatchExecutionItem] = Field(default_factory=list)
    summary: BatchExecutionSummary


class RunningConfigResponse(BaseModel):
    """Running configuration snapshot returned by the API."""

    device_name: str
    lines: list[str]
    cached: bool = False
    collection_error: str | None = None


class AutomationJobRequest(BaseModel):
    """Request for creating an async automation job."""

    operation: Literal["apply", "compliance"] = "apply"
    device_name: str
    request: BaseConfigurationRequest
    dry_run: bool = False


class DemoResetResponse(BaseModel):
    """Summary of a demo-state reset operation."""

    execution_backend: Literal["mock", "netmiko"]
    inventory_backend: Literal["mock", "netbox"]
    devices_reset: int
    snapshots_cleared: int
    operations_cleared: int


class OperationRecord(BaseModel):
    """Audit entry for an automation action."""

    operation_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    operation: Literal["preview", "apply", "rollback", "compliance"]
    device_name: str
    request_id: str | None = None
    dry_run: bool = False
    backend: Literal["mock", "netmiko"] = "mock"
    status: Literal["success", "failed"]
    request: BaseConfigurationRequest | None = None
    commands: list[str] = Field(default_factory=list)
    changed: bool = False
    would_change: bool = False
    detail: str | None = None
    snapshot_id: UUID | None = None


class OperationSummary(BaseModel):
    """Aggregate counters for filtered automation operations."""

    total_operations: int
    successful_operations: int
    failed_operations: int
    preview_operations: int
    apply_operations: int
    rollback_operations: int
    compliance_operations: int
