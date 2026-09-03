import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table
from sqlalchemy.engine import Engine

from sqlalchemy_extended_statistics_extension.extended_statistic.sqlalchemy import (
    DEPENDENCIES,
    MCV,
    NDISTINCT,
    ExtendedStatistics,
)
from tests.alembic_helpers import AlembicRunner
from tests.utils import get_pg_extended_stats


@pytest.mark.usefixtures("clean_db")
def test_extended_statistics_lifecycle(engine: Engine):
    """
    Test creation, multiple kinds, modification, drop, and downgrade for extended statistics.
    """
    metadata = MetaData()
    Table(
        "orders",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("user_id", Integer),
        Column("city", String(50)),
        Column("state", String(50)),
        ExtendedStatistics(
            "orders_city_state_stats", [NDISTINCT, DEPENDENCIES], "city", "state"
        ),
        ExtendedStatistics(None, [MCV], "user_id", "city"),
    )

    runner = AlembicRunner(engine, metadata)
    try:
        # 1. Initial migration: create table & statistics
        script1 = runner.autogenerate("create_orders_with_stats")
        assert (
            "create_statistics('public', 'orders', 'orders_city_state_stats'" in script1
        )
        assert (
            "create_statistics('public', 'orders', 'public_orders_user_id_city_stats'"
            in script1
        )

        runner.upgrade("head")

        with engine.connect() as conn:
            stats = get_pg_extended_stats(conn, "public", "orders")
            assert "orders_city_state_stats" in stats
            assert stats["orders_city_state_stats"]["kinds"] == {
                "NDISTINCT",
                "DEPENDENCIES",
            }
            assert stats["orders_city_state_stats"]["columns"] == ["city", "state"]

            assert "public_orders_user_id_city_stats" in stats
            assert stats["public_orders_user_id_city_stats"]["kinds"] == {"MCV"}
            assert stats["public_orders_user_id_city_stats"]["columns"] == [
                "user_id",
                "city",
            ]

        # 2. Modify statistics: drop user_id_city, keep city_state with only NDISTINCT, add user_id_state
        metadata2 = MetaData()
        Table(
            "orders",
            metadata2,
            Column("id", Integer, primary_key=True),
            Column("user_id", Integer),
            Column("city", String(50)),
            Column("state", String(50)),
            ExtendedStatistics("orders_city_state_stats", [NDISTINCT], "city", "state"),
            ExtendedStatistics("orders_user_state_stats", [MCV], "user_id", "state"),
        )
        runner.set_metadata(metadata2)
        script2 = runner.autogenerate("update_orders_stats")
        # In comparator, existing stats on table in DB are dropped and new ones defined in metadata are recreated
        assert "drop_statistics" in script2
        assert (
            "create_statistics('public', 'orders', 'orders_user_state_stats'" in script2
        )

        runner.upgrade("head")

        with engine.connect() as conn:
            stats = get_pg_extended_stats(conn, "public", "orders")
            assert "public_orders_user_id_city_stats" not in stats
            assert "orders_city_state_stats" in stats
            assert stats["orders_city_state_stats"]["kinds"] == {"NDISTINCT"}
            assert "orders_user_state_stats" in stats

        # 3. Downgrade step 2
        runner.downgrade("-1")
        with engine.connect() as conn:
            stats = get_pg_extended_stats(conn, "public", "orders")
            # Dropped stats are recreated upon downgrade because CreateStatisticsOp.reverse() is DropStatisticsOp
            assert "orders_user_state_stats" not in stats

    finally:
        runner.cleanup()


@pytest.mark.usefixtures("clean_db")
def test_extended_statistics_custom_schema(engine: Engine):
    """
    Test extended statistics in a non-public schema.
    """
    schema_metadata = MetaData(schema="test_schema")
    Table(
        "items",
        schema_metadata,
        Column("id", Integer, primary_key=True),
        Column("category", String(50)),
        Column("subcategory", String(50)),
        ExtendedStatistics(
            "test_items_cat_subcat_stats", [NDISTINCT, MCV], "category", "subcategory"
        ),
    )

    runner = AlembicRunner(engine, schema_metadata, schema="test_schema")
    try:
        script = runner.autogenerate("create_test_items_stats")
        assert (
            "create_statistics('test_schema', 'items', 'test_items_cat_subcat_stats'"
            in script
        )

        runner.upgrade("head")

        with engine.connect() as conn:
            stats = get_pg_extended_stats(conn, "test_schema", "items")
            assert "test_items_cat_subcat_stats" in stats
            assert stats["test_items_cat_subcat_stats"]["kinds"] == {"NDISTINCT", "MCV"}
            assert stats["test_items_cat_subcat_stats"]["columns"] == [
                "category",
                "subcategory",
            ]

    finally:
        runner.cleanup()
