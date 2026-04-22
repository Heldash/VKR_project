import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_automation_service, get_device_state_repository, get_operation_journal_repository
from app.main import create_app


def reset_runtime_repositories() -> None:
    get_automation_service.cache_clear()
    get_device_state_repository.cache_clear()
    get_operation_journal_repository.cache_clear()


@pytest.mark.asyncio
async def test_running_state_snapshots_and_operations_persist_across_repository_rebuild():
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        apply_response = await ac.post(
            "/api/automation/devices/lab-r1/base-config/apply",
            headers={"X-Request-ID": "req-persist-apply"},
            json={
                "hostname": "EDGE-R1",
                "domain_name": "persist.lab",
                "banner_motd": "Persistent config",
            },
        )
        operations_before = await ac.get("/api/automation/operations")
        snapshots_before = await ac.get("/api/automation/devices/lab-r1/snapshots")
        running_before = await ac.get("/api/automation/devices/lab-r1/running-config")

    assert apply_response.status_code == 200
    snapshot_id = apply_response.json()["snapshot_id"]
    assert snapshot_id is not None
    assert operations_before.status_code == 200
    assert snapshots_before.status_code == 200
    assert running_before.status_code == 200

    reset_runtime_repositories()
    restarted_app = create_app()

    async with AsyncClient(transport=ASGITransport(app=restarted_app), base_url="http://test") as ac:
        operations_after = await ac.get("/api/automation/operations")
        snapshots_after = await ac.get("/api/automation/devices/lab-r1/snapshots")
        running_after = await ac.get("/api/automation/devices/lab-r1/running-config")

    assert operations_after.status_code == 200
    assert snapshots_after.status_code == 200
    assert running_after.status_code == 200
    assert operations_after.json()[0]["request_id"] == "req-persist-apply"
    assert snapshots_after.json()[0]["snapshot_id"] == snapshot_id
    assert running_after.json() == running_before.json()
    assert "hostname EDGE-R1" in running_after.json()["lines"]
    assert "ip domain-name persist.lab" in running_after.json()["lines"]


@pytest.mark.asyncio
async def test_persisted_snapshot_can_be_used_for_rollback_after_repository_rebuild():
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        original_running = await ac.get("/api/automation/devices/lab-r1/running-config")
        apply_response = await ac.post(
            "/api/automation/devices/lab-r1/base-config/apply",
            headers={"X-Request-ID": "req-persisted-snapshot"},
            json={
                "hostname": "EDGE-R1",
                "domain_name": "persist.lab",
                "banner_motd": "Config before restart",
            },
        )
        changed_running = await ac.get("/api/automation/devices/lab-r1/running-config")

    assert original_running.status_code == 200
    assert apply_response.status_code == 200
    assert changed_running.status_code == 200
    snapshot_id = apply_response.json()["snapshot_id"]
    assert snapshot_id is not None
    assert changed_running.json() != original_running.json()

    reset_runtime_repositories()
    restarted_app = create_app()

    async with AsyncClient(transport=ASGITransport(app=restarted_app), base_url="http://test") as ac:
        rollback_response = await ac.post(
            f"/api/automation/devices/lab-r1/rollback/{snapshot_id}",
            headers={"X-Request-ID": "req-rollback-after-restart"},
        )
        restored_running = await ac.get("/api/automation/devices/lab-r1/running-config")
        operations = await ac.get(
            "/api/automation/operations",
            params={"request_id": "req-rollback-after-restart"},
        )

    assert rollback_response.status_code == 200
    assert restored_running.status_code == 200
    assert operations.status_code == 200
    assert rollback_response.json()["snapshot_id"] == snapshot_id
    assert restored_running.json() == original_running.json()
    assert operations.json()[0]["operation"] == "rollback"
    assert operations.json()[0]["request_id"] == "req-rollback-after-restart"
