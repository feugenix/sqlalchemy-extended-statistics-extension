from typing import Any, Sequence
from alembic.operations import Operations, MigrateOperation
from alembic.autogenerate.api import AutogenContext
from alembic.autogenerate import renderers
from sqlalchemy import ColumnElement, Column
from logging import getLogger

from .sqlalchemy import StatisticsKind
from ..utils import coerce_to_quoted, get_alembic_autogenerate_prefix

logger = getLogger("alembic.plugins.ext_stats_plugin.extended_statistics.operations")


def _format_expression(expr: str | ColumnElement[Any]) -> str:
    if isinstance(expr, Column):
        return coerce_to_quoted(expr.name)
    expr_str = str(expr).strip()
    if "," in expr_str:
        return expr_str
    if expr_str.startswith("(") and expr_str.endswith(")"):
        return expr_str
    if "(" in expr_str or any(op in expr_str for op in [" + ", " - ", " * ", " / ", " || ", "::"]):
        return f"({expr_str})"
    return coerce_to_quoted(expr_str)

@Operations.register_operation("create_statistics")
class CreateStatisticsOp(MigrateOperation):
    def __init__(self, schema_name: str | None, table_name: str, statistics_name: str | None, kind: set[StatisticsKind], *expressions: str | ColumnElement[Any]) -> None:
        self.schema_name = schema_name or "public"
        self.table_name = table_name
        self.name = statistics_name
        self.kind = kind
        self.expressions = expressions

    @classmethod
    def create_statistics(cls, operations: Operations, schema_name: str | None, table_name: str, statistics_name: str | None, kind: list[StatisticsKind], expressions: list[str | ColumnElement[Any]]) -> Any:
        kind_dedup = set(kind)
        op = cls(schema_name, table_name, statistics_name, kind_dedup, *expressions)
        return operations.invoke(op)

    def reverse(self) -> 'DropStatisticsOp':
        if self.name is None:
            raise ValueError("Cannot reverse CreateStatisticsOp when statistics name is None.")

        return DropStatisticsOp(schema_name=self.schema_name, statistics_name=self.name)


@Operations.register_operation("drop_statistics")
class DropStatisticsOp(MigrateOperation):
    def __init__(
        self,
        schema_name: str | None,
        statistics_name: str,
        table_name: str | None = None,
        kind: set[StatisticsKind] | None = None,
        expressions: Sequence[str | ColumnElement[Any]] | None = None,
    ) -> None:
        self.schema_name = schema_name or "public"
        self.name = statistics_name
        self.table_name = table_name
        self.kind = kind or set()
        self.expressions = tuple(expressions) if expressions is not None else ()

    @classmethod
    def drop_statistics(
        cls,
        operations: Operations,
        schema_name: str | None,
        statistics_name: str,
        table_name: str | None = None,
        kind: list[StatisticsKind] | None = None,
        expressions: list[str | ColumnElement[Any]] | None = None,
    ) -> Any:
        kind_set = set(kind) if kind is not None else None
        op = cls(schema_name, statistics_name, table_name, kind_set, expressions)
        return operations.invoke(op)

    def reverse(self) -> 'CreateStatisticsOp':
        if not self.table_name or not self.kind or not self.expressions:
            raise NotImplementedError(
                "Reverse operation for DropStatisticsOp requires table_name, kind, and expressions."
            )
        return CreateStatisticsOp(
            self.schema_name,
            self.table_name,
            self.name,
            self.kind,
            *self.expressions,
        )

def _get_expressions_string(expressions: Sequence[str | ColumnElement[Any]]) -> str:
    return ", ".join(f"'{str(expr)}'" for expr in expressions)


@renderers.dispatch_for(CreateStatisticsOp)
def _create_statistics(autogen_context: AutogenContext, op: CreateStatisticsOp) -> str:
    tmpl = (
        "%(prefix)screate_statistics(%(schema_name)r, %(table_name)r, %(name)r, [%(kind)s], [%(expressions)s])"
    )

    statistic_kinds_str = ", ".join({repr(k).upper() for k in op.kind})

    return tmpl % {
        "prefix": get_alembic_autogenerate_prefix(autogen_context),
        "schema_name": str(op.schema_name),
        "table_name": str(op.table_name),
        "name": str(op.name),
        "kind": statistic_kinds_str,
        "expressions": _get_expressions_string(op.expressions),
    }

@renderers.dispatch_for(DropStatisticsOp)
def _drop_statistics(autogen_context: AutogenContext, op: DropStatisticsOp) -> str:
    tmpl = (
        "%(prefix)sdrop_statistics(%(schema_name)r, %(name)r)"
    )

    return tmpl % {
        "prefix": get_alembic_autogenerate_prefix(autogen_context),
        "schema_name": str(op.schema_name),
        "name": str(op.name),
    }

@Operations.implementation_for(CreateStatisticsOp)
def create_statistics_impl(operations: Operations, operation: CreateStatisticsOp) -> None:
    if not operation.name:
        raise ValueError("Statistics name must be provided for CreateStatisticsOp.")

    logger.info(f"Executing CreateStatisticsOp: schema_name={operation.schema_name} table_name={operation.table_name}, name={operation.name}, kind={operation.kind}, expressions={operation.expressions}")

    expressions_str = ", ".join(_format_expression(expr) for expr in operation.expressions)
    quoted_schema_name = coerce_to_quoted(operation.schema_name)
    quoted_table_name = coerce_to_quoted(operation.table_name)
    quoted_statistics_name = coerce_to_quoted(operation.name)
    statistic_kinds_str = ", ".join({k.lower() for k in operation.kind})
    operations.execute(
        f"CREATE STATISTICS {quoted_schema_name}.{quoted_statistics_name} ({statistic_kinds_str}) ON {expressions_str} FROM {quoted_schema_name}.{quoted_table_name}"
    )

@Operations.implementation_for(DropStatisticsOp)
def drop_statistics_impl(operations: Operations, operation: DropStatisticsOp) -> None:
    if not operation.name:
        raise ValueError("Statistics name must be provided for DropStatisticsOp.")

    logger.info(f"Executing DropStatisticsOp: schema_name={operation.schema_name} name={operation.name}")

    quoted_schema_name = coerce_to_quoted(operation.schema_name)
    quoted_statistics_name = coerce_to_quoted(operation.name)
    operations.execute(
        f"DROP STATISTICS {quoted_schema_name}.{quoted_statistics_name}"
    )
