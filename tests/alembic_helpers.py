import os
import shutil
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.plugins import Plugin
from sqlalchemy import MetaData
from sqlalchemy.engine import Engine

import ext_stat_plugin.main as ext_stat_plugin_main


class AlembicRunner:
    def __init__(
        self,
        engine: Engine,
        target_metadata: MetaData | list[MetaData],
        schema: str | None = None,
    ):
        self.engine = engine
        self.target_metadata = target_metadata
        self.schema = schema
        self.temp_dir = tempfile.mkdtemp()
        self.versions_dir = os.path.join(self.temp_dir, "versions")
        os.makedirs(self.versions_dir, exist_ok=True)

        self.ini_path = os.path.join(self.temp_dir, "alembic.ini")
        self.env_py_path = os.path.join(self.temp_dir, "env.py")
        self.script_mako_path = os.path.join(self.temp_dir, "script.py.mako")

        self._setup_files()
        self.config = self._create_config()

        # Register plugin only if not already registered
        try:
            Plugin.setup_plugin_from_module(
                ext_stat_plugin_main, "extended_statistics_plugin"
            )
        except ValueError:
            pass

    def _setup_files(self):
        # Write alembic.ini
        with open(self.ini_path, "w") as f:
            f.write(f"""[alembic]
script_location = {self.temp_dir}
prepend_sys_path = .
version_locations = {self.versions_dir}
path_separator = os
sqlalchemy.url = {self.engine.url.render_as_string(hide_password=False)}
""")

        # Write script.py.mako
        with open(self.script_mako_path, "w") as f:
            f.write('''"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, Sequence[str], None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    """Upgrade schema."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Downgrade schema."""
    ${downgrades if downgrades else "pass"}
''')

        # Write env.py
        with open(self.env_py_path, "w") as f:
            f.write("""from alembic import context
from sqlalchemy import engine_from_config, pool
import ext_stat_plugin

config = context.config
target_metadata = config.attributes.get("target_metadata")
version_table_schema = config.attributes.get("version_table_schema")

def run_migrations_online() -> None:
    connectable = config.attributes.get("connection", None)
    if connectable is None:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    def include_object(object, name, type_, reflected, compare_to):
        if type_ == "table" and name == "alembic_version":
            return False
        return True

    if hasattr(connectable, "connect"):
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                include_object=include_object,
                autogenerate_plugins=[
                    "alembic.autogenerate.*",
                    "extended_statistics_plugin",
                ],
                version_table_schema=version_table_schema,
                include_schemas=True,
            )

            with context.begin_transaction():
                context.run_migrations()
    else:
        context.configure(
            connection=connectable,
            target_metadata=target_metadata,
            include_object=include_object,
            autogenerate_plugins=[
                "alembic.autogenerate.*",
                "extended_statistics_plugin",
            ],
            version_table_schema=version_table_schema,
            include_schemas=True,
        )

        with context.begin_transaction():
            context.run_migrations()

run_migrations_online()
""")

    def _create_config(self) -> Config:
        cfg = Config(self.ini_path)
        cfg.set_main_option("script_location", self.temp_dir)
        cfg.attributes["target_metadata"] = self.target_metadata
        cfg.attributes["version_table_schema"] = self.schema
        return cfg

    def set_metadata(self, target_metadata: MetaData | list[MetaData]):
        self.target_metadata = target_metadata
        self.config.attributes["target_metadata"] = target_metadata

    def autogenerate(self, message: str = "autogen") -> str:
        """Runs autogenerate revision and returns the generated revision script content."""
        with self.engine.connect() as conn:
            self.config.attributes["connection"] = conn
            command.revision(self.config, message=message, autogenerate=True)
        # Find the latest generated file in versions_dir
        rev_files = list(Path(self.versions_dir).glob("*.py"))
        latest_file = max(rev_files, key=os.path.getctime)
        with open(latest_file, "r") as f:
            return f.read()

    def upgrade(self, revision: str = "head") -> None:
        """Upgrades the database to the specified revision."""
        with self.engine.connect() as conn:
            self.config.attributes["connection"] = conn
            command.upgrade(self.config, revision)

    def downgrade(self, revision: str = "-1") -> None:
        """Downgrades the database."""
        with self.engine.connect() as conn:
            self.config.attributes["connection"] = conn
            command.downgrade(self.config, revision)

    def cleanup(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
