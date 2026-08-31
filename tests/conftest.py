import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
import os

from testcontainers.community.postgres import PostgresContainer


@pytest.fixture(scope="session")
def postgres_url():
    """Returns PostgreSQL connection URL either from env var or via testcontainers."""
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        yield env_url
        return

    with PostgresContainer("postgres:18-alpine") as postgres:
        url = postgres.get_connection_url()
        yield url


@pytest.fixture(scope="session")
def engine(postgres_url: str):
    """Session-scoped SQLAlchemy engine with NullPool."""
    from sqlalchemy.pool import NullPool
    eng = create_engine(postgres_url, poolclass=NullPool)
    yield eng
    eng.dispose()


@pytest.fixture
def clean_db(engine: Engine):
    """Resets schemas before a test runs."""
    with engine.begin() as conn:
        conn.execute(text('DROP SCHEMA IF EXISTS "test_schema" CASCADE;'))
        conn.execute(text('DROP SCHEMA IF EXISTS "custom-schema" CASCADE;'))
        conn.execute(text('DROP SCHEMA IF EXISTS "MixedCaseSchema" CASCADE;'))
        conn.execute(text('DROP SCHEMA IF EXISTS public CASCADE;'))
        conn.execute(text('CREATE SCHEMA public;'))
        conn.execute(text('GRANT ALL ON SCHEMA public TO PUBLIC;'))
        conn.execute(text('GRANT ALL ON SCHEMA public TO CURRENT_USER;'))
        conn.execute(text('CREATE SCHEMA test_schema;'))
        conn.execute(text('GRANT ALL ON SCHEMA test_schema TO PUBLIC;'))
        conn.execute(text('GRANT ALL ON SCHEMA test_schema TO CURRENT_USER;'))
    yield
