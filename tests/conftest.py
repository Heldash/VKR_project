import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from app.api.deps import (
    get_automation_service,
    get_configuration_profile_repository,
    get_database_service,
    get_diagnostics_service,
    get_device_repository,
    get_reachability_service,
    get_device_service,
    get_device_state_repository,
    get_execution_backend,
    get_job_service,
    get_operation_journal_repository,
)
from app.core.config import settings


@pytest.fixture(autouse=True)
def clear_dependency_caches():
    factories = (
        get_automation_service,
        get_configuration_profile_repository,
        get_diagnostics_service,
        get_database_service,
        get_device_repository,
        get_reachability_service,
        get_device_service,
        get_device_state_repository,
        get_execution_backend,
        get_job_service,
        get_operation_journal_repository,
    )
    runtime_dir = Path("tests_runtime") / str(uuid4())
    runtime_dir.mkdir(parents=True, exist_ok=True)

    original_api_key = settings.api_key
    original_database_path = settings.database_path
    original_rbac_enabled = settings.rbac_enabled
    original_mock_state_path = settings.mock_state_path
    original_operation_journal_path = settings.operation_journal_path

    settings.database_path = str(runtime_dir / "netauto.db")
    settings.rbac_enabled = False
    settings.mock_state_path = str(runtime_dir / "mock_device_state.json")
    settings.operation_journal_path = str(runtime_dir / "operation_journal.json")

    for factory in factories:
        factory.cache_clear()

    yield

    settings.api_key = original_api_key
    settings.database_path = original_database_path
    settings.rbac_enabled = original_rbac_enabled
    settings.mock_state_path = original_mock_state_path
    settings.operation_journal_path = original_operation_journal_path

    for factory in factories:
        factory.cache_clear()

    shutil.rmtree(runtime_dir, ignore_errors=True)
