"""SQLite-backed database initialization for RBAC and background-task metadata."""

import json
import sqlite3
from pathlib import Path

from app.automation.models import AutomationJobRequest
from app.core.config import settings
from app.core.security import hash_password
from app.db.models import AutomationJobRecord, DatabaseStatus, DatabaseUserCredentials

DEFAULT_ROLES: tuple[tuple[str, str], ...] = (
    ("admin", "Full access to administration and automation actions"),
    ("operator", "Can run automation workflows but cannot manage system settings"),
    ("viewer", "Read-only access to inventory and reports"),
)
DEFAULT_USERS: tuple[tuple[str, str, str], ...] = (
    ("admin", "admin", "bootstrap_admin"),
    ("operator", "operator", "bootstrap_operator"),
    ("viewer", "viewer", "bootstrap_viewer"),
)


class SQLiteDatabase:
    """Very small SQLite wrapper used as the first DB foundation step."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)

    @property
    def path(self) -> Path:
        return self._database_path

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._database_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS roles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    role_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(role_id) REFERENCES roles(id)
                );

                CREATE TABLE IF NOT EXISTS automation_jobs (
                    job_id TEXT PRIMARY KEY,
                    operation TEXT NOT NULL,
                    status TEXT NOT NULL,
                    device_name TEXT NOT NULL,
                    queue_backend TEXT NOT NULL DEFAULT 'database',
                    dry_run INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            connection.executemany(
                "INSERT OR IGNORE INTO roles(name, description) VALUES(?, ?)",
                DEFAULT_ROLES,
            )
            for username, role_name, prefix in DEFAULT_USERS:
                configured_username = getattr(settings, f"{prefix}_username")
                configured_password = getattr(settings, f"{prefix}_password")
                role_id = self._get_role_id(connection, role_name)
                connection.execute(
                    """
                    INSERT OR IGNORE INTO users(username, password_hash, role_id)
                    VALUES(?, ?, ?)
                    """,
                    (
                        configured_username,
                        hash_password(configured_password),
                        role_id,
                    ),
                )
            connection.commit()

    def get_status(self) -> DatabaseStatus:
        self.initialize()
        with sqlite3.connect(self._database_path) as connection:
            roles_count = self._count_rows(connection, "roles")
            users_count = self._count_rows(connection, "users")
        return DatabaseStatus(
            path=str(self._database_path),
            initialized=self._database_path.exists(),
            roles_count=roles_count,
            users_count=users_count,
        )

    def get_user_by_username(self, username: str) -> DatabaseUserCredentials | None:
        self.initialize()
        with sqlite3.connect(self._database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT users.id, users.username, users.password_hash, users.is_active, roles.name AS role
                FROM users
                JOIN roles ON roles.id = users.role_id
                WHERE users.username = ?
                """,
                (username,),
            ).fetchone()
        if row is None:
            return None
        return DatabaseUserCredentials(
            id=int(row["id"]),
            username=str(row["username"]),
            password_hash=str(row["password_hash"]),
            role=str(row["role"]),
            is_active=bool(row["is_active"]),
        )

    def create_job(
        self,
        job: AutomationJobRequest,
        job_id: str,
        queue_backend: str,
    ) -> AutomationJobRecord:
        self.initialize()
        payload_json = json.dumps(job.model_dump(mode="json"), ensure_ascii=True)
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO automation_jobs(
                    job_id, operation, status, device_name, queue_backend, dry_run, payload_json
                )
                VALUES(?, ?, 'queued', ?, ?, ?, ?)
                """,
                (
                    job_id,
                    job.operation,
                    job.device_name,
                    queue_backend,
                    int(job.dry_run),
                    payload_json,
                ),
            )
            connection.commit()
        created = self.get_job(job_id)
        if created is None:
            raise RuntimeError(f"Failed to persist automation job '{job_id}'")
        return created

    def get_job(self, job_id: str) -> AutomationJobRecord | None:
        self.initialize()
        with sqlite3.connect(self._database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM automation_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return self._row_to_job(row) if row is not None else None

    def list_jobs(self, limit: int = 50) -> list[AutomationJobRecord]:
        self.initialize()
        with sqlite3.connect(self._database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT * FROM automation_jobs
                ORDER BY datetime(created_at) DESC, job_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def update_job(
        self,
        job_id: str,
        *,
        status: str,
        result: dict | None = None,
        error: str | None = None,
    ) -> AutomationJobRecord:
        self.initialize()
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                UPDATE automation_jobs
                SET status = ?,
                    result_json = ?,
                    error = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = ?
                """,
                (
                    status,
                    json.dumps(result, ensure_ascii=True) if result is not None else None,
                    error,
                    job_id,
                ),
            )
            connection.commit()
        updated = self.get_job(job_id)
        if updated is None:
            raise RuntimeError(f"Failed to update automation job '{job_id}'")
        return updated

    @staticmethod
    def _count_rows(connection: sqlite3.Connection, table_name: str) -> int:
        cursor = connection.execute(f"SELECT COUNT(*) FROM {table_name}")
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    @staticmethod
    def _get_role_id(connection: sqlite3.Connection, role_name: str) -> int:
        cursor = connection.execute(
            "SELECT id FROM roles WHERE name = ?",
            (role_name,),
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError(f"Role '{role_name}' was not initialized")
        return int(row[0])

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> AutomationJobRecord:
        result = row["result_json"]
        return AutomationJobRecord(
            job_id=str(row["job_id"]),
            operation=str(row["operation"]),
            status=str(row["status"]),
            device_name=str(row["device_name"]),
            queue_backend=str(row["queue_backend"]),
            dry_run=bool(row["dry_run"]),
            payload=json.loads(str(row["payload_json"])),
            result=json.loads(str(result)) if result else None,
            error=str(row["error"]) if row["error"] else None,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
