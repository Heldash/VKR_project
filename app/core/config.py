"""Application-wide settings."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = "NetAuto MVP"
    version: str = "0.1.0"
    inventory_backend: Literal["mock", "netbox"] = "mock"
    execution_backend: Literal["mock", "netmiko"] = "mock"
    task_queue_backend: Literal["database", "celery"] = "database"
    celery_queue_name: str = "automation"
    api_key: str | None = None
    rbac_enabled: bool = False
    mock_state_path: str = "data/mock_device_state.json"
    operation_journal_path: str = "data/operation_journal.json"
    database_path: str = "data/netauto.db"
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "admin"
    bootstrap_operator_username: str = "operator"
    bootstrap_operator_password: str = "operator"
    bootstrap_viewer_username: str = "viewer"
    bootstrap_viewer_password: str = "viewer"
    netbox_url: str | None = None
    netbox_token: str | None = None
    netbox_timeout: float = 30.0
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    device_username: str | None = None
    device_password: str | None = None
    device_secret: str | None = None
    device_port: int = 22
    running_config_command: str = "show running-config"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="NAA_")


settings = Settings()
