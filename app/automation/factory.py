"""Factory functions for automation execution backends."""

from app.automation.execution_backends import (
    ConfigExecutionBackend,
    MockExecutionBackend,
    NetmikoExecutionBackend,
)
from app.core.config import settings


def build_execution_backend() -> ConfigExecutionBackend:
    """Builds the execution backend selected for the current environment."""

    if settings.execution_backend == "mock":
        return MockExecutionBackend()
    return NetmikoExecutionBackend(
        running_config_command=settings.running_config_command,
    )
