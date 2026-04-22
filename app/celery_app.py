"""Celery application bootstrap for async automation workers."""

from app.core.config import settings


def create_celery_app():
    """Builds a Celery application using current settings."""
    try:
        from celery import Celery
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise RuntimeError(
            "Celery is not installed. Run pip install -r requirements.txt before starting the worker."
        ) from exc

    app = Celery(
        "netauto",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
    )
    app.conf.task_default_queue = settings.celery_queue_name
    return app


celery_app = create_celery_app()
