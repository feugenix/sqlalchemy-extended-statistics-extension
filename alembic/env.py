from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context
from src.ext_stat_plugin_test.db import public_metadata, test_metadata
from src.ext_stat_plugin_test import all_repos  # noqa: F401

from alembic.runtime.plugins import Plugin
import plugin.main as ext_stat_plugin

# Register the plugin manually
Plugin.setup_plugin_from_module(
    ext_stat_plugin,
    "extended_statistics_plugin"
)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = test_metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            autogenerate_plugins=[
                "alembic.autogenerate.*",
                "extended_statistics_plugin",
            ],
            version_table_schema=target_metadata.schema,
            include_schemas=True,
        )

        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
