from collections.abc import Sequence
from logging import getLogger
from typing import Any, Literal

from sqlalchemy import ColumnElement, Table
from sqlalchemy.schema import SchemaItem
from sqlalchemy.sql.base import SchemaEventTarget

StatisticsKind = Literal["NDISTINCT", "DEPENDENCIES", "MCV"]

NDISTINCT: StatisticsKind = "NDISTINCT"
DEPENDENCIES: StatisticsKind = "DEPENDENCIES"
MCV: StatisticsKind = "MCV"

logger = getLogger("alembic.plugins.sqlalchemy_extended_statistics_extension.extended_statistics.sqlalchemy")


def _get_expression_name(expression: str | ColumnElement[Any]) -> str:
    if isinstance(expression, str):
        return expression

    return "expr"


def _get_default_statistics_name(
    schema_name: str | None, table_name: str, *expressions: str | ColumnElement[Any]
) -> str:
    expressions_names = "_".join(_get_expression_name(expr) for expr in expressions)
    return f"{schema_name or 'public'}_{table_name}_{expressions_names}_stats"


class ExtendedStatistics(SchemaItem):
    table: Table
    kind: set[StatisticsKind]

    def __init__(
        self,
        statistics_name: str | None,
        kind: Sequence[StatisticsKind] | None = None,
        *expressions: str | ColumnElement[Any],
    ) -> None:
        self.name = statistics_name
        self.kind = set(kind) if kind is not None else {"NDISTINCT"}
        self.expressions = expressions

        logger.info(
            f"Creating ExtendedStatistics: name={statistics_name}, kind={kind}, expressions={expressions}"
        )

    def _set_parent(self, parent: SchemaEventTarget, **kw: Any):
        table = parent
        assert isinstance(table, Table)
        self.table = table

        existing_stats = getattr(table, "__ext_stats__", None)
        if existing_stats is None:
            existing_stats = []
        existing_stats.append(self)
        setattr(table, "__ext_stats__", existing_stats)  # noqa: B010

        if self.name is None:
            self.name = _get_default_statistics_name(
                table.schema, table.name, *self.expressions
            )
        logger.info(f"ExtendedStatistics added to table '{table.name}'")
