from fastapi.testclient import TestClient


def test_auth_ac_28_openapi_exposes_bearer_and_no_password_hash(
    client: TestClient,
) -> None:
    res = client.get("/api/openapi.json")
    assert res.status_code == 200
    spec = res.json()

    security_schemes = spec.get("components", {}).get("securitySchemes", {})
    assert "HTTPBearer" in security_schemes
    assert security_schemes["HTTPBearer"]["type"] == "http"
    assert security_schemes["HTTPBearer"]["scheme"] == "bearer"
    assert security_schemes["HTTPBearer"].get("bearerFormat") == "JWT"

    paths = spec["paths"]
    assert "post" in paths["/api/auth/register"]
    assert "post" in paths["/api/auth/login"]
    assert "get" in paths["/api/auth/me"]
    assert "patch" in paths["/api/auth/me"]
    assert "get" in paths["/api/users"]
    assert "get" in paths["/api/users/{user_id}"]
    assert "patch" in paths["/api/users/{user_id}"]

    for forbidden_path in (
        "/api/auth/logout",
        "/api/auth/refresh",
    ):
        assert forbidden_path not in paths
    assert "delete" not in paths["/api/users/{user_id}"]
    assert "post" not in paths["/api/users"]

    schemas = spec.get("components", {}).get("schemas", {})
    assert "UserRead" in schemas
    user_read_props = schemas["UserRead"]["properties"]
    assert set(user_read_props.keys()) == {
        "id",
        "email",
        "full_name",
        "role",
        "is_active",
        "created_at",
        "updated_at",
    }
    assert "password_hash" not in res.text
