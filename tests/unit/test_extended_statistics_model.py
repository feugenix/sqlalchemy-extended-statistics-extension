import pytest
from sqlalchemy import Table, Column, Integer, String, MetaData
from ext_stat_plugin.extended_statistic.sqlalchemy import (
    ExtendedStatistics,
    NDISTINCT,
    MCV,
    DEPENDENCIES,
    _get_default_statistics_name,
)


def test_default_statistics_name():
    name = _get_default_statistics_name("public", "my_table", "col1", "col2")
    assert name == "public_my_table_col1_col2_stats"

    name_none_schema = _get_default_statistics_name(None, "my_table", "col1")
    assert name_none_schema == "public_my_table_col1_stats"

    name_special = _get_default_statistics_name("My-Schema", "Order Details", "user", "Item-Count")
    assert name_special == "My-Schema_Order Details_user_Item-Count_stats"

    name_expr = _get_default_statistics_name("public", "metrics", "(lower(name))", "(val1 + val2)")
    assert name_expr == "public_metrics_(lower(name))_(val1 + val2)_stats"


def test_extended_statistics_with_expressions():
    metadata = MetaData()
    table = Table(
        "expr_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(50)),
        Column("val1", Integer),
        Column("val2", Integer),
    )
    stat = ExtendedStatistics(
        None,
        [NDISTINCT, MCV],
        "(lower(name))",
        table.c.val1 + table.c.val2,
    )
    table.append_column(stat)

    ext_stats = getattr(table, "__ext_stats__")
    assert len(ext_stats) == 1
    assert ext_stats[0].name == "public_expr_table_(lower(name))_expr_stats"
    assert ext_stats[0].kind == {NDISTINCT, MCV}
    assert ext_stats[0].table is table


def test_extended_statistics_attachment():
    metadata = MetaData()
    stat1 = ExtendedStatistics(
        "custom_stat_name",
        [NDISTINCT, MCV],
        "name",
        "description",
    )
    stat2 = ExtendedStatistics(
        None,  # auto-generated name
        [DEPENDENCIES],
        "id",
        "name",
    )

    table = Table(
        "sample_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(50)),
        Column("description", String(100)),
        stat1,
        stat2,
    )

    # Check that statistics were attached to table.__ext_stats__
    assert hasattr(table, "__ext_stats__")
    ext_stats = getattr(table, "__ext_stats__")
    assert len(ext_stats) == 2

    assert ext_stats[0].name == "custom_stat_name"
    assert ext_stats[0].kind == {NDISTINCT, MCV}
    assert ext_stats[0].expressions == ("name", "description")
    assert ext_stats[0].table is table

    assert ext_stats[1].name == "public_sample_table_id_name_stats"
    assert ext_stats[1].kind == {DEPENDENCIES}
    assert ext_stats[1].expressions == ("id", "name")
    assert ext_stats[1].table is table


def test_extended_statistics_default_kind():
    metadata = MetaData()
    stat = ExtendedStatistics("test_stat", None, "col1", "col2")
    Table(
        "table_default_kind",
        metadata,
        Column("col1", Integer),
        Column("col2", Integer),
        stat,
    )
    assert stat.kind == {"NDISTINCT"}
