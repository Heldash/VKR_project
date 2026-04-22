"""In-memory operation journal for automation audit history."""

import json
from pathlib import Path

from app.automation.models import OperationRecord, OperationSummary
from app.domain.exceptions import DeviceNotFoundError


class OperationJournalRepository:
    """Stores automation operation history in memory."""

    def __init__(self, storage_path: str | Path | None = None) -> None:
        self._storage_path = Path(storage_path) if storage_path else None
        self._records: list[OperationRecord] = []
        self._load()

    def add(self, record: OperationRecord) -> OperationRecord:
        self._records.insert(0, record)
        self._save()
        return record

    def list_records(
        self,
        device_name: str | None = None,
        operation: str | None = None,
        status: str | None = None,
        request_id: str | None = None,
        limit: int | None = None,
    ) -> list[OperationRecord]:
        records = self._filter_records(
            device_name=device_name,
            operation=operation,
            status=status,
            request_id=request_id,
        )
        if limit is not None:
            records = records[:limit]
        return records

    def build_summary(
        self,
        device_name: str | None = None,
        operation: str | None = None,
        status: str | None = None,
        request_id: str | None = None,
    ) -> OperationSummary:
        records = self._filter_records(
            device_name=device_name,
            operation=operation,
            status=status,
            request_id=request_id,
        )
        return OperationSummary(
            total_operations=len(records),
            successful_operations=sum(1 for record in records if record.status == "success"),
            failed_operations=sum(1 for record in records if record.status == "failed"),
            preview_operations=sum(1 for record in records if record.operation == "preview"),
            apply_operations=sum(1 for record in records if record.operation == "apply"),
            rollback_operations=sum(1 for record in records if record.operation == "rollback"),
            compliance_operations=sum(1 for record in records if record.operation == "compliance"),
        )

    def get_record(self, operation_id: str) -> OperationRecord:
        for record in self._records:
            if str(record.operation_id) == operation_id:
                return record
        raise DeviceNotFoundError(f"Operation '{operation_id}' not found")

    def reset(self) -> int:
        cleared = len(self._records)
        self._records = []
        self._save()
        return cleared

    def _load(self) -> None:
        if self._storage_path is None or not self._storage_path.exists():
            return
        payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        self._records = [
            OperationRecord.model_validate(record_payload)
            for record_payload in payload.get("records", [])
        ]

    def _save(self) -> None:
        if self._storage_path is None:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "records": [record.model_dump(mode="json") for record in self._records],
        }
        self._storage_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    def _filter_records(
        self,
        device_name: str | None = None,
        operation: str | None = None,
        status: str | None = None,
        request_id: str | None = None,
    ) -> list[OperationRecord]:
        records = list(self._records)
        if device_name is not None:
            records = [record for record in records if record.device_name == device_name]
        if operation is not None:
            records = [record for record in records if record.operation == operation]
        if status is not None:
            records = [record for record in records if record.status == status]
        if request_id is not None:
            records = [record for record in records if record.request_id == request_id]
        return records
