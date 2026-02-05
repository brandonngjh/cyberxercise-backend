from __future__ import annotations

import os
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.settings import Settings, get_settings
from app.db.deps import get_db_session
from app.db.session import create_engine, create_sessionmaker
from app.main import create_app


if not os.getenv("CI"):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

def _get_test_database_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")

    # Local only: allow deriving TEST_DATABASE_URL from DATABASE_URL
    if not url and not os.getenv("CI"):
        base = os.getenv("DATABASE_URL")
        if base:
            parsed = urlparse(base)
            db_name = (parsed.path or "").lstrip("/")
            if db_name and not db_name.endswith("_test"):
                url = parsed._replace(path=f"/{db_name}_test").geturl()

    if not url:
        raise RuntimeError(
            "TEST_DATABASE_URL is required for tests. "
        )

    # Safety check: MUST be a test database
    parsed = urlparse(url)
    db_name = (parsed.path or "").lstrip("/")
    if not db_name.endswith("_test"):
        raise RuntimeError(
            f"Refusing to run tests on non-test database '{db_name}'. "
            "TEST_DATABASE_URL must end with '_test'."
        )

    return url



@pytest.fixture(scope="session")
def test_database_url() -> str:
    return _get_test_database_url()


@pytest_asyncio.fixture(scope="session")
async def db_engine(test_database_url: str) -> AsyncEngine:
    engine = create_engine(test_database_url, echo=False)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def db_sessionmaker(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_sessionmaker(db_engine)


async def _truncate_public_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        rows = await conn.exec_driver_sql(
            """
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
            """
        )
        table_names = [r[0] for r in rows.fetchall()]
        table_names = [t for t in table_names if t != "alembic_version"]
        if not table_names:
            return

        quoted = ", ".join(f'"{t}"' for t in table_names)
        await conn.exec_driver_sql(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE")


@pytest_asyncio.fixture(autouse=True)
async def _clean_db(db_engine: AsyncEngine):
    # IMPORTANT: assumes schema already exists (migrations run beforehand)
    await _truncate_public_tables(db_engine)


@pytest.fixture
def app(test_database_url: str, db_sessionmaker: async_sessionmaker[AsyncSession]):
    app = create_app()

    def override_settings() -> Settings:
        # Keep JWT secret deterministic in tests
        return Settings(
            database_url=test_database_url,
            jwt_secret="test-jwt-secret",
            allow_instructor_register=False,
        )

    async def override_db_session():
        async with db_sessionmaker() as session:
            yield session

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_db_session] = override_db_session
    return app


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with LifespanManager(app):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest_asyncio.fixture
async def db_session(db_sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncSession:
    async with db_sessionmaker() as session:
        yield session
