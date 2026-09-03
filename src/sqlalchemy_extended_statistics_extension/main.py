from logging import getLogger

from alembic.runtime.plugins import Plugin

from .column_statistics_target.alembic import compare_tables_column_statistics
from .extended_statistic.alembic import compare_tables_extended_statistics

logger = getLogger("alembic.plugins.sqlalchemy_extended_statistics_extension.main")


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
