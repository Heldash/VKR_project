"""Database models used by the SQLite storage layer."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DatabaseStatus(BaseModel):
    """High-level database readiness information."""

    backend: str = "sqlite"
    path: str
    initialized: bool
    roles_count: int
    users_count: int


class DatabaseUser(BaseModel):
    """Public user representation returned by auth and RBAC helpers."""

    id: int
    username: str
    role: Literal["admin", "operator", "viewer"]
    is_active: bool


class DatabaseUserCredentials(DatabaseUser):
    """Internal user representation with a password hash."""

    password_hash: str


class AutomationJobRecord(BaseModel):
    """Persistent async automation job record stored in SQLite."""

    job_id: str
    operation: Literal["apply", "compliance"]
    status: Literal["queued", "running", "succeeded", "failed"]
    device_name: str
    queue_backend: Literal["database", "celery"]
    dry_run: bool
    payload: dict
    result: dict | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
