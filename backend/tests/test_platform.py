from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session


def test_plat_ac_11_postgres_test_db_and_pg_trgm_enabled(
    db_session: Session,
    db_truncate,
) -> None:
    bind = db_session.get_bind()
    assert bind.dialect.name == "postgresql"

    current_db = db_session.exec(text("SELECT current_database()")).scalar_one()
    assert current_db == "mis_eventos_test"

    ext_name = db_session.exec(
        text("SELECT extname FROM pg_extension WHERE extname = 'pg_trgm'")
    ).scalar_one_or_none()
    assert ext_name == "pg_trgm"

    similarity_score = db_session.exec(
        text("SELECT similarity('concierto', 'conciertos')")
    ).scalar_one()
    assert similarity_score > 0.5

    version_num = db_session.exec(
        text("SELECT version_num FROM alembic_version")
    ).scalar_one_or_none()
    assert version_num == "0002_create_users"
    assert callable(db_truncate)


def test_plat_ac_01_health_returns_ok_when_db_and_redis_up(
    client: TestClient,
) -> None:
    from app.core.cache import cache_client

    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "redis": "ok",
    }
    assert cache_client.set("plat:test:key", {"count": 1}, ttl_seconds=30) is True
    assert cache_client.get("plat:test:key") == {"count": 1}
    assert cache_client.invalidate_prefix("plat:test:") is True
    assert cache_client.get("plat:test:key") is None


def test_plat_ac_02_health_and_cache_degrade_gracefully_when_redis_down(
    client: TestClient,
) -> None:
    from app.core.cache import CacheClient, get_cache_client
    from app.main import app

    broken_cache = CacheClient(redis_url="redis://127.0.0.1:6399/0", timeout=0.1)
    assert broken_cache.ping() is False
    assert broken_cache.get("any:key") is None
    assert broken_cache.set("any:key", {"a": 1}) is False
    assert broken_cache.invalidate_prefix("any:") is False

    app.dependency_overrides[get_cache_client] = lambda: broken_cache
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "redis": "degraded",
    }


def test_plat_ac_03_health_returns_503_in_spanish_when_db_down(
    client: TestClient,
) -> None:
    from sqlalchemy.exc import OperationalError
    from app.core.database import get_session
    from app.main import app

    class BrokenSession:
        def exec(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("db unreachable"))

    app.dependency_overrides[get_session] = lambda: BrokenSession()
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"detail": "Servicio de base de datos no disponible"}


def test_plat_ac_04_openapi_and_docs_exposed_without_open_cors(
    client: TestClient,
) -> None:
    import importlib
    from app.main import app

    openapi_res = client.get(
        "/api/openapi.json",
        headers={"Origin": "http://evil.example.com"},
    )
    assert openapi_res.status_code == 200
    assert "access-control-allow-origin" not in {
        k.lower() for k in openapi_res.headers.keys()
    }
    schema = openapi_res.json()
    assert schema["openapi"].startswith("3.")
    assert schema["info"]["title"] == "Mis Eventos API"
    assert "/api/health" in schema["paths"]

    docs_res = client.get(
        "/api/docs",
        headers={"Origin": "http://evil.example.com"},
    )
    assert docs_res.status_code == 200
    assert "/api/openapi.json" in docs_res.text
    assert "access-control-allow-origin" not in {
        k.lower() for k in docs_res.headers.keys()
    }

    middleware_names = [m.cls.__name__ for m in app.user_middleware]
    assert "CORSMiddleware" not in middleware_names

    for domain_pkg in (
        "app.auth",
        "app.users",
        "app.events",
        "app.sessions",
        "app.registrations",
    ):
        assert importlib.import_module(domain_pkg) is not None


def test_plat_ac_05_http_errors_return_spanish_detail_string(
    client: TestClient,
) -> None:
    not_found_res = client.get("/api/non-existent-route")
    assert not_found_res.status_code == 404
    assert not_found_res.json() == {"detail": "Recurso no encontrado"}

    method_not_allowed_res = client.post("/api/health")
    assert method_not_allowed_res.status_code == 405
    assert method_not_allowed_res.json() == {"detail": "Método no permitido"}


def test_plat_ac_06_validation_error_422_normalized_to_spanish(
    client: TestClient,
) -> None:
    from pydantic import BaseModel, Field
    from app.main import app

    class SamplePayload(BaseModel):
        title: str = Field(min_length=3, max_length=20)
        capacity: int = Field(ge=1, le=50)

    @app.post("/api/_test/validation")
    def _validate_payload(payload: SamplePayload) -> dict[str, str]:
        return {"ok": payload.title}

    res = client.post(
        "/api/_test/validation",
        json={"title": "ab", "capacity": 100},
    )
    assert res.status_code == 422
    data = res.json()
    assert isinstance(data["detail"], str)
    assert "Error de validación" in data["detail"]
    assert isinstance(data["errors"], list)
    fields = {err["field"]: err["message"] for err in data["errors"]}
    assert "title" in fields
    assert "capacity" in fields
    assert "Input should" not in res.text
    assert "Field required" not in res.text

    missing_res = client.post("/api/_test/validation", json={})
    assert missing_res.status_code == 422
    missing_data = missing_res.json()
    assert isinstance(missing_data["detail"], str)
    assert any(
        "obligatorio" in err["message"].lower() for err in missing_data["errors"]
    )

    bad_json_res = client.post(
        "/api/_test/validation",
        content="{invalid-json",
        headers={"Content-Type": "application/json"},
    )
    assert bad_json_res.status_code == 422
    bad_json_data = bad_json_res.json()
    assert bad_json_data["detail"] == "El cuerpo de la petición no es un JSON válido"
    assert isinstance(bad_json_data["errors"], list)
    app.router.routes = [
        r for r in app.router.routes if getattr(r, "path", None) != "/api/_test/validation"
    ]


def test_plat_ac_07_unhandled_exception_returns_generic_500_in_spanish(
    client: TestClient,
) -> None:
    from app.main import app

    @app.get("/api/_test/boom")
    def _boom() -> None:
        raise RuntimeError("SELECT * FROM users WHERE password_hash = 'secret'")

    try:
        res = client.get("/api/_test/boom")
        assert res.status_code == 500
        assert res.json() == {"detail": "Error interno del servidor"}
        assert "SELECT * FROM users" not in res.text
        assert "Traceback" not in res.text
    finally:
        app.router.routes = [
            r for r in app.router.routes if getattr(r, "path", None) != "/api/_test/boom"
        ]


def test_plat_ac_08_pagination_envelope_and_defaults(
    client: TestClient,
) -> None:
    from fastapi import Depends
    from app.core.pagination import (
        PaginatedResponse,
        PaginationParams,
        build_paginated_response,
    )
    from app.main import app

    all_items = [f"item-{i}" for i in range(1, 26)]

    @app.get("/api/_test/items", response_model=PaginatedResponse[str])
    def _list_items(
        params: PaginationParams = Depends(),
        empty: bool = False,
    ) -> PaginatedResponse[str]:
        if empty:
            return build_paginated_response([], 0, params)
        sliced = all_items[params.offset : params.offset + params.size]
        return build_paginated_response(sliced, len(all_items), params)

    try:
        default_res = client.get("/api/_test/items")
        assert default_res.status_code == 200
        assert default_res.json() == {
            "items": [f"item-{i}" for i in range(1, 11)],
            "total": 25,
            "page": 1,
            "size": 10,
            "pages": 3,
        }

        page3_res = client.get("/api/_test/items?page=3&size=10")
        assert page3_res.status_code == 200
        assert page3_res.json() == {
            "items": [f"item-{i}" for i in range(21, 26)],
            "total": 25,
            "page": 3,
            "size": 10,
            "pages": 3,
        }

        beyond_res = client.get("/api/_test/items?page=5&size=10")
        assert beyond_res.status_code == 200
        assert beyond_res.json() == {
            "items": [],
            "total": 25,
            "page": 5,
            "size": 10,
            "pages": 3,
        }

        empty_res = client.get("/api/_test/items?empty=true")
        assert empty_res.status_code == 200
        assert empty_res.json() == {
            "items": [],
            "total": 0,
            "page": 1,
            "size": 10,
            "pages": 0,
        }
    finally:
        app.router.routes = [
            r for r in app.router.routes if getattr(r, "path", None) != "/api/_test/items"
        ]


def test_plat_ac_09_pagination_rejects_out_of_range_params_with_spanish_422(
    client: TestClient,
) -> None:
    from fastapi import Depends
    from app.core.pagination import (
        PaginatedResponse,
        PaginationParams,
        build_paginated_response,
    )
    from app.main import app

    @app.get("/api/_test/items-range", response_model=PaginatedResponse[str])
    def _list_items_range(
        params: PaginationParams = Depends(),
    ) -> PaginatedResponse[str]:
        return build_paginated_response([], 0, params)

    try:
        for invalid_query, expected_field in (
            ("page=0", "page"),
            ("size=0", "size"),
            ("size=51", "size"),
        ):
            res = client.get(f"/api/_test/items-range?{invalid_query}")
            assert res.status_code == 422
            payload = res.json()
            assert isinstance(payload["detail"], str)
            assert "Error de validación" in payload["detail"]
            assert any(err["field"] == expected_field for err in payload["errors"])
    finally:
        app.router.routes = [
            r
            for r in app.router.routes
            if getattr(r, "path", None) != "/api/_test/items-range"
        ]


def test_plat_ac_10_datetime_normalized_and_serialized_in_utc() -> None:
    from datetime import datetime, timedelta, timezone
    from pydantic import BaseModel
    from app.core.datetime_utils import UTCDateTime, ensure_utc, utc_now

    class EventTimeSchema(BaseModel):
        starts_at: UTCDateTime

    now = utc_now()
    assert now.tzinfo == timezone.utc

    naive = datetime(2026, 10, 31, 15, 30, 0)
    normalized_naive = ensure_utc(naive)
    assert normalized_naive.tzinfo == timezone.utc
    assert normalized_naive.hour == 15

    bogota_tz = timezone(timedelta(hours=-5))
    bogota_dt = datetime(2026, 10, 31, 10, 30, 0, tzinfo=bogota_tz)
    normalized_offset = ensure_utc(bogota_dt)
    assert normalized_offset.tzinfo == timezone.utc
    assert normalized_offset.hour == 15

    model = EventTimeSchema(starts_at="2026-10-31T10:30:00-05:00")
    assert model.starts_at.tzinfo == timezone.utc
    assert model.starts_at.hour == 15
    dumped = model.model_dump(mode="json")
    assert dumped["starts_at"] == "2026-10-31T15:30:00Z"


def test_plat_ac_12_docker_compose_and_nginx_gateway_routing() -> None:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    nginx_conf_path = repo_root / "infra" / "nginx" / "default.conf"
    compose_path = repo_root / "docker-compose.yml"
    backend_dockerfile = repo_root / "backend" / "Dockerfile"
    frontend_dockerfile = repo_root / "frontend" / "Dockerfile"
    env_example_path = repo_root / ".env.example"
    backend_readme = repo_root / "backend" / "README.md"

    assert nginx_conf_path.is_file()
    nginx_conf = nginx_conf_path.read_text(encoding="utf-8")
    assert "location /api/media/" in nginx_conf
    assert "alias /var/www/media/;" in nginx_conf
    assert "location /api/" in nginx_conf
    assert "proxy_pass http://api:8000/api/;" in nginx_conf
    assert "location /" in nginx_conf
    assert "proxy_pass http://web:80/;" in nginx_conf
    assert "client_max_body_size 10M;" in nginx_conf

    assert compose_path.is_file()
    compose_text = compose_path.read_text(encoding="utf-8")
    for svc in ("gateway:", "web:", "api:", "db:", "redis:"):
        assert svc in compose_text
    assert "/var/www/media:ro" in compose_text
    assert "/app/media" in compose_text
    assert "alembic upgrade head" in compose_text

    assert backend_dockerfile.is_file()
    assert "python:3.14-slim" in backend_dockerfile.read_text(encoding="utf-8")

    assert frontend_dockerfile.is_file()
    frontend_df_text = frontend_dockerfile.read_text(encoding="utf-8")
    assert "node:22-alpine" in frontend_df_text
    assert "nginx:1.27-alpine" in frontend_df_text

    assert env_example_path.is_file()
    env_example = env_example_path.read_text(encoding="utf-8")
    for mcp_var in (
        "CONTEXT7_API_KEY=",
        "GITHUB_PERSONAL_ACCESS_TOKEN=",
        "BROWSER_PATH=",
        "DEV_DATABASE_URI=",
    ):
        assert mcp_var in env_example
    for app_var in (
        "GATEWAY_PORT=",
        "POSTGRES_USER=",
        "POSTGRES_PASSWORD=",
        "POSTGRES_DB=",
        "POSTGRES_TEST_DB=",
        "DATABASE_URL=",
        "TEST_DATABASE_URL=",
        "REDIS_URL=",
        "MEDIA_ROOT=",
        "JWT_SECRET_KEY=",
    ):
        assert app_var in env_example

    assert backend_readme.is_file()
    assert len(backend_readme.read_text(encoding="utf-8").strip()) > 100













