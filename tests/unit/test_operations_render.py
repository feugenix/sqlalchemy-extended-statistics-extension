import pytest
from unittest.mock import MagicMock
from ext_stat_plugin.column_statistics_target.operations import (
    AlterColumnStatisticsTargetOp,
    _alter_statistics_target,
)
from ext_stat_plugin.extended_statistic.operations import (
    CreateStatisticsOp,
    DropStatisticsOp,
    _create_statistics,
    _drop_statistics,
)
from ext_stat_plugin.extended_statistic.sqlalchemy import NDISTINCT, MCV, DEPENDENCIES


def _make_mock_autogen_context():
    ctx = MagicMock()
    ctx.opts = {"alembic_module_prefix": "op."}
    return ctx


def test_alter_column_statistics_target_op_validation():
    # Valid targets
    op = AlterColumnStatisticsTargetOp("public", "users", "age", 500, "default")
    assert op.new_target == 500
    assert op.prev_target == "default"

    op_default = AlterColumnStatisticsTargetOp("public", "users", "age", "default", 500)
    assert op_default.new_target == "default"
    assert op_default.prev_target == 500

    # Invalid targets
    with pytest.raises(ValueError, match="Invalid new_target"):
        AlterColumnStatisticsTargetOp("public", "users", "age", 15000)

    with pytest.raises(ValueError, match="Invalid new_target"):
        AlterColumnStatisticsTargetOp("public", "users", "age", -10)

    with pytest.raises(ValueError, match="Invalid prev_target"):
        AlterColumnStatisticsTargetOp("public", "users", "age", 100, "invalid_prev")


def test_alter_column_statistics_target_op_reverse():
    op = AlterColumnStatisticsTargetOp("public", "users", "age", 500, 200)
    rev = op.reverse()
    assert rev.new_target == 200
    assert rev.schema_name == "public"
    assert rev.table_name == "users"
    assert rev.column_name == "age"


def test_alter_column_statistics_target_rendering():
    ctx = _make_mock_autogen_context()

    op_with_prev = AlterColumnStatisticsTargetOp("public", "users", "age", 500, 200)
    rendered = _alter_statistics_target(ctx, op_with_prev)
    assert rendered == "op.alter_column_statistics_target('public', 'users', 'age', 500, 200)"

    op_default_prev = AlterColumnStatisticsTargetOp("public", "users", "age", 500, "default")
    rendered_default = _alter_statistics_target(ctx, op_default_prev)
    assert rendered_default == "op.alter_column_statistics_target('public', 'users', 'age', 500)"


def test_create_and_drop_statistics_op_reverse():
    create_op = CreateStatisticsOp("public", "users", "users_stats", {NDISTINCT, MCV}, "col1", "col2")
    drop_op = create_op.reverse()
    assert isinstance(drop_op, DropStatisticsOp)
    assert drop_op.name == "users_stats"
    assert drop_op.schema_name == "public"

    with pytest.raises(NotImplementedError):
        drop_op.reverse()


def test_create_and_drop_statistics_rendering():
    ctx = _make_mock_autogen_context()

    create_op = CreateStatisticsOp("public", "users", "users_stats", {NDISTINCT}, "col1", "col2")
    rendered_create = _create_statistics(ctx, create_op)
    assert "op.create_statistics('public', 'users', 'users_stats'" in rendered_create
    assert "'NDISTINCT'" in rendered_create
    assert "'col1', 'col2'" in rendered_create

    drop_op = DropStatisticsOp("test_schema", "my_stat")
    rendered_drop = _drop_statistics(ctx, drop_op)
    assert rendered_drop == "op.drop_statistics('test_schema', 'my_stat')"


def test_operations_rendering_quoted_and_special_chars():
    ctx = _make_mock_autogen_context()

    # Special chars, reserved words, mixed casing in alter_column_statistics_target
    op_alter = AlterColumnStatisticsTargetOp(
        "Custom-Schema",
        "Order Table",
        "user select",
        1500,
        500,
    )
    rendered_alter = _alter_statistics_target(ctx, op_alter)
    assert rendered_alter == "op.alter_column_statistics_target('Custom-Schema', 'Order Table', 'user select', 1500, 500)"

    # Special chars, reserved words, mixed casing in create_statistics and drop_statistics
    op_create = CreateStatisticsOp(
        "Custom-Schema",
        "Order Table",
        "Stats (User & Type)",
        {NDISTINCT, DEPENDENCIES},
        "user select",
        "Price-USD",
    )
    rendered_create = _create_statistics(ctx, op_create)
    assert "op.create_statistics('Custom-Schema', 'Order Table', 'Stats (User & Type)'" in rendered_create
    assert "'user select'" in rendered_create
    assert "'Price-USD'" in rendered_create

    op_drop = DropStatisticsOp("Custom-Schema", "Stats (User & Type)", "Order Table", {NDISTINCT}, ["user select", "Price-USD"])
    rendered_drop = _drop_statistics(ctx, op_drop)
    assert rendered_drop == "op.drop_statistics('Custom-Schema', 'Stats (User & Type)')"

    reversed_create = op_drop.reverse()
    assert reversed_create.schema_name == "Custom-Schema"
    assert reversed_create.table_name == "Order Table"
    assert reversed_create.name == "Stats (User & Type)"
    assert reversed_create.expressions == ("user select", "Price-USD")


def test_create_statistics_rendering_with_expressions():
    ctx = _make_mock_autogen_context()

    op = CreateStatisticsOp(
        "public",
        "items",
        "items_expr_stats",
        {NDISTINCT, MCV},
        "(lower(name))",
        "(a + b)",
    )
    rendered = _create_statistics(ctx, op)
    assert "op.create_statistics('public', 'items', 'items_expr_stats'" in rendered
    assert "'(lower(name))'" in rendered
    assert "'(a + b)'" in rendered

    reversed_drop = op.reverse()
    assert reversed_drop.name == "items_expr_stats"
    assert reversed_drop.schema_name == "public"
