# ext-stat-plugin

Alembic & SQLAlchemy plugin for PostgreSQL extended statistics (`CREATE STATISTICS` / `DROP STATISTICS`) and column statistics targets (`ALTER TABLE ... ALTER COLUMN ... SET STATISTICS`).

## Overview

PostgreSQL allows tuning query planner statistics beyond single-column defaults:
- **Extended Statistics**: Captures multi-column correlations, n-distinct coefficients, and most common values (`MCV`) across multiple columns or expressions.
- **Column Statistics Targets**: Adjusts the sample size and histogram detail for individual columns (`0` to `10000`, or `'default'`).

`ext-stat-plugin` lets you define extended statistics and column statistics targets declaratively in SQLAlchemy models and automatically generates Alembic migrations (`autogenerate`) for them.

---

## Features

- **Declarative Extended Statistics**: Define statistics objects directly on SQLAlchemy `Table` or `DeclarativeBase` models with `ExtendedStatistics`.
- **Supports All PostgreSQL Statistics Kinds**: `NDISTINCT`, `DEPENDENCIES`, and `MCV`.
- **Supports Column Names and Expressions**: Pass string column names or SQLAlchemy expression objects (e.g. `func.lower(...)`, `col1 + col2`).
- **Column Statistics Targets**: Set statistics target via `Column(..., info={"ext_stats": {"target": ...}})`.
- **Alembic Autogenerate**: Compares database state against your SQLAlchemy metadata to generate `create_statistics`, `drop_statistics`, and `alter_column_statistics_target` operations.
- **Reversible Migrations**: Supports seamless Alembic `upgrade()` and `downgrade()`.

---

## Installation

```bash
uv add ext-stat-plugin
# or
pip install ext-stat-plugin
```

---

## Alembic Setup

To enable autogeneration for extended statistics and column targets, import `ext_stat_plugin` in your Alembic `env.py`:

```python
# env.py
import ext_stat_plugin  # noqa: F401
from alembic.runtime.plugins import Plugin
import ext_stat_plugin.main as ext_stat_plugin_main

# If not using automatic plugin discovery:
Plugin.setup_plugin_from_module(ext_stat_plugin_main, "extended_statistics_plugin")
```

---

## Usage Examples

### 1. Extended Statistics on SQLAlchemy Models

```python
from sqlalchemy import Column, Integer, MetaData, String, Table, func
from ext_stat_plugin import ExtendedStatistics, NDISTINCT, MCV, DEPENDENCIES

metadata = MetaData()

# Define table with multi-column extended statistics
orders = Table(
    "orders",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer),
    Column("city", String(50)),
    Column("state", String(50)),
    # Extended statistics with custom name and multiple kinds
    ExtendedStatistics(
        "orders_city_state_stats",
        [NDISTINCT, DEPENDENCIES],
        "city",
        "state",
    ),
    # Auto-generated statistics name (public_orders_user_id_city_stats)
    ExtendedStatistics(None, [MCV], "user_id", "city"),
)

# Extended statistics with expressions
metrics = Table(
    "metrics",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("tag", String(50)),
    Column("val1", Integer),
    Column("val2", Integer),
    ExtendedStatistics(
        "metrics_expr_stat",
        [NDISTINCT, MCV],
        "(lower(tag))",
        "(val1 + val2)",
    ),
)
```

### 2. Column Statistics Target

Set the target directly in the column's `info` dictionary:

```python
from sqlalchemy import Column, Integer, MetaData, String, Table

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    # Set sample target to 1000 for high-cardinality/critical column
    Column("age", Integer, info={"ext_stats": {"target": 1000}}),
    Column("name", String(50)),
)
```

### 3. Generated Alembic Migrations

When running `alembic revision --autogenerate`, migrations will include:

```python
"""create statistics and alter column targets

Revision ID: 1234567890ab
"""

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    # Column target update
    op.alter_column_statistics_target("public", "users", "age", 1000)

    # Extended statistics creation
    op.create_statistics(
        "public",
        "orders",
        "orders_city_state_stats",
        ["NDISTINCT", "DEPENDENCIES"],
        "city",
        "state",
    )


def downgrade() -> None:
    # Drop extended statistics
    op.drop_statistics("public", "orders", "orders_city_state_stats")

    # Reset column target to default
    op.alter_column_statistics_target("public", "users", "age", "default", 1000)
```

---

## Development

Run tests, type-checking, and linting with `uv`:

```bash
# Run unit tests
uv run pytest tests/unit

# Run all tests (including PostgreSQL integration tests)
uv run pytest

# Type checking
uv run mypy .

# Linting & Formatting
uv run ruff check .
uv run ruff format --check .
```
