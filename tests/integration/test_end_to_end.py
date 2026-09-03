import pytest
from sqlalchemy import (
    Column,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
)
from sqlalchemy.engine import Engine

from sqlalchemy_extended_statistics_extension.extended_statistic.sqlalchemy import (
    MCV,
    NDISTINCT,
    ExtendedStatistics,
)
from tests.alembic_helpers import AlembicRunner
from tests.utils import get_pg_column_stat_target, get_pg_extended_stats


@pytest.mark.usefixtures("clean_db")
def test_end_to_end_repo_example(engine: Engine):
    """
    Test simulating the exact structure and models from old_tests/ext_stat_plugin_test/repo.py.
    Verifies both public and test_schema models with column stats target and extended stats.
    """
    public_metadata = MetaData()
    test_metadata = MetaData(schema="test_schema")

    # Model 1: SomeClass in public schema
    Table(
        "some_table",
        public_metadata,
        Column("id", Integer, info={"ext_stats": {"target": 1000}}),
        Column("name", String(50)),
        Column("clear_col", String(50), info={"ext_stats": {"target": 1051}}),
        Index("ix_some_table_name_clear_col", "name", "clear_col"),
        PrimaryKeyConstraint("id", "name", name="mytable_pk"),
        ExtendedStatistics(
            "some_table_name_clear_col_stats",
            [NDISTINCT],
            "name",
            "clear_col",
        ),
        ExtendedStatistics(
            "some_table_id_name_stats",
            [MCV],
            "id",
            "name",
        ),
    )

    # 1. Run migrations for public schema
    runner_public = AlembicRunner(engine, public_metadata)
    try:
        script1 = runner_public.autogenerate("create_some_table")
        assert (
            "alter_column_statistics_target('public', 'some_table', 'id', '1000')"
            in script1
        )
        assert (
            "alter_column_statistics_target('public', 'some_table', 'clear_col', '1051')"
            in script1
        )
        assert (
            "create_statistics('public', 'some_table', 'some_table_name_clear_col_stats'"
            in script1
        )
        assert (
            "create_statistics('public', 'some_table', 'some_table_id_name_stats'"
            in script1
        )

        runner_public.upgrade("head")

        with engine.connect() as conn:
            # Check column targets
            assert get_pg_column_stat_target(conn, "public", "some_table", "id") == 1000
            assert (
                get_pg_column_stat_target(conn, "public", "some_table", "clear_col")
                == 1051
            )

            # Check extended statistics
            stats = get_pg_extended_stats(conn, "public", "some_table")
            assert "some_table_name_clear_col_stats" in stats
            assert stats["some_table_name_clear_col_stats"]["kinds"] == {"NDISTINCT"}
            assert stats["some_table_name_clear_col_stats"]["columns"] == [
                "name",
                "clear_col",
            ]

            assert "some_table_id_name_stats" in stats
            assert stats["some_table_id_name_stats"]["kinds"] == {"MCV"}
            assert stats["some_table_id_name_stats"]["columns"] == ["id", "name"]
    finally:
        runner_public.cleanup()

    # Model 2: SomeClassTest in test_schema
    Table(
        "some_table_test",
        test_metadata,
        Column("id", Integer, primary_key=True, info={"ext_stats": {"target": 1000}}),
        Column("name", String(50)),
        Column("description", String(50)),
        ExtendedStatistics(
            "some_table_test_name_description_stats",
            [NDISTINCT],
            "name",
            "description",
        ),
        ExtendedStatistics(
            "some_table_test_id_name_description_stats",
            [MCV],
            "id",
            "name",
            "description",
        ),
    )

    # 2. Run migrations for test_schema
    runner_test = AlembicRunner(engine, test_metadata, schema="test_schema")
    try:
        script2 = runner_test.autogenerate("create_some_table_test")
        assert (
            "alter_column_statistics_target('test_schema', 'some_table_test', 'id', '1000')"
            in script2
        )
        assert (
            "create_statistics('test_schema', 'some_table_test', 'some_table_test_name_description_stats'"
            in script2
        )
        assert (
            "create_statistics('test_schema', 'some_table_test', 'some_table_test_id_name_description_stats'"
            in script2
        )

        runner_test.upgrade("head")

        with engine.connect() as conn:
            # Check column target
            assert (
                get_pg_column_stat_target(conn, "test_schema", "some_table_test", "id")
                == 1000
            )

            # Check extended statistics
            stats = get_pg_extended_stats(conn, "test_schema", "some_table_test")
            assert "some_table_test_name_description_stats" in stats
            assert stats["some_table_test_name_description_stats"]["kinds"] == {
                "NDISTINCT"
            }
            assert stats["some_table_test_name_description_stats"]["columns"] == [
                "name",
                "description",
            ]

            assert "some_table_test_id_name_description_stats" in stats
            assert stats["some_table_test_id_name_description_stats"]["kinds"] == {
                "MCV"
            }
            assert stats["some_table_test_id_name_description_stats"]["columns"] == [
                "id",
                "name",
                "description",
            ]
    finally:
        runner_test.cleanup()
