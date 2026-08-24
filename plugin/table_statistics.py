from typing import Any
from alembic.operations import Operations, MigrateOperation
from alembic.autogenerate.api import AutogenContext
from alembic.autogenerate import renderers
from alembic.operations.ops import UpgradeOps
from alembic.util import PriorityDispatchResult
from sqlalchemy import quoted_name, Column, Table, text
from logging import getLogger
from .utils import _alembic_autogenerate_prefix

logger = getLogger("alembic.plugins.ext_stats_plugin.column_statistics_target")

type TargetValue = int | str

@Operations.register_operation("alter_column_statistics_target")
class AlterColumnStatisticsTargetOp(MigrateOperation):
    def __init__(self, schema_name: str | None, table_name: str, column_name: str, new_target: TargetValue, prev_target: TargetValue | None = "default") -> None:
        self.schema_name = schema_name or "public"
        self.table_name = table_name
        self.column_name = column_name

        self.new_target = new_target
        self._assert_target_value(self.new_target, "new_target")

        self.prev_target = prev_target
        if self.prev_target is not None:
            self._assert_target_value(self.prev_target, "prev_target")

    def _assert_target_value(self, target: TargetValue, field_name: str) -> None:
        if target == "default":
            return

        try:
            target_value = int(target)
            if not 0 <= target_value <= 10000:
                raise ValueError()
        except ValueError:
            raise ValueError(
                f"Invalid {field_name}: {target}. Must be an integer between 0 and 10000 or 'default'."
            )

    @classmethod
    def alter_column_statistics_target(cls, operations: Operations, schema_name: str | None, table_name: str, column_name: str, new_value: TargetValue, prev_value: TargetValue | None = "default") -> Any:
        op = cls(schema_name, table_name, column_name, new_value, prev_value)
        return operations.invoke(op)

    def reverse(self) -> 'AlterColumnStatisticsTargetOp':
        return AlterColumnStatisticsTargetOp(
            schema_name=self.schema_name,
            table_name=self.table_name,
            column_name=self.column_name,
            new_target=self.prev_target if self.prev_target is not None else "default",
        )

@renderers.dispatch_for(AlterColumnStatisticsTargetOp)
def _alter_statistics_target(autogen_context: AutogenContext, op: AlterColumnStatisticsTargetOp) -> str:
    tmpl = (
        "%(prefix)salter_column_statistics_target(%(schema_name)r, %(table)r, %(columns)s, %(new_target)r, %(prev_target)r)"
    )

    if op.prev_target is None or op.prev_target == "default":
        tmpl = (
            "%(prefix)salter_column_statistics_target(%(schema_name)r, %(table)r, %(columns)s, %(new_target)r)"
        )

    return tmpl % {
        "prefix": _alembic_autogenerate_prefix(autogen_context),
        "schema_name": str(op.schema_name),
        "table": str(op.table_name),
        "columns": repr(op.column_name),
        "new_target": op.new_target,
        "prev_target": op.prev_target,
    }


@Operations.implementation_for(AlterColumnStatisticsTargetOp)
def _alter_column_statistics_target_impl(operations: Operations, operation: AlterColumnStatisticsTargetOp) -> None:
    logger.info(f"Executing ALTER TABLE {operation.schema_name}.{operation.table_name} ALTER COLUMN {operation.column_name} SET STATISTICS {operation.new_target}")

    operations.execute(
        f"ALTER TABLE {operation.schema_name}.{operation.table_name} ALTER COLUMN {operation.column_name} SET STATISTICS {operation.new_target}"
    )

def _get_column_stat_target(column: Column[Any]) -> str:
    return column.info.get("ext_stats", {}).get("target", "default")

def _load_table_metadata(autogen_context: AutogenContext, schema: str | None, tname: quoted_name | str, column_names: list[str]) -> dict[str, str | None]:
    connection = autogen_context.connection
    if connection is None:
        raise ValueError("Connection is not available in autogen_context")

    try:
        table_metadata = connection.execute(
            text(
                "SELECT attname, attstattarget FROM pg_attribute WHERE attrelid = (SELECT oid FROM pg_class WHERE relname = :table_name AND relnamespace::regnamespace::text = :schema_name) AND attname in :column_names"
            ),
            {
                "table_name": str(tname),
                "schema_name": str(schema or "public"),
                "column_names": tuple(column_names),
            },
        ).fetchall()
    except Exception as e:
        logger.warning(f"Error loading table metadata for '{tname}': {e}")
        return {}

    result: dict[str, str | None] = {}

    logger.debug(f"Loaded metadata for table '{tname}': {len(table_metadata)} columns found")
    for row in table_metadata:
        column_name = row.attname
        stat_target = row.attstattarget
        if stat_target == -1:
            stat_target = "default"
        else:
            stat_target = stat_target
        logger.debug(f"Loaded statistics for column '{tname}.{column_name}': {stat_target}")
        result[column_name] = stat_target

    return result

def compare_tables_column_statistics(
    autogen_context: AutogenContext,
    upgrade_ops: UpgradeOps,
    schema: str | None,
    tname: quoted_name | str,
    conn_table: Table[Any] | None,
    metadata_table: Table[Any] | None,
) -> PriorityDispatchResult:
    logger.debug(f"Comparing tables '{tname}'")
    if metadata_table is None:
        logger.debug(f"No metadata table found for '{tname}', skipping")
        return PriorityDispatchResult.CONTINUE

    existing_metadata = _load_table_metadata(autogen_context, schema, tname, list(metadata_table.columns.keys()))

    for cname, metadata_col in metadata_table.columns.items():
        stat_target = _get_column_stat_target(metadata_col)
        conn_stat_target = existing_metadata.get(cname, "default")

        if stat_target == conn_stat_target:
            logger.debug(f"No changes in statistics for column '{tname}.{cname}', skipping")
            continue

        # This is not a change because current target is default and there is no previous target
        if stat_target == "default" and conn_stat_target is None:
            logger.debug(f"Column '{tname}.{cname}' has no previous statistics target and is set to default, skipping")
            continue

        logger.info(f"Detected change in statistics for column '{tname}.{cname}': metadata target={stat_target}, connection target={conn_stat_target}")
        alter_column_op = AlterColumnStatisticsTargetOp(
            schema_name=schema,
            table_name=tname,
            column_name=cname,
            new_target=stat_target,
            prev_target=conn_stat_target,
        )
        upgrade_ops.ops.append(alter_column_op)

    return PriorityDispatchResult.CONTINUE