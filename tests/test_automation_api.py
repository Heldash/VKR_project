import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import create_app


@pytest.mark.asyncio
async def test_list_profiles_endpoint():
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/automation/profiles")

    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 2
    assert body[0]["name"] in {"branch-edge", "campus-distribution"}


@pytest.mark.asyncio
async def test_preview_base_configuration_endpoint():
    app = create_app()
    payload = {
        "hostname": "EDGE-R1",
        "domain_name": "branch.lab",
        "banner_motd": "Managed by API",
        "ntp_server": "192.0.2.200",
        "interfaces": [
            {
                "name": "Loopback0",
                "description": "API preview loopback",
                "ipv4_address": "10.255.0.1/32",
                "enabled": True,
            }
        ],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/devices/lab-r1/base-config/preview",
            json=payload,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["device_name"] == "lab-r1"
    assert "hostname EDGE-R1" in body["commands"]
    assert "ntp server 192.0.2.200" in body["commands"]


@pytest.mark.asyncio
async def test_automation_post_endpoint_requires_api_key_when_enabled():
    settings.api_key = "test-secret"
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/devices/lab-r1/base-config/preview",
            json={"hostname": "EDGE-R1"},
        )

    assert response.status_code == 401
    assert "X-API-Key" in response.json()["detail"]


@pytest.mark.asyncio
async def test_automation_post_endpoint_accepts_valid_api_key_when_enabled():
    settings.api_key = "test-secret"
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/devices/lab-r1/base-config/preview",
            json={"hostname": "EDGE-R1"},
            headers={"X-API-Key": "test-secret"},
        )

    assert response.status_code == 200
    assert response.json()["device_name"] == "lab-r1"


@pytest.mark.asyncio
async def test_get_endpoints_remain_open_when_api_key_is_enabled():
    settings.api_key = "test-secret"
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        devices_response = await ac.get("/api/devices")
        profiles_response = await ac.get("/api/automation/profiles")

    assert devices_response.status_code == 200
    assert profiles_response.status_code == 200


@pytest.mark.asyncio
async def test_auth_me_returns_current_rbac_user_when_enabled():
    settings.rbac_enabled = True
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(
            "/api/system/auth/me",
            auth=("admin", "admin"),
        )

    assert response.status_code == 200
    assert response.json()["username"] == "admin"
    assert response.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_operator_role_is_required_for_automation_post_when_rbac_enabled():
    settings.rbac_enabled = True
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/devices/lab-r1/base-config/preview",
            json={"hostname": "EDGE-R1"},
            auth=("viewer", "viewer"),
        )

    assert response.status_code == 403
    assert "Operator or admin role" in response.json()["detail"]


@pytest.mark.asyncio
async def test_operator_can_run_automation_post_when_rbac_enabled():
    settings.rbac_enabled = True
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/devices/lab-r1/base-config/preview",
            json={"hostname": "EDGE-R1"},
            auth=("operator", "operator"),
        )

    assert response.status_code == 200
    assert response.json()["device_name"] == "lab-r1"


@pytest.mark.asyncio
async def test_demo_reset_requires_admin_role_when_rbac_enabled():
    settings.rbac_enabled = True
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/demo/reset",
            auth=("operator", "operator"),
        )

    assert response.status_code == 403
    assert "Admin role is required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_automation_job_endpoint_returns_queued_job():
    app = create_app()
    payload = {
        "operation": "apply",
        "device_name": "lab-r1",
        "request": {
            "hostname": "EDGE-R1",
            "domain_name": "branch.lab",
        },
        "dry_run": True,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/automation/jobs", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["operation"] == "apply"
    assert body["status"] == "queued"
    assert body["device_name"] == "lab-r1"
    assert body["dry_run"] is True
    assert body["payload"]["request"]["hostname"] == "EDGE-R1"


@pytest.mark.asyncio
async def test_list_and_get_automation_jobs_endpoints():
    app = create_app()
    payload = {
        "operation": "compliance",
        "device_name": "lab-r1",
        "request": {
            "hostname": "EDGE-R1",
        },
        "dry_run": False,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create_response = await ac.post("/api/automation/jobs", json=payload)
        job_id = create_response.json()["job_id"]

        list_response = await ac.get("/api/automation/jobs")
        get_response = await ac.get(f"/api/automation/jobs/{job_id}")

    assert list_response.status_code == 200
    jobs = list_response.json()
    assert len(jobs) == 1
    assert jobs[0]["job_id"] == job_id
    assert jobs[0]["operation"] == "compliance"

    assert get_response.status_code == 200
    job = get_response.json()
    assert job["job_id"] == job_id
    assert job["status"] == "queued"
    assert job["payload"]["request"]["hostname"] == "EDGE-R1"


@pytest.mark.asyncio
async def test_execute_database_backed_automation_job_endpoint():
    original_task_queue_backend = settings.task_queue_backend
    settings.task_queue_backend = "database"
    app = create_app()
    payload = {
        "operation": "apply",
        "device_name": "lab-r1",
        "request": {
            "hostname": "EDGE-R1",
        },
        "dry_run": True,
    }

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            create_response = await ac.post("/api/automation/jobs", json=payload)
            job_id = create_response.json()["job_id"]

            execute_response = await ac.post(f"/api/automation/jobs/{job_id}/execute")
    finally:
        settings.task_queue_backend = original_task_queue_backend

    assert execute_response.status_code == 200
    body = execute_response.json()
    assert body["status"] == "succeeded"
    assert body["result"]["device_name"] == "lab-r1"
    assert body["result"]["dry_run"] is True


@pytest.mark.asyncio
async def test_retry_failed_database_backed_automation_job_endpoint():
    original_task_queue_backend = settings.task_queue_backend
    settings.task_queue_backend = "database"
    app = create_app()
    payload = {
        "operation": "apply",
        "device_name": "lab-r3",
        "request": {
            "hostname": "EDGE-R3",
        },
        "dry_run": False,
    }

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            create_response = await ac.post("/api/automation/jobs", json=payload)
            job_id = create_response.json()["job_id"]

            execute_response = await ac.post(f"/api/automation/jobs/{job_id}/execute")
            retry_response = await ac.post(f"/api/automation/jobs/{job_id}/retry")
    finally:
        settings.task_queue_backend = original_task_queue_backend

    assert execute_response.status_code == 200
    assert execute_response.json()["status"] == "failed"

    assert retry_response.status_code == 200
    assert retry_response.json()["status"] == "queued"
    assert retry_response.json()["error"] is None


@pytest.mark.asyncio
async def test_preview_base_configuration_rejects_invalid_payload():
    app = create_app()
    payload = {
        "hostname": "EDGE R1",
        "ntp_server": "not-an-ip",
        "interfaces": [
            {
                "name": "Loopback0",
                "description": "Primary loopback",
                "ipv4_address": "10.255.0.1/32",
                "enabled": True,
            },
            {
                "name": "loopback0",
                "description": "Duplicate loopback",
                "ipv4_address": "10.255.0.2/32",
                "enabled": True,
            },
        ],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/devices/lab-r1/base-config/preview",
            json=payload,
        )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert len(detail) >= 1


@pytest.mark.asyncio
async def test_preview_base_configuration_batch_endpoint_returns_partial_results():
    app = create_app()
    payload = {
        "items": [
            {
                "device_name": "lab-r1",
                "request": {
                    "hostname": "EDGE-R1",
                    "domain_name": "branch.lab",
                },
            },
            {
                "device_name": "lab-r99",
                "request": {
                    "hostname": "MISSING-R99",
                },
            },
        ]
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/batch/base-config/preview",
            json=payload,
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["summary"]["total_items"] == 2
    assert body["summary"]["successful_items"] == 1
    assert body["summary"]["failed_items"] == 1
    assert body["items"][0]["status"] == "success"
    assert body["items"][0]["preview"]["device_name"] == "lab-r1"
    assert "hostname EDGE-R1" in body["items"][0]["preview"]["commands"]
    assert body["items"][1]["status"] == "failed"
    assert body["items"][1]["preview"] is None
    assert "lab-r99" in body["items"][1]["detail"]


@pytest.mark.asyncio
async def test_preview_base_configuration_batch_rejects_duplicate_devices():
    app = create_app()
    payload = {
        "items": [
            {
                "device_name": "lab-r1",
                "request": {
                    "hostname": "EDGE-R1",
                },
            },
            {
                "device_name": "LAB-R1",
                "request": {
                    "hostname": "EDGE-R1-B",
                },
            },
        ]
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/batch/base-config/preview",
            json=payload,
        )

    assert response.status_code == 422
    assert len(response.json()["detail"]) >= 1


@pytest.mark.asyncio
async def test_preview_base_configuration_from_profile_endpoint():
    app = create_app()
    payload = {
        "hostname": "EDGE-R1",
        "banner_motd": "Managed by profile override",
        "interfaces": [
            {
                "name": "GigabitEthernet0/0",
                "description": "Primary ISP uplink",
                "ipv4_address": "198.51.100.1/30",
                "enabled": True,
            }
        ],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/devices/lab-r1/base-config/profiles/branch-edge/preview",
            json=payload,
        )

    assert response.status_code == 200
    body = response.json()
    assert "hostname EDGE-R1" in body["commands"]
    assert "ip domain-name branch.lab" in body["commands"]
    assert "banner motd ^Managed by profile override^" in body["commands"]
    assert "ntp server 192.0.2.200" in body["commands"]


@pytest.mark.asyncio
async def test_resolve_device_targets_endpoint_filters_inventory_matches():
    app = create_app()
    payload = {"site": "msk-lab", "status": "reachable"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/selection/resolve",
            json=payload,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total_devices"] == 2
    assert [device["name"] for device in body["devices"]] == ["lab-r1", "lab-r2"]


@pytest.mark.asyncio
async def test_preflight_endpoint_reports_ready_mock_environment():
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/automation/preflight")

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["inventory_backend"] == "mock"
    assert body["execution_backend"] == "mock"
    assert body["matched_devices"] == 3
    assert body["reachable_devices"] == 2


@pytest.mark.asyncio
async def test_preflight_endpoint_reports_missing_netmiko_credentials():
    original_execution_backend = settings.execution_backend
    original_device_username = settings.device_username
    original_device_password = settings.device_password
    original_device_secret = settings.device_secret
    settings.execution_backend = "netmiko"
    settings.device_username = None
    settings.device_password = None
    settings.device_secret = None
    app = create_app()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/automation/preflight")
    finally:
        settings.execution_backend = original_execution_backend
        settings.device_username = original_device_username
        settings.device_password = original_device_password
        settings.device_secret = original_device_secret

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is False
    assert any(
        check["name"] == "execution_backend" and check["status"] == "failed"
        for check in body["checks"]
    )


@pytest.mark.asyncio
async def test_preflight_endpoint_reports_failed_selector_match():
    app = create_app()
    payload = {"site": "unknown-site"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/preflight",
            json=payload,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is False
    assert body["matched_devices"] == 0
    assert any(
        check["name"] == "target_selector" and check["status"] == "failed"
        for check in body["checks"]
    )


@pytest.mark.asyncio
async def test_check_base_configuration_compliance_endpoint_reports_drift():
    app = create_app()
    payload = {
        "hostname": "EDGE-R1",
        "domain_name": "branch.lab",
        "banner_motd": "Managed by compliance",
        "interfaces": [
            {
                "name": "GigabitEthernet0/1",
                "description": "Users VLAN gateway",
                "ipv4_address": "10.30.0.1/24",
                "enabled": True,
            }
        ],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/devices/lab-r1/base-config/compliance",
            json=payload,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["device_name"] == "lab-r1"
    assert body["compliant"] is False
    assert any(item["path"] == "hostname" for item in body["drift"])
    assert any(item["path"] == "interfaces.GigabitEthernet0/1.description" for item in body["drift"])


@pytest.mark.asyncio
async def test_check_base_configuration_from_profile_compliance_endpoint_becomes_compliant_after_apply():
    app = create_app()
    payload = {
        "hostname": "EDGE-R1",
        "interfaces": [
            {
                "name": "GigabitEthernet0/0",
                "description": "Primary ISP uplink",
                "ipv4_address": "198.51.100.1/30",
                "enabled": True,
            }
        ],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        before = await ac.post(
            "/api/automation/devices/lab-r1/base-config/profiles/branch-edge/compliance",
            json=payload,
        )
        apply_response = await ac.post(
            "/api/automation/devices/lab-r1/base-config/profiles/branch-edge/apply",
            json=payload,
        )
        after = await ac.post(
            "/api/automation/devices/lab-r1/base-config/profiles/branch-edge/compliance",
            json=payload,
        )

    assert before.status_code == 200
    assert apply_response.status_code == 200
    assert after.status_code == 200
    assert before.json()["compliant"] is False
    assert after.json()["compliant"] is True
    assert after.json()["drift"] == []


@pytest.mark.asyncio
async def test_check_base_configuration_compliance_batch_endpoint_returns_partial_results():
    app = create_app()
    payload = {
        "items": [
            {
                "device_name": "lab-r1",
                "request": {
                    "hostname": "EDGE-R1",
                },
            },
            {
                "device_name": "lab-r99",
                "request": {
                    "hostname": "MISSING-R99",
                },
            },
        ]
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/batch/base-config/compliance",
            json=payload,
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["summary"]["total_items"] == 2
    assert body["summary"]["successful_items"] == 1
    assert body["summary"]["failed_items"] == 1
    assert body["summary"]["drifted_items"] == 1
    assert body["items"][0]["status"] == "success"
    assert body["items"][0]["report"]["device_name"] == "lab-r1"
    assert body["items"][0]["report"]["compliant"] is False
    assert body["items"][1]["status"] == "failed"
    assert body["items"][1]["report"] is None
    assert "lab-r99" in body["items"][1]["detail"]


@pytest.mark.asyncio
async def test_check_base_configuration_batch_from_profile_endpoint_returns_partial_results():
    app = create_app()
    payload = {
        "items": [
            {
                "device_name": "lab-r1",
                "overrides": {
                    "hostname": "EDGE-R1",
                },
            },
            {
                "device_name": "lab-r99",
                "overrides": {
                    "hostname": "MISSING-R99",
                },
            },
        ]
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/batch/base-config/profiles/branch-edge/compliance",
            json=payload,
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["items"][0]["status"] == "success"
    assert body["items"][0]["report"]["device_name"] == "lab-r1"
    assert body["items"][1]["status"] == "failed"
    assert body["items"][1]["report"] is None
    assert "lab-r99" in body["items"][1]["detail"]


@pytest.mark.asyncio
async def test_check_base_configuration_compliance_for_selection_endpoint_uses_inventory_filters():
    app = create_app()
    payload = {
        "selector": {
            "site": "msk-lab",
            "status": "reachable",
        },
        "request": {
            "hostname": "EDGE-R1",
        },
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/selection/base-config/compliance",
            json=payload,
        )

    assert response.status_code == 200
    body = response.json()
    assert [item["device_name"] for item in body["items"]] == ["lab-r1", "lab-r2"]
    assert all(item["status"] == "success" for item in body["items"])


@pytest.mark.asyncio
async def test_check_base_configuration_from_profile_for_selection_returns_not_found_when_selector_matches_nothing():
    app = create_app()
    payload = {
        "selector": {
            "site": "unknown-site",
        },
        "overrides": {
            "hostname": "EDGE-R1",
        },
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/selection/base-config/profiles/branch-edge/compliance",
            json=payload,
        )

    assert response.status_code == 404
    assert "unknown-site" in response.json()["detail"]


@pytest.mark.asyncio
async def test_preview_base_configuration_for_selection_endpoint_returns_matched_devices():
    app = create_app()
    payload = {
        "selector": {
            "site": "msk-lab",
            "status": "reachable",
        },
        "request": {
            "hostname": "EDGE-R1",
        },
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/selection/base-config/preview",
            json=payload,
        )

    assert response.status_code == 200
    body = response.json()
    assert [item["device_name"] for item in body["items"]] == ["lab-r1", "lab-r2"]
    assert all(item["status"] == "success" for item in body["items"])


@pytest.mark.asyncio
async def test_apply_base_configuration_from_profile_for_selection_endpoint_handles_maintenance_devices():
    app = create_app()
    payload = {
        "selector": {
            "site": "spb-lab",
        },
        "overrides": {
            "hostname": "CORE-R3",
        },
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/selection/base-config/profiles/branch-edge/apply",
            json=payload,
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["summary"]["total_items"] == 1
    assert body["summary"]["successful_items"] == 0
    assert body["summary"]["failed_items"] == 1
    assert body["items"][0]["device_name"] == "lab-r3"
    assert body["items"][0]["status"] == "failed"
    assert body["items"][0]["result"] is None
    assert "maintenance mode" in body["items"][0]["detail"]


@pytest.mark.asyncio
async def test_apply_base_configuration_dry_run_endpoint():
    app = create_app()
    payload = {
        "hostname": "DIST-R2",
        "domain_name": "dist.lab",
        "banner_motd": "Preview only",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        before = await ac.get("/api/automation/devices/lab-r2/running-config")
        response = await ac.post(
            "/api/automation/devices/lab-r2/base-config/apply?dry_run=true",
            json=payload,
        )
        after = await ac.get("/api/automation/devices/lab-r2/running-config")
        snapshots = await ac.get("/api/automation/devices/lab-r2/snapshots")

    assert before.status_code == 200
    assert response.status_code == 200
    assert after.status_code == 200
    assert snapshots.status_code == 200
    assert response.json()["dry_run"] is True
    assert response.json()["changed"] is False
    assert response.json()["would_change"] is True
    assert response.json()["before"] != response.json()["after"]
    assert before.json() == after.json()
    assert snapshots.json() == []


@pytest.mark.asyncio
async def test_apply_base_configuration_from_profile_updates_running_config_endpoint():
    app = create_app()
    payload = {
        "hostname": "EDGE-R1",
        "interfaces": [
            {
                "name": "GigabitEthernet0/0",
                "description": "Primary ISP uplink",
                "ipv4_address": "198.51.100.1/30",
                "enabled": True,
            }
        ],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/devices/lab-r1/base-config/profiles/branch-edge/apply",
            json=payload,
        )
        running = await ac.get("/api/automation/devices/lab-r1/running-config")
        snapshots = await ac.get("/api/automation/devices/lab-r1/snapshots")

    assert response.status_code == 200
    assert running.status_code == 200
    assert snapshots.status_code == 200
    assert response.json()["changed"] is True
    assert response.json()["snapshot_id"] is not None
    assert len(snapshots.json()) == 1
    assert snapshots.json()[0]["snapshot_id"] == response.json()["snapshot_id"]
    assert "hostname EDGE-R1" in running.json()["lines"]
    assert "ip domain-name branch.lab" in running.json()["lines"]
    assert "ntp server 192.0.2.200" in running.json()["lines"]


@pytest.mark.asyncio
async def test_rollback_endpoint_restores_previous_running_config():
    app = create_app()
    payload = {
        "hostname": "EDGE-R1",
        "domain_name": "edge.lab",
        "banner_motd": "Managed by automation",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        before = await ac.get("/api/automation/devices/lab-r1/running-config")
        apply_response = await ac.post(
            "/api/automation/devices/lab-r1/base-config/apply",
            json=payload,
        )
        snapshot_id = apply_response.json()["snapshot_id"]
        changed = await ac.get("/api/automation/devices/lab-r1/running-config")
        rollback_response = await ac.post(
            f"/api/automation/devices/lab-r1/rollback/{snapshot_id}"
        )
        restored = await ac.get("/api/automation/devices/lab-r1/running-config")

    assert before.status_code == 200
    assert apply_response.status_code == 200
    assert changed.status_code == 200
    assert rollback_response.status_code == 200
    assert restored.status_code == 200
    assert before.json() != changed.json()
    assert rollback_response.json()["snapshot_id"] == snapshot_id
    assert rollback_response.json()["changed"] is True
    assert restored.json() == before.json()


@pytest.mark.asyncio
async def test_apply_base_configuration_batch_from_profile_endpoint_returns_partial_results():
    app = create_app()
    payload = {
        "items": [
            {
                "device_name": "lab-r1",
                "overrides": {
                    "hostname": "EDGE-R1",
                },
            },
            {
                "device_name": "lab-r3",
                "overrides": {
                    "hostname": "CORE-R3",
                },
            },
        ]
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/batch/base-config/profiles/branch-edge/apply",
            json=payload,
        )
        running = await ac.get("/api/automation/devices/lab-r1/running-config")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["items"][0]["status"] == "success"
    assert body["items"][0]["result"]["device_name"] == "lab-r1"
    assert body["items"][0]["result"]["backend"] == "mock"
    assert body["items"][0]["result"]["snapshot_id"] is not None
    assert body["items"][1]["status"] == "failed"
    assert body["items"][1]["result"] is None
    assert "maintenance mode" in body["items"][1]["detail"]
    assert running.status_code == 200
    assert "hostname EDGE-R1" in running.json()["lines"]


@pytest.mark.asyncio
async def test_apply_base_configuration_rejects_maintenance_device_endpoint():
    app = create_app()
    payload = {
        "hostname": "CORE-R3",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/devices/lab-r3/base-config/apply",
            json=payload,
        )

    assert response.status_code == 409
    assert "maintenance mode" in response.json()["detail"]


@pytest.mark.asyncio
async def test_preview_base_configuration_returns_not_found_for_unknown_device():
    app = create_app()
    payload = {
        "hostname": "UNKNOWN-R1",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/devices/lab-r99/base-config/preview",
            json=payload,
        )

    assert response.status_code == 404
    assert "lab-r99" in response.json()["detail"]


@pytest.mark.asyncio
async def test_profile_endpoint_returns_not_found_for_unknown_profile():
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/automation/profiles/unknown-profile")

    assert response.status_code == 404
    assert "unknown-profile" in response.json()["detail"]

@pytest.mark.asyncio
async def test_diagnostics_endpoint_reports_mock_environment_ok():
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/automation/diagnostics")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["inventory_backend"] == "mock"
    assert body["execution_backend"] == "mock"
    assert body["matched_devices"] == 3


@pytest.mark.asyncio
async def test_diagnostics_endpoint_reports_failed_selector_match():
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/automation/diagnostics",
            json={"site": "unknown-site"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["matched_devices"] == 0
    assert any(
        check["name"] == "target_selector" and check["status"] == "failed"
        for check in body["checks"]
    )

@pytest.mark.asyncio
async def test_reset_demo_state_endpoint_clears_mock_runtime_and_history():
    app = create_app()
    payload = {
        "hostname": "EDGE-R1",
        "domain_name": "branch.lab",
        "banner_motd": "Reset endpoint test",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        apply_response = await ac.post(
            "/api/automation/devices/lab-r1/base-config/apply",
            json=payload,
        )
        assert apply_response.status_code == 200

        reset_response = await ac.post("/api/automation/demo/reset")
        running_config_response = await ac.get("/api/automation/devices/lab-r1/running-config")
        operations_response = await ac.get("/api/automation/operations")
        snapshots_response = await ac.get("/api/automation/devices/lab-r1/snapshots")

    assert reset_response.status_code == 200
    reset_body = reset_response.json()
    assert reset_body["execution_backend"] == "mock"
    assert reset_body["devices_reset"] == 3
    assert reset_body["snapshots_cleared"] >= 1
    assert reset_body["operations_cleared"] >= 1
    assert running_config_response.status_code == 200
    assert running_config_response.json()["lines"][0] == "hostname R1"
    assert operations_response.json() == []
    assert snapshots_response.json() == []

