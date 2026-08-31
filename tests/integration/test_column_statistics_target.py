import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table
from sqlalchemy.engine import Engine

from tests.alembic_helpers import AlembicRunner
from tests.utils import get_pg_column_stat_target


@pytest.mark.usefixtures("clean_db")
def test_column_statistics_target_lifecycle(engine: Engine):
    """
    Test setting target, modifying target, resetting to default, and downgrading.
    """
    metadata = MetaData()
    Table(
        "users",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("age", Integer, info={"ext_stats": {"target": 1000}}),
        Column("name", String(50)),
    )

    runner = AlembicRunner(engine, metadata)
    try:
        # 1. Initial migration: create table and set stats target to 1000
        script1 = runner.autogenerate("create_users_with_target")
        assert (
            "alter_column_statistics_target('public', 'users', 'age', '1000')"
            in script1
        )
        runner.upgrade("head")

        with engine.connect() as conn:
            target = get_pg_column_stat_target(conn, "public", "users", "age")
            assert target == 1000

            name_target = get_pg_column_stat_target(conn, "public", "users", "name")
            assert name_target is None or name_target == -1

        # 2. Update target to 500
        metadata2 = MetaData()
        Table(
            "users",
            metadata2,
            Column("id", Integer, primary_key=True),
            Column("age", Integer, info={"ext_stats": {"target": 500}}),
            Column("name", String(50)),
        )
        runner.set_metadata(metadata2)
        script2 = runner.autogenerate("update_age_target_500")
        assert (
            "alter_column_statistics_target('public', 'users', 'age', '500', 1000)"
            in script2
        )
        runner.upgrade("head")

        with engine.connect() as conn:
            target = get_pg_column_stat_target(conn, "public", "users", "age")
            assert target == 500

        # 3. Downgrade step 2 -> should revert target back to 1000
        runner.downgrade("-1")
        with engine.connect() as conn:
            target = get_pg_column_stat_target(conn, "public", "users", "age")
            assert target == 1000

        # Upgrade back to head
        runner.upgrade("head")
        with engine.connect() as conn:
            target = get_pg_column_stat_target(conn, "public", "users", "age")
            assert target == 500

        # 4. Reset target to default
        metadata3 = MetaData()
        Table(
            "users",
            metadata3,
            Column("id", Integer, primary_key=True),
            Column("age", Integer),  # No target specified
            Column("name", String(50)),
        )
        runner.set_metadata(metadata3)
        script3 = runner.autogenerate("reset_age_target_default")
        assert (
            "alter_column_statistics_target('public', 'users', 'age', 'default', 500)"
            in script3
        )
        runner.upgrade("head")

        with engine.connect() as conn:
            target = get_pg_column_stat_target(conn, "public", "users", "age")
            assert target == None or target == -1  # Default target

    finally:
        runner.cleanup()


@pytest.mark.usefixtures("clean_db")
def test_column_statistics_target_custom_schema(engine: Engine):
    """
    Test column statistics target on a non-public schema.
    """
    schema_metadata = MetaData(schema="test_schema")
    Table(
        "products",
        schema_metadata,
        Column("id", Integer, primary_key=True),
        Column("price", Integer, info={"ext_stats": {"target": 2500}}),
    )

    runner = AlembicRunner(engine, schema_metadata, schema="test_schema")
    try:
        script = runner.autogenerate("create_test_products")
        assert (
            "alter_column_statistics_target('test_schema', 'products', 'price', '2500')"
            in script
        )
        runner.upgrade("head")

        with engine.connect() as conn:
            target = get_pg_column_stat_target(conn, "test_schema", "products", "price")
            assert target == 2500

    finally:
        runner.cleanup()
