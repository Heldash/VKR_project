import pytest
from httpx import ASGITransport, AsyncClient

from app.automation.models import BaseConfigurationRequest
from app.main import create_app
from app.services.automation_service import AutomationService
from app.store.mock_device_state import MockDeviceStateRepository
from app.store.mock_inventory import MockInventoryRepository


def build_service() -> AutomationService:
    repository = MockInventoryRepository()
    state_repository = MockDeviceStateRepository(repository.list_devices())
    return AutomationService(
        repository=repository,
        state_repository=state_repository,
    )


def test_service_records_preview_apply_and_rollback_operations_in_reverse_chronological_order():
    service = build_service()

    service.generate_base_configuration(
        "lab-r1",
        BaseConfigurationRequest(hostname="EDGE-R1"),
    )
    service.check_base_configuration_compliance(
        "lab-r1",
        BaseConfigurationRequest(hostname="EDGE-R1"),
    )
    apply_result = service.deploy_base_configuration(
        "lab-r1",
        BaseConfigurationRequest(hostname="EDGE-R1"),
    )
    service.rollback_to_snapshot("lab-r1", str(apply_result.snapshot_id))

    operations = service.list_operations()

    assert len(operations) == 4
    assert operations[0].operation == "rollback"
    assert operations[0].status == "success"
    assert str(operations[0].snapshot_id) == str(apply_result.snapshot_id)
    assert operations[0].request_id is None
    assert operations[1].operation == "apply"
    assert operations[1].status == "success"
    assert operations[2].operation == "compliance"
    assert operations[2].status == "success"
    assert operations[3].operation == "preview"


@pytest.mark.asyncio
async def test_api_returns_operation_history_with_failed_apply_and_successful_rollback():
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        preview_response = await ac.post(
            "/api/automation/devices/lab-r1/base-config/preview",
            headers={"X-Request-ID": "req-preview"},
            json={"hostname": "EDGE-R1"},
        )
        apply_response = await ac.post(
            "/api/automation/devices/lab-r1/base-config/apply",
            headers={"X-Request-ID": "req-apply"},
            json={"hostname": "EDGE-R1"},
        )
        failed_apply = await ac.post(
            "/api/automation/devices/lab-r3/base-config/apply",
            headers={"X-Request-ID": "req-failed-apply"},
            json={"hostname": "CORE-R3"},
        )
        snapshot_id = apply_response.json()["snapshot_id"]
        rollback_response = await ac.post(
            f"/api/automation/devices/lab-r1/rollback/{snapshot_id}",
            headers={"X-Request-ID": "req-rollback"},
        )
        operations_response = await ac.get("/api/automation/operations")

    assert preview_response.status_code == 200
    assert preview_response.headers["X-Request-ID"] == "req-preview"
    assert apply_response.status_code == 200
    assert apply_response.headers["X-Request-ID"] == "req-apply"
    assert failed_apply.status_code == 409
    assert failed_apply.headers["X-Request-ID"] == "req-failed-apply"
    assert rollback_response.status_code == 200
    assert rollback_response.headers["X-Request-ID"] == "req-rollback"
    assert operations_response.status_code == 200

    operations = operations_response.json()
    assert len(operations) == 4
    assert operations[0]["operation"] == "rollback"
    assert operations[0]["status"] == "success"
    assert operations[0]["snapshot_id"] == snapshot_id
    assert operations[0]["request_id"] == "req-rollback"
    assert operations[1]["operation"] == "apply"
    assert operations[1]["status"] == "failed"
    assert operations[1]["request_id"] == "req-failed-apply"
    assert "maintenance mode" in operations[1]["detail"]
    assert operations[2]["operation"] == "apply"
    assert operations[2]["status"] == "success"
    assert operations[2]["request_id"] == "req-apply"
    assert operations[3]["operation"] == "preview"
    assert operations[3]["status"] == "success"
    assert operations[3]["request_id"] == "req-preview"


@pytest.mark.asyncio
async def test_api_filters_operation_history_and_limits_results():
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(
            "/api/automation/devices/lab-r1/base-config/preview",
            headers={"X-Request-ID": "req-preview-lab-r1"},
            json={"hostname": "EDGE-R1"},
        )
        await ac.post(
            "/api/automation/devices/lab-r2/base-config/preview",
            headers={"X-Request-ID": "req-preview-lab-r2"},
            json={"hostname": "DIST-R2"},
        )
        await ac.post(
            "/api/automation/devices/lab-r3/base-config/apply",
            headers={"X-Request-ID": "req-failed-lab-r3"},
            json={"hostname": "CORE-R3"},
        )

        filtered_response = await ac.get(
            "/api/automation/operations",
            params={"device_name": "lab-r3", "status": "failed", "limit": 1},
        )
        request_filtered_response = await ac.get(
            "/api/automation/operations",
            params={"request_id": "req-preview-lab-r1"},
        )

    assert filtered_response.status_code == 200
    filtered_body = filtered_response.json()
    assert len(filtered_body) == 1
    assert filtered_body[0]["device_name"] == "lab-r3"
    assert filtered_body[0]["status"] == "failed"

    assert request_filtered_response.status_code == 200
    request_filtered_body = request_filtered_response.json()
    assert len(request_filtered_body) == 1
    assert request_filtered_body[0]["request_id"] == "req-preview-lab-r1"
    assert request_filtered_body[0]["operation"] == "preview"


@pytest.mark.asyncio
async def test_api_returns_operation_summary_for_filtered_history():
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(
            "/api/automation/devices/lab-r1/base-config/preview",
            headers={"X-Request-ID": "req-summary-preview"},
            json={"hostname": "EDGE-R1"},
        )
        await ac.post(
            "/api/automation/devices/lab-r1/base-config/compliance",
            headers={"X-Request-ID": "req-summary-compliance"},
            json={"hostname": "EDGE-R1"},
        )
        await ac.post(
            "/api/automation/devices/lab-r1/base-config/apply",
            headers={"X-Request-ID": "req-summary-apply"},
            json={"hostname": "EDGE-R1"},
        )
        summary_response = await ac.get(
            "/api/automation/operations/summary",
            params={"device_name": "lab-r1"},
        )

    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["total_operations"] == 3
    assert summary["successful_operations"] == 3
    assert summary["failed_operations"] == 0
    assert summary["preview_operations"] == 1
    assert summary["apply_operations"] == 1
    assert summary["rollback_operations"] == 0
    assert summary["compliance_operations"] == 1


@pytest.mark.asyncio
async def test_api_returns_single_operation_by_id():
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(
            "/api/automation/devices/lab-r1/base-config/preview",
            headers={"X-Request-ID": "req-single-operation"},
            json={"hostname": "EDGE-R1"},
        )
        operations_response = await ac.get("/api/automation/operations")
        operation_id = operations_response.json()[0]["operation_id"]
        operation_response = await ac.get(f"/api/automation/operations/{operation_id}")

    assert operation_response.status_code == 200
    assert operation_response.json()["operation_id"] == operation_id
    assert operation_response.json()["device_name"] == "lab-r1"
    assert operation_response.json()["request_id"] == "req-single-operation"


@pytest.mark.asyncio
async def test_api_returns_not_found_for_unknown_operation():
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(
            "/api/automation/operations/00000000-0000-0000-0000-000000000000"
        )

    assert response.status_code == 404
    assert "Operation" in response.json()["detail"]
