"""Celery tasks that execute persistent automation jobs."""

from app.api.deps import (
    get_automation_service,
    get_device_repository,
)
from app.celery_app import celery_app
from app.core.config import settings
from app.db.sqlite import SQLiteDatabase
from app.services.job_service import JobService


@celery_app.task(name="app.celery_tasks.execute_automation_job")
def execute_automation_job(job_id: str) -> dict:
    """Executes one queued automation job and persists its final state."""
    job_service = JobService(
        database=SQLiteDatabase(settings.database_path),
        repository=get_device_repository(),
    )
    result = job_service.execute_job(
        job_id=job_id,
        automation_service=get_automation_service(),
    )
    return result.model_dump(mode="json")
