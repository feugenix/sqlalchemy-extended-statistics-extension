import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, func
from sqlalchemy.engine import Engine

from ext_stat_plugin.extended_statistic.sqlalchemy import (
    MCV,
    NDISTINCT,
    ExtendedStatistics,
)
from tests.alembic_helpers import AlembicRunner
from tests.utils import get_pg_extended_stats


@pytest.mark.usefixtures("clean_db")
def test_extended_statistics_on_raw_sql_expressions(engine: Engine):
    """
    Test extended statistics created using raw SQL expression strings like
    '(lower(name))' and '(a + b)'.
    """
    metadata = MetaData()
    Table(
        "users",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(50)),
        Column("a", Integer),
        Column("b", Integer),
        ExtendedStatistics(
            "users_lower_name_a_b_stats",
            [NDISTINCT, MCV],
            "(lower(name))",
            "(a + b)",
        ),
    )

    runner = AlembicRunner(engine, metadata)
    try:
        # 1. Autogenerate & upgrade
        script1 = runner.autogenerate("create_users_with_expr_stats")
        assert (
            "create_statistics('public', 'users', 'users_lower_name_a_b_stats'"
            in script1
        )
        assert "'(lower(name))'" in script1
        assert "'(a + b)'" in script1

        runner.upgrade("head")

        with engine.connect() as conn:
            stats = get_pg_extended_stats(conn, "public", "users")
            assert "users_lower_name_a_b_stats" in stats
            stat = stats["users_lower_name_a_b_stats"]
            assert "NDISTINCT" in stat["kinds"]
            assert "MCV" in stat["kinds"]
            assert "EXPRESSIONS" in stat["kinds"]
            assert "lower(" in stat["def_columns"] and "name" in stat["def_columns"]
            assert "(a + b)" in stat["def_columns"]

        # 2. Modify: change statistic kinds or drop
        metadata2 = MetaData()
        Table(
            "users",
            metadata2,
            Column("id", Integer, primary_key=True),
            Column("name", String(50)),
            Column("a", Integer),
            Column("b", Integer),
            ExtendedStatistics(
                "users_lower_name_a_b_stats",
                [NDISTINCT],
                "(lower(name))",
                "(a + b)",
            ),
        )
        runner.set_metadata(metadata2)
        script2 = runner.autogenerate("update_users_expr_stats")
        assert "drop_statistics" in script2
        assert (
            "create_statistics('public', 'users', 'users_lower_name_a_b_stats'"
            in script2
        )

        runner.upgrade("head")

        with engine.connect() as conn:
            stats = get_pg_extended_stats(conn, "public", "users")
            assert "users_lower_name_a_b_stats" in stats
            stat = stats["users_lower_name_a_b_stats"]
            assert stat["kinds"] == {"NDISTINCT", "EXPRESSIONS"}

        # 3. Downgrade step 2 -> should restore original kinds
        runner.downgrade("-1")

        with engine.connect() as conn:
            stats = get_pg_extended_stats(conn, "public", "users")
            assert "users_lower_name_a_b_stats" in stats
            stat = stats["users_lower_name_a_b_stats"]
            assert "NDISTINCT" in stat["kinds"]
            assert "MCV" in stat["kinds"]

    finally:
        runner.cleanup()


@pytest.mark.usefixtures("clean_db")
def test_extended_statistics_mixed_column_and_expression(engine: Engine):
    """
    Test extended statistics combining regular column names and expressions.
    """
    metadata = MetaData()
    Table(
        "products",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("code", String(20)),
        Column("title", String(100)),
        ExtendedStatistics(
            "products_code_lower_title_stats",
            [NDISTINCT, MCV],
            "code",
            "lower(title)",
        ),
    )

    runner = AlembicRunner(engine, metadata)
    try:
        script = runner.autogenerate("create_products_mixed_stats")
        assert (
            "create_statistics('public', 'products', 'products_code_lower_title_stats'"
            in script
        )
        assert "'code'" in script
        assert "'lower(title)'" in script

        runner.upgrade("head")

        with engine.connect() as conn:
            stats = get_pg_extended_stats(conn, "public", "products")
            assert "products_code_lower_title_stats" in stats
            stat = stats["products_code_lower_title_stats"]
            assert "NDISTINCT" in stat["kinds"]
            assert "MCV" in stat["kinds"]
            assert "code" in stat["columns"]
            assert any(
                "lower" in expr and "title" in expr for expr in stat["expressions"]
            )

        # Downgrade drops table and stats cleanly
        runner.downgrade("-1")

        with engine.connect() as conn:
            stats = get_pg_extended_stats(conn, "public", "products")
            assert "products_code_lower_title_stats" not in stats

    finally:
        runner.cleanup()


@pytest.mark.usefixtures("clean_db")
def test_extended_statistics_sqlalchemy_column_elements(engine: Engine):
    """
    Test extended statistics defined with SQLAlchemy ColumnElement objects (func, binary ops).
    """
    metadata = MetaData(schema="test_schema")
    table = Table(
        "metrics",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("tag", String(50)),
        Column("val1", Integer),
        Column("val2", Integer),
    )
    # Add ExtendedStatistics with SQLAlchemy expression objects
    stat = ExtendedStatistics(
        "metrics_expr_stat",
        [NDISTINCT, MCV],
        func.lower(table.c.tag),
        table.c.val1 + table.c.val2,
    )
    stat._set_parent(table)

    runner = AlembicRunner(engine, metadata, schema="test_schema")
    try:
        script = runner.autogenerate("create_metrics_with_expr_objs")
        assert (
            "create_statistics('test_schema', 'metrics', 'metrics_expr_stat'" in script
        )

        runner.upgrade("head")

        with engine.connect() as conn:
            stats = get_pg_extended_stats(conn, "test_schema", "metrics")
            assert "metrics_expr_stat" in stats
            pg_stat = stats["metrics_expr_stat"]
            assert "NDISTINCT" in pg_stat["kinds"]
            assert "MCV" in pg_stat["kinds"]
            assert (
                "lower(" in pg_stat["def_columns"] and "tag" in pg_stat["def_columns"]
            )
            assert "(val1 + val2)" in pg_stat["def_columns"]

    finally:
        runner.cleanup()
