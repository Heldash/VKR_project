"""Service layer for database initialization and status checks."""

from app.core.security import verify_password
from app.db.models import DatabaseStatus, DatabaseUser
from app.db.sqlite import SQLiteDatabase


class DatabaseService:
    """Coordinates database bootstrap and health/status access."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def initialize(self) -> None:
        self._database.initialize()

    def get_status(self) -> DatabaseStatus:
        return self._database.get_status()

    def authenticate_user(self, username: str, password: str) -> DatabaseUser | None:
        credentials = self._database.get_user_by_username(username)
        if credentials is None or not credentials.is_active:
            return None
        if not verify_password(password, credentials.password_hash):
            return None
        return DatabaseUser(
            id=credentials.id,
            username=credentials.username,
            role=credentials.role,
            is_active=credentials.is_active,
        )
