from typing import Any
from alembic.operations import Operations, MigrateOperation
from alembic.autogenerate.api import AutogenContext
from alembic.autogenerate import renderers
from logging import getLogger
from ..utils import get_alembic_autogenerate_prefix, coerce_to_quoted

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
    def alter_column_statistics_target(cls, operations: Operations, schema_name: str | None, table_name: str, column_name: str, new_target: TargetValue, prev_target: TargetValue | None = "default") -> Any:
        op = cls(schema_name, table_name, column_name, new_target, prev_target)
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
        "prefix": get_alembic_autogenerate_prefix(autogen_context),
        "schema_name": str(op.schema_name),
        "table": str(op.table_name),
        "columns": repr(op.column_name),
        "new_target": op.new_target,
        "prev_target": op.prev_target,
    }


@Operations.implementation_for(AlterColumnStatisticsTargetOp)
def _alter_column_statistics_target_impl(operations: Operations, operation: AlterColumnStatisticsTargetOp) -> None:
    logger.info(f"Executing ALTER TABLE {operation.schema_name}.{operation.table_name} ALTER COLUMN {operation.column_name} SET STATISTICS {operation.new_target}")

    quoted_schema = coerce_to_quoted(operation.schema_name)
    quoted_table_name = coerce_to_quoted(operation.table_name)
    quoted_column_name = coerce_to_quoted(operation.column_name)
    operations.execute(
        f"ALTER TABLE {quoted_schema}.{quoted_table_name} ALTER COLUMN {quoted_column_name} SET STATISTICS {operation.new_target}"
    )