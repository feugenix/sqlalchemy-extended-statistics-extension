import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, text
from sqlalchemy.engine import Engine

from sqlalchemy_extended_statistics_extension.extended_statistic.sqlalchemy import (
    DEPENDENCIES,
    MCV,
    NDISTINCT,
    ExtendedStatistics,
)
from tests.alembic_helpers import AlembicRunner
from tests.utils import get_pg_column_stat_target, get_pg_extended_stats


@pytest.mark.usefixtures("clean_db")
def test_column_statistics_target_quoted_identifiers(engine: Engine):
    """
    Test column statistics target on schemas, tables, and columns requiring quoting:
    - Reserved keywords (e.g. 'order', 'user', 'select')
    - Mixed casing (e.g. 'CustomSchema', 'OrderDetails', 'ItemCount')
    - Special / disallowed characters (e.g. hyphens, spaces, parentheses)
    """
    schema_name = "custom-schema"
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}";'))
        conn.execute(text(f'GRANT ALL ON SCHEMA "{schema_name}" TO PUBLIC;'))
        conn.execute(text(f'GRANT ALL ON SCHEMA "{schema_name}" TO CURRENT_USER;'))

    metadata = MetaData(schema=schema_name)
    Table(
        "Order Details",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("user", Integer, info={"ext_stats": {"target": 1200}}),
        Column("Item-Count", Integer, info={"ext_stats": {"target": 800}}),
        Column("Price (USD)", Integer, info={"ext_stats": {"target": 500}}),
    )

    runner = AlembicRunner(engine, metadata, schema=schema_name)
    try:
        # 1. Autogenerate & upgrade initial migration
        script1 = runner.autogenerate("create_order_details_quoted")
        assert (
            "alter_column_statistics_target('custom-schema', 'Order Details', 'user', '1200')"
            in script1
        )
        assert (
            "alter_column_statistics_target('custom-schema', 'Order Details', 'Item-Count', '800')"
            in script1
        )
        assert (
            "alter_column_statistics_target('custom-schema', 'Order Details', 'Price (USD)', '500')"
            in script1
        )

        runner.upgrade("head")

        with engine.connect() as conn:
            assert (
                get_pg_column_stat_target(conn, schema_name, "Order Details", "user")
                == 1200
            )
            assert (
                get_pg_column_stat_target(
                    conn, schema_name, "Order Details", "Item-Count"
                )
                == 800
            )
            assert (
                get_pg_column_stat_target(
                    conn, schema_name, "Order Details", "Price (USD)"
                )
                == 500
            )

        # 2. Update target on mixed-case/special-char columns
        metadata2 = MetaData(schema=schema_name)
        Table(
            "Order Details",
            metadata2,
            Column("id", Integer, primary_key=True),
            Column("user", Integer, info={"ext_stats": {"target": 600}}),
            Column("Item-Count", Integer),  # Reset to default
            Column("Price (USD)", Integer, info={"ext_stats": {"target": 1500}}),
        )
        runner.set_metadata(metadata2)
        script2 = runner.autogenerate("update_order_details_targets")
        assert (
            "alter_column_statistics_target('custom-schema', 'Order Details', 'user', '600', 1200)"
            in script2
        )
        assert (
            "alter_column_statistics_target('custom-schema', 'Order Details', 'Item-Count', 'default', 800)"
            in script2
        )
        assert (
            "alter_column_statistics_target('custom-schema', 'Order Details', 'Price (USD)', '1500', 500)"
            in script2
        )

        runner.upgrade("head")

        with engine.connect() as conn:
            assert (
                get_pg_column_stat_target(conn, schema_name, "Order Details", "user")
                == 600
            )
            target_default = get_pg_column_stat_target(
                conn, schema_name, "Order Details", "Item-Count"
            )
            assert target_default is None or target_default == -1
            assert (
                get_pg_column_stat_target(
                    conn, schema_name, "Order Details", "Price (USD)"
                )
                == 1500
            )

        # 3. Revert via downgrade
        runner.downgrade("-1")

        with engine.connect() as conn:
            assert (
                get_pg_column_stat_target(conn, schema_name, "Order Details", "user")
                == 1200
            )
            assert (
                get_pg_column_stat_target(
                    conn, schema_name, "Order Details", "Item-Count"
                )
                == 800
            )
            assert (
                get_pg_column_stat_target(
                    conn, schema_name, "Order Details", "Price (USD)"
                )
                == 500
            )

    finally:
        runner.cleanup()


@pytest.mark.usefixtures("clean_db")
def test_extended_statistics_quoted_identifiers(engine: Engine):
    """
    Test extended statistics on tables/columns/schemas with quotes, reserved words,
    mixed case, and special characters.
    """
    schema_name = "MixedCaseSchema"
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}";'))
        conn.execute(text(f'GRANT ALL ON SCHEMA "{schema_name}" TO PUBLIC;'))
        conn.execute(text(f'GRANT ALL ON SCHEMA "{schema_name}" TO CURRENT_USER;'))

    metadata = MetaData(schema=schema_name)
    Table(
        "User Events",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("user", Integer),
        Column("Event Type", String(50)),
        Column("from-location", String(50)),
        ExtendedStatistics(
            "Stats on User & Event", [NDISTINCT, MCV], "user", "Event Type"
        ),
        ExtendedStatistics(None, [DEPENDENCIES], "Event Type", "from-location"),
    )

    runner = AlembicRunner(engine, metadata, schema=schema_name)
    try:
        # 1. Autogenerate & upgrade
        script1 = runner.autogenerate("create_user_events_with_stats")
        assert (
            "create_statistics('MixedCaseSchema', 'User Events', 'Stats on User & Event'"
            in script1
        )

        runner.upgrade("head")

        with engine.connect() as conn:
            stats = get_pg_extended_stats(conn, schema_name, "User Events")
            assert "Stats on User & Event" in stats
            assert stats["Stats on User & Event"]["kinds"] == {"NDISTINCT", "MCV"}
            assert stats["Stats on User & Event"]["columns"] == ["user", "Event Type"]

            # Check auto-generated default name
            default_stat_name = (
                f"{schema_name}_User Events_Event Type_from-location_stats"
            )
            assert default_stat_name in stats
            assert stats[default_stat_name]["kinds"] == {"DEPENDENCIES"}
            assert stats[default_stat_name]["columns"] == [
                "Event Type",
                "from-location",
            ]

        # 2. Modify extended statistics
        metadata2 = MetaData(schema=schema_name)
        Table(
            "User Events",
            metadata2,
            Column("id", Integer, primary_key=True),
            Column("user", Integer),
            Column("Event Type", String(50)),
            Column("from-location", String(50)),
            # Change kinds on first stat
            ExtendedStatistics(
                "Stats on User & Event", [NDISTINCT], "user", "Event Type"
            ),
        )
        runner.set_metadata(metadata2)
        script2 = runner.autogenerate("modify_user_events_stats")
        assert "drop_statistics" in script2
        runner.upgrade("head")

        with engine.connect() as conn:
            stats = get_pg_extended_stats(conn, schema_name, "User Events")
            assert default_stat_name not in stats
            assert "Stats on User & Event" in stats
            assert stats["Stats on User & Event"]["kinds"] == {"NDISTINCT"}

        # 3. Downgrade should restore the dropped statistic
        runner.downgrade("-1")

        with engine.connect() as conn:
            stats = get_pg_extended_stats(conn, schema_name, "User Events")
            assert "Stats on User & Event" in stats
            assert stats["Stats on User & Event"]["kinds"] == {"NDISTINCT", "MCV"}
            assert default_stat_name in stats

    finally:
        runner.cleanup()


@pytest.mark.usefixtures("clean_db")
def test_reserved_keywords_as_identifiers(engine: Engine):
    """
    Test tables and columns that are SQL reserved keywords (select, where, group, order, table).
    """
    metadata = MetaData()
    Table(
        "select",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("where", Integer, info={"ext_stats": {"target": 1100}}),
        Column("group", String(50)),
        Column("order", String(50)),
        ExtendedStatistics(
            "select_group_order_stats", [NDISTINCT, MCV], "group", "order"
        ),
    )

    runner = AlembicRunner(engine, metadata)
    try:
        script = runner.autogenerate("create_reserved_table")
        assert (
            "alter_column_statistics_target('public', 'select', 'where', '1100')"
            in script
        )
        assert (
            "create_statistics('public', 'select', 'select_group_order_stats'" in script
        )

        runner.upgrade("head")

        with engine.connect() as conn:
            target = get_pg_column_stat_target(conn, "public", "select", "where")
            assert target == 1100

            stats = get_pg_extended_stats(conn, "public", "select")
            assert "select_group_order_stats" in stats
            assert stats["select_group_order_stats"]["kinds"] == {"NDISTINCT", "MCV"}
            assert stats["select_group_order_stats"]["columns"] == ["group", "order"]

        # Verify downgrade drops stats and table cleanly
        runner.downgrade("-1")

        with engine.connect() as conn:
            target = get_pg_column_stat_target(conn, "public", "select", "where")
            assert target is None

    finally:
        runner.cleanup()
