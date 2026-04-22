"""Service layer for async automation jobs prepared for future Celery workers."""

from collections.abc import Callable
from uuid import uuid4

from app.automation.models import AutomationJobRequest
from app.core.config import settings
from app.db.models import AutomationJobRecord
from app.db.sqlite import SQLiteDatabase
from app.domain.exceptions import AutomationExecutionError, DeviceNotFoundError
from app.services.automation_service import AutomationService
from app.store.contracts import DeviceRepository

CeleryDispatch = Callable[[str], str]


class JobService:
    """Creates and reads persistent automation job records."""

    def __init__(
        self,
        database: SQLiteDatabase,
        repository: DeviceRepository,
        celery_dispatcher: CeleryDispatch | None = None,
    ) -> None:
        self._database = database
        self._repository = repository
        self._celery_dispatcher = celery_dispatcher or self._dispatch_to_celery

    def create_job(self, job_request: AutomationJobRequest) -> AutomationJobRecord:
        self._repository.get_device(job_request.device_name)
        created = self._database.create_job(
            job=job_request,
            job_id=str(uuid4()),
            queue_backend=settings.task_queue_backend,
        )
        if settings.task_queue_backend == "celery":
            broker_task_id = self._celery_dispatcher(created.job_id)
            return self._database.update_job(
                created.job_id,
                status="queued",
                result={"broker_task_id": broker_task_id},
            )
        return created

    def get_job(self, job_id: str) -> AutomationJobRecord:
        job = self._database.get_job(job_id)
        if job is None:
            raise DeviceNotFoundError(f"Automation job '{job_id}' not found")
        return job

    def list_jobs(self, limit: int = 50) -> list[AutomationJobRecord]:
        return self._database.list_jobs(limit=limit)

    def execute_job(
        self,
        job_id: str,
        automation_service: AutomationService,
    ) -> AutomationJobRecord:
        job = self.get_job(job_id)
        if job.queue_backend != "database":
            raise AutomationExecutionError(
                "Manual execute is supported only for database-backed jobs"
            )
        if job.status not in {"queued", "failed"}:
            raise AutomationExecutionError(
                f"Job '{job_id}' cannot be executed from status '{job.status}'"
            )
        request = AutomationJobRequest.model_validate(job.payload)
        self._database.update_job(job_id, status="running")

        try:
            if request.operation == "apply":
                result = automation_service.deploy_base_configuration(
                    request.device_name,
                    request.request,
                    dry_run=request.dry_run,
                )
            elif request.operation == "compliance":
                result = automation_service.check_base_configuration_compliance(
                    request.device_name,
                    request.request,
                )
            else:
                raise AutomationExecutionError(
                    f"Unsupported automation job operation '{request.operation}'"
                )
        except Exception as exc:
            return self._database.update_job(
                job_id,
                status="failed",
                error=str(exc),
            )

        return self._database.update_job(
            job_id,
            status="succeeded",
            result=result.model_dump(mode="json"),
        )

    def retry_job(self, job_id: str) -> AutomationJobRecord:
        job = self.get_job(job_id)
        if job.status == "running":
            raise AutomationExecutionError(
                f"Job '{job_id}' is already running and cannot be retried"
            )

        reset = self._database.update_job(
            job_id,
            status="queued",
            result=None,
            error=None,
        )
        if reset.queue_backend == "celery":
            broker_task_id = self._celery_dispatcher(job_id)
            return self._database.update_job(
                job_id,
                status="queued",
                result={"broker_task_id": broker_task_id},
                error=None,
            )
        return reset

    @staticmethod
    def _dispatch_to_celery(job_id: str) -> str:
        try:
            from celery import Celery
        except ImportError as exc:  # pragma: no cover - depends on optional dependency
            raise AutomationExecutionError(
                "Celery is not installed. Install dependencies and configure a broker before using task_queue_backend=celery"
            ) from exc

        celery_app = Celery(
            "netauto",
            broker=settings.celery_broker_url,
            backend=settings.celery_result_backend,
        )
        async_result = celery_app.send_task(
            "app.celery_tasks.execute_automation_job",
            args=[job_id],
            queue=settings.celery_queue_name,
        )
        return str(async_result.id)
