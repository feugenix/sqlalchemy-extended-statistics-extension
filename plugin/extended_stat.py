from typing import Any, Literal, Sequence
from alembic.operations import Operations, MigrateOperation
from alembic.autogenerate.api import AutogenContext
from alembic.autogenerate import renderers
from alembic.util import PriorityDispatchResult
from sqlalchemy import Table, text, ColumnElement, quoted_name
from logging import getLogger
from sqlalchemy.schema import SchemaItem
from sqlalchemy.sql.base import SchemaEventTarget
from .utils import _alembic_autogenerate_prefix
from alembic.operations.ops import UpgradeOps

logger = getLogger("alembic.plugins.ext_stats_plugin.extended_statistics")

NDISTINCT = "NDISTINCT"
DEPENDENCIES = "DEPENDENCIES"
MCV = "MCV"

type StatisticsKind = Literal["NDISTINCT", "DEPENDENCIES", "MCV"]

def _get_expression_name(expression: str | ColumnElement[Any]) -> str:
    if isinstance(expression, str):
        return expression

    return "expr"

def _get_default_statistics_name(schema_name: str | None, table_name: str, *expressions: str | ColumnElement[Any]) -> str:
    expressions_names = "_".join(_get_expression_name(expr) for expr in expressions)
    return f"{schema_name or 'public'}_{table_name}_{expressions_names}_stats"

class ExtendedStatistics(SchemaItem):
    table: Table
    kind: StatisticsKind

    def __init__(
            self,
            statistics_name: str | None,
            kind: StatisticsKind = "NDISTINCT",
            *expressions: str | ColumnElement[Any],
    ) -> None:
        self.name = statistics_name
        self.kind = kind
        self.expressions = expressions

        logger.info(f"Creating ExtendedStatistics: name={statistics_name}, kind={kind}, expressions={expressions}")

    def _set_parent(self, parent: SchemaEventTarget, **kw: Any):
        table = parent
        assert isinstance(table, Table)
        self.table = table

        existing_stats = getattr(table, "__ext_stats__", None)
        if existing_stats is None:
            existing_stats = []
        existing_stats.append(self)
        setattr(table, "__ext_stats__", existing_stats)

        if self.name is None:
            self.name = _get_default_statistics_name(table.schema, table.name, *self.expressions)
        logger.info(f"ExtendedStatistics added to table '{table.name}'")


@Operations.register_operation("create_statistics")
class CreateStatisticsOp(MigrateOperation):
    def __init__(self, schema_name: str | None, table_name: str, statistics_name: str | None, kind: StatisticsKind, *expressions: str | ColumnElement[Any]) -> None:
        self.schema_name = schema_name or "public"
        self.table_name = table_name
        self.name = statistics_name
        self.kind = kind
        self.expressions = expressions

    @classmethod
    def create_statistics(cls, operations: Operations, schema_name: str | None, table_name: str, statistics_name: str | None, kind: StatisticsKind, expressions: list[str | ColumnElement[Any]]) -> Any:
        op = cls(schema_name, table_name, statistics_name, kind, *expressions)
        return operations.invoke(op)

    def reverse(self) -> 'DropStatisticsOp':
        if self.name is None:
            raise ValueError("Cannot reverse CreateStatisticsOp when statistics name is None.")

        return DropStatisticsOp(schema_name=self.schema_name, statistics_name=self.name)


@Operations.register_operation("drop_statistics")
class DropStatisticsOp(MigrateOperation):
    def __init__(self, schema_name: str | None, statistics_name: str) -> None:
        self.schema_name = schema_name or "public"
        self.name = statistics_name

    @classmethod
    def drop_statistics(cls, operations: Operations, schema_name: str | None, statistics_name: str) -> Any:
        op = cls(schema_name, statistics_name)
        return operations.invoke(op)

    def reverse(self) -> 'DropStatisticsOp':
        raise NotImplementedError("Reverse operation for DropStatisticsOp is not implemented.")

def _get_expressions_string(expressions: Sequence[str | ColumnElement[Any]]) -> str:
    exp_body = ", ".join(f"'{str(expr)}'" for expr in expressions)
    return f"[{exp_body}]"


@renderers.dispatch_for(CreateStatisticsOp)
def _create_statistics(autogen_context: AutogenContext, op: CreateStatisticsOp) -> str:
    tmpl = (
        "%(prefix)screate_statistics(%(schema_name)r, %(table_name)r, %(name)r, %(kind)s, %(expressions)s)"
    )

    return tmpl % {
        "prefix": _alembic_autogenerate_prefix(autogen_context),
        "schema_name": str(op.schema_name),
        "table_name": str(op.table_name),
        "name": str(op.name),
        "kind": f"'{str(op.kind).upper()}'",
        "expressions": _get_expressions_string(op.expressions),
    }

@renderers.dispatch_for(DropStatisticsOp)
def _drop_statistics(autogen_context: AutogenContext, op: DropStatisticsOp) -> str:
    tmpl = (
        "%(prefix)sdrop_statistics(%(schema_name)r, %(name)r)"
    )

    return tmpl % {
        "prefix": _alembic_autogenerate_prefix(autogen_context),
        "schema_name": str(op.schema_name),
        "name": str(op.name),
    }

@Operations.implementation_for(CreateStatisticsOp)
def create_statistics_impl(operations: Operations, operation: CreateStatisticsOp) -> None:
    logger.info(f"Executing CreateStatisticsOp: schema_name={operation.schema_name} table_name={operation.table_name}, name={operation.name}, kind={operation.kind}, expressions={operation.expressions}")

    expressions_str = ", ".join(str(expr) for expr in operation.expressions)
    operations.execute(
        f"CREATE STATISTICS {operation.schema_name}.{operation.name} ({operation.kind}) ON {expressions_str} FROM {operation.schema_name}.{operation.table_name}"
    )

@Operations.implementation_for(DropStatisticsOp)
def drop_statistics_impl(operations: Operations, operation: DropStatisticsOp) -> None:
    logger.info(f"Executing DropStatisticsOp: schema_name={operation.schema_name} name={operation.name}")

    operations.execute(
        f"DROP STATISTICS {operation.schema_name}.{operation.name}"
    )

def _load_existing_table_statistics(conn, table_name: str) -> set[str]:
    try:
        table_metadata = conn.execute(
            text(
                """
                SELECT s.stxname AS statistics_name FROM pg_statistic_ext s WHERE s.stxrelid = :table_name::regclass
                """
            ),
            {"table_name": table_name},
        ).fetchall()
    except Exception as e:
        logger.warning(f"Error loading existing statistics for table '{table_name}': {e}")
        return set()

    return {row.statistics_name for row in table_metadata}

def _get_table_ext_stats(metadata_table: Table[Any]) -> list[ExtendedStatistics]:
    return getattr(metadata_table, "__ext_stats__", [])

def _clear_ext_stat_info(metadata_table: Table[Any]) -> None:
    try:
        delattr(metadata_table, "__ext_stats__")
    except:
        pass

def compare_tables_extended_statistics(
    autogen_context: AutogenContext,
    upgrade_ops: UpgradeOps,
    schema: str | None,
    tname: quoted_name | str,
    conn_table: Table[Any] | None,
    metadata_table: Table[Any],
) -> PriorityDispatchResult:
    logger.debug(f"Comparing tables '{tname}'")

    schema = schema or "public"

    statistics_from_db = _load_existing_table_statistics(autogen_context.connection, str(f"{schema}.{tname}"))
    statistics_from_metadata: list[ExtendedStatistics] = [stat for stat in _get_table_ext_stats(metadata_table)]

    if not statistics_from_metadata and not statistics_from_db:
        logger.info("No extended statistics found. Skipping it.")
        return PriorityDispatchResult.CONTINUE

    for stat_name in statistics_from_db:
        logger.debug(f"Statistics '{stat_name}' exists in database. Dropping it.")
        upgrade_ops.ops.append(DropStatisticsOp(schema_name=schema, statistics_name=stat_name))

    for stat in statistics_from_metadata:
        logger.debug(f"Statistics '{stat.name}' defined in metadata. Creating it.")
        upgrade_ops.ops.append(
            CreateStatisticsOp(
                schema,
                str(tname),
                stat.name,
                stat.kind,
                *stat.expressions,
            )
        )

    _clear_ext_stat_info(metadata_table)

    return PriorityDispatchResult.CONTINUE
