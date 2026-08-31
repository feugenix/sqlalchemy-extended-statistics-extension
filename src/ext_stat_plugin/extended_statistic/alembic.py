from sqlalchemy import Connection, Table, text
from alembic.autogenerate.api import AutogenContext
from alembic.operations.ops import UpgradeOps
from alembic.util import PriorityDispatchResult
from sqlalchemy import Table, quoted_name
from logging import getLogger
from typing import Any

from .operations import CreateStatisticsOp, DropStatisticsOp
from .sqlalchemy import ExtendedStatistics
from ..utils import coerce_to_quoted


logger = getLogger("alembic.plugins.ext_stats_plugin.extended_statistics.alembic")

def _get_table_ext_stats(metadata_table: Table[Any]) -> list[ExtendedStatistics]:
    return getattr(metadata_table, "__ext_stats__", [])

KIND_MAP_FROM_PG = {
    "d": "NDISTINCT",
    "f": "DEPENDENCIES",
    "m": "MCV",
}


def _load_existing_table_statistics(conn: Connection | None, schema_name: str | None, table_name: str) -> dict[str, dict[str, Any]]:
    if conn is None:
        logger.warning(f"Connection is not available for loading existing statistics for table '{table_name}'")
        return {}

    try:
        table_metadata = conn.execute(
            text(
                """
                SELECT
                    s.stxname AS statistics_name,
                    s.stxkind AS kinds,
                    pg_get_statisticsobjdef_columns(s.oid) AS cols_def
                FROM pg_statistic_ext s
                JOIN pg_class c ON c.oid = s.stxrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = :table_name AND n.nspname = :schema_name
                """
            ),
            {
                "table_name": str(table_name),
                "schema_name": str(schema_name or "public"),
            },
        ).fetchall()
    except Exception as e:
        logger.warning(f"Error loading existing statistics for table '{table_name}': {e}")
        return {}

    result = {}
    for row in table_metadata:
        kinds = {KIND_MAP_FROM_PG[k] for k in row.kinds if k in KIND_MAP_FROM_PG}
        result[row.statistics_name] = {
            "kind": kinds,
            "expressions": (row.cols_def,) if row.cols_def else (),
        }
    return result

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

    statistics_from_db = _load_existing_table_statistics(autogen_context.connection, schema, str(tname))
    statistics_from_metadata: list[ExtendedStatistics] = [stat for stat in _get_table_ext_stats(metadata_table)]

    if not statistics_from_metadata and not statistics_from_db:
        logger.info("No extended statistics found. Skipping it.")
        return PriorityDispatchResult.CONTINUE

    for stat_name, stat_info in statistics_from_db.items():
        logger.debug(f"Statistics '{stat_name}' exists in database. Dropping it.")
        upgrade_ops.ops.append(
            DropStatisticsOp(
                schema_name=schema,
                statistics_name=stat_name,
                table_name=str(tname),
                kind=stat_info["kind"],
                expressions=stat_info["expressions"],
            )
        )

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

    return PriorityDispatchResult.CONTINUE