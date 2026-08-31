from typing import Any
from logging import getLogger
from alembic.autogenerate.api import AutogenContext
from alembic.operations.ops import UpgradeOps
from alembic.util import PriorityDispatchResult
from sqlalchemy import quoted_name, Column, Table, text

from .operations import AlterColumnStatisticsTargetOp
from ..utils import coerce_to_quoted

logger = getLogger("alembic.plugins.ext_stats_plugin.column_statistics_target.alembic")


def _get_column_stat_target(column: Column[Any]) -> str:
    return str(column.info.get("ext_stats", {}).get("target", "default"))


def _load_table_metadata(autogen_context: AutogenContext, schema: str | None, tname: quoted_name | str, column_names: list[str]) -> dict[str, str | None]:
    connection = autogen_context.connection
    if connection is None:
        raise ValueError("Connection is not available in autogen_context")

    try:
        table_metadata = connection.execute(
            text(
                "SELECT attname, attstattarget FROM pg_attribute WHERE attrelid = (SELECT oid FROM pg_class WHERE relname = :table_name AND relnamespace::regnamespace::text = :schema_name) AND attname = ANY(ARRAY[:column_names])"
            ),
            {
                "table_name": str(tname),
                "schema_name": str(schema or "public"),
                "column_names": [str(c) for c in column_names],
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

    if conn_table is not None:
        existing_metadata = _load_table_metadata(autogen_context, schema, tname, list(metadata_table.columns.keys()))
    else:
        existing_metadata = {}

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
