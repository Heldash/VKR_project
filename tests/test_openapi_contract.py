from app.main import create_app


def test_openapi_schema_includes_key_mvp_paths():
    schema = create_app().openapi()
    paths = schema["paths"]

    assert "/api/automation/preflight" in paths
    assert "/api/automation/diagnostics" in paths
    assert "/api/automation/devices/{device_name}/base-config/preview" in paths
    assert "/api/automation/devices/{device_name}/base-config/apply" in paths
    assert "/api/automation/selection/base-config/profiles/{profile_name}/apply" in paths
    assert "/api/automation/operations/summary" in paths


def test_openapi_schema_uses_expected_project_metadata():
    schema = create_app().openapi()

    assert schema["info"]["title"] == "NetAuto MVP"
    assert schema["info"]["version"] == "0.1.0"
