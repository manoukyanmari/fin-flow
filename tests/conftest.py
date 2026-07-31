import os

# app.database reads DATABASE_URL at import time, so it has to exist before the
# application package is imported below. Port 5433 is where docker-compose
# publishes the database on the host, chosen to avoid colliding with a
# PostgreSQL already listening on the default 5432.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5433/app",
)

from collections.abc import Generator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

# Tests run against PostgreSQL, not SQLite: SQLite leaves foreign keys off by
# default, so the cascade test would pass without proving anything.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", os.environ["DATABASE_URL"])


@pytest.fixture(scope="session")
def engine() -> Generator[Engine, None, None]:
    eng = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def clean_tables(engine: Engine) -> Generator[None, None, None]:
    """Start each test from an empty database with predictable ids."""
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE users RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def client(engine: Engine) -> Generator[TestClient, None, None]:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
