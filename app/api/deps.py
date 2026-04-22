"""Dependency providers for API routes."""

from functools import lru_cache
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.automation.execution_backends import ConfigExecutionBackend
from app.automation.factory import build_execution_backend
from app.core.config import settings
from app.db.models import DatabaseUser
from app.db.sqlite import SQLiteDatabase
from app.services.automation_service import AutomationService
from app.services.database_service import DatabaseService
from app.services.device_service import DeviceService
from app.services.diagnostics_service import DiagnosticsService
from app.services.job_service import JobService
from app.services.preflight_service import PreflightService
from app.store.config_profiles import ConfigurationProfileRepository
from app.store.contracts import DeviceRepository
from app.store.factory import build_device_repository
from app.store.mock_device_state import MockDeviceStateRepository
from app.store.operation_journal import OperationJournalRepository

basic_security = HTTPBasic(auto_error=False)


@lru_cache
def get_device_repository() -> DeviceRepository:
    return build_device_repository()


@lru_cache
def get_device_state_repository() -> MockDeviceStateRepository:
    return MockDeviceStateRepository(
        devices=get_device_repository().list_devices(),
        storage_path=settings.mock_state_path,
    )


@lru_cache
def get_operation_journal_repository() -> OperationJournalRepository:
    return OperationJournalRepository(storage_path=settings.operation_journal_path)


@lru_cache
def get_configuration_profile_repository() -> ConfigurationProfileRepository:
    return ConfigurationProfileRepository()


@lru_cache
def get_database_service() -> DatabaseService:
    return DatabaseService(database=SQLiteDatabase(settings.database_path))


@lru_cache
def get_job_service() -> JobService:
    return JobService(
        database=SQLiteDatabase(settings.database_path),
        repository=get_device_repository(),
    )


@lru_cache
def get_device_service() -> DeviceService:
    return DeviceService(repository=get_device_repository())


@lru_cache
def get_execution_backend() -> ConfigExecutionBackend:
    return build_execution_backend()


@lru_cache
def get_preflight_service() -> PreflightService:
    return PreflightService()


@lru_cache
def get_diagnostics_service() -> DiagnosticsService:
    return DiagnosticsService()


@lru_cache
def get_automation_service() -> AutomationService:
    return AutomationService(
        repository=get_device_repository(),
        state_repository=get_device_state_repository(),
        execution_backend=get_execution_backend(),
        journal_repository=get_operation_journal_repository(),
        profile_repository=get_configuration_profile_repository(),
    )


def require_automation_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    if not settings.api_key:
        return
    if x_api_key and compare_digest(x_api_key, settings.api_key):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing X-API-Key header",
    )


def get_current_user(
    credentials: Annotated[HTTPBasicCredentials | None, Depends(basic_security)],
    database_service: DatabaseService = Depends(get_database_service),
) -> DatabaseUser:
    if not settings.rbac_enabled:
        return DatabaseUser(
            id=0,
            username="rbac-disabled",
            role="admin",
            is_active=True,
        )

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="RBAC is enabled; provide HTTP Basic credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    user = database_service.authenticate_user(
        credentials.username,
        credentials.password,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return user


def require_operator_role(
    current_user: DatabaseUser = Depends(get_current_user),
) -> None:
    if current_user.role in {"admin", "operator"}:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Operator or admin role is required",
    )


def require_admin_role(
    current_user: DatabaseUser = Depends(get_current_user),
) -> None:
    if current_user.role == "admin":
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin role is required",
    )
