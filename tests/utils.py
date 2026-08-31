from typing import Any
from sqlalchemy import Connection, text


def get_pg_extended_stats(connection: Connection, schema: str | None, table_name: str) -> dict[str, dict[str, Any]]:
    """
    Returns existing extended statistics for a table in PostgreSQL.
    Result format: { stat_name: { 'kinds': set[str], 'columns': list[str], 'expressions': list[str], 'def_columns': str } }
    """
    schema_name = schema or "public"
    query = text("""
        SELECT
            s.stxname AS name,
            s.stxkind AS kinds,
            ARRAY(
                SELECT a.attname
                FROM unnest(s.stxkeys) WITH ORDINALITY AS k(attnum, ord)
                JOIN pg_attribute a ON a.attrelid = s.stxrelid AND a.attnum = k.attnum
                ORDER BY k.ord
            ) AS columns,
            pg_get_statisticsobjdef_expressions(s.oid) AS expressions,
            pg_get_statisticsobjdef_columns(s.oid) AS def_columns
        FROM pg_statistic_ext s
        JOIN pg_class c ON c.oid = s.stxrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = :schema_name AND c.relname = :table_name
    """)
    rows = connection.execute(query, {"schema_name": schema_name, "table_name": table_name}).fetchall()

    res: dict[str, dict[str, Any]] = {}
    # PostgreSQL stxkind stores char array: 'd' for ndistinct, 'f' for dependencies, 'm' for mcv, 'e' for expressions
    kind_map = {
        'd': 'NDISTINCT',
        'f': 'DEPENDENCIES',
        'm': 'MCV',
        'e': 'EXPRESSIONS',
    }
    for row in rows:
        kinds = {kind_map.get(k, k) for k in row.kinds}
        res[row.name] = {
            "kinds": kinds,
            "columns": list(row.columns),
            "expressions": list(row.expressions) if row.expressions is not None else [],
            "def_columns": row.def_columns,
        }
    return res


def get_pg_column_stat_target(connection: Connection, schema: str | None, table_name: str, column_name: str) -> int | None:
    """
    Returns attstattarget for a given column in PostgreSQL.
    None or -1 means default, or an integer 0-10000.
    """
    schema_name = schema or "public"
    query = text("""
        SELECT a.attstattarget
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = :schema_name AND c.relname = :table_name AND a.attname = :column_name
    """)
    res = connection.execute(query, {
        "schema_name": schema_name,
        "table_name": table_name,
        "column_name": column_name,
    }).scalar_one_or_none()
    return res
