from collections.abc import Callable, Generator
from pathlib import Path
import socket
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, Session, create_engine
from app.core.config import settings
from app.core.database import get_session
from app.main import app


@pytest.fixture(autouse=True)
def low_cost_password_hasher(monkeypatch: pytest.MonkeyPatch):
    from argon2 import PasswordHasher
    from app.auth import security

    hasher = PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)
    monkeypatch.setattr(security, "_password_hasher", hasher)
    monkeypatch.setattr(
        security,
        "DUMMY_PASSWORD_HASH",
        hasher.hash("mis-eventos-dummy-password"),
    )
    monkeypatch.setattr(settings, "bootstrap_admin_email", None)
    monkeypatch.setattr(settings, "bootstrap_admin_password", None)
    return hasher


def _resolve_db_url(raw_url: str) -> str:
    url = raw_url
    if "@db:" in url:
        try:
            socket.gethostbyname("db")
        except socket.gaierror:
            url = url.replace("@db:", "@127.0.0.1:")
    elif "@localhost:" in url:
        url = url.replace("@localhost:", "@127.0.0.1:")
    return url


def _run_migrations(db_url: str) -> None:
    backend_dir = Path(__file__).resolve().parent.parent
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")


@pytest.fixture(scope="session")
def test_engine() -> Generator[Engine, None, None]:
    main_url = _resolve_db_url(settings.database_url)
    url = _resolve_db_url(settings.test_database_url)
    eng = create_engine(url, pool_pre_ping=True)
    assert eng.dialect.name == "postgresql", (
        "R3.6 violation: tests must run exclusively against PostgreSQL"
    )
    _run_migrations(main_url)
    _run_migrations(url)
    yield eng
    eng.dispose()


@pytest.fixture()
def db_session(test_engine: Engine) -> Generator[Session, None, None]:
    connection = test_engine.connect()
    outer_tx = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        outer_tx.rollback()
        connection.close()


@pytest.fixture()
def db_truncate(test_engine: Engine) -> Generator[Callable[[], None], None, None]:
    def _truncate() -> None:
        table_names = [table.name for table in SQLModel.metadata.sorted_tables]
        if not table_names:
            return
        quoted = ", ".join(f'"{name}"' for name in table_names)
        with test_engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE;"))

    yield _truncate
    _truncate()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _override_get_session() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()

