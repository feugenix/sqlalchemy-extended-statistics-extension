from alembic.runtime.plugins import Plugin
from logging import getLogger
from .table_statistics import compare_tables_column_statistics
from .extended_stat import compare_tables_extended_statistics

logger = getLogger("alembic.plugins.ext_stats_plugin.main")

def setup(plugin: Plugin) -> None:
    logger.debug("Setting up extended statistics plugin")

    plugin.add_autogenerate_comparator(
        compare_tables_column_statistics,
        compare_target="table",
        qualifier="postgresql",
    )

    plugin.add_autogenerate_comparator(
        compare_tables_extended_statistics,
        compare_target="table",
        qualifier="postgresql",
    )