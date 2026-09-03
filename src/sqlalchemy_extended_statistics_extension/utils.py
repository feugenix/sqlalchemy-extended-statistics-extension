from alembic.autogenerate.api import AutogenContext


def get_alembic_autogenerate_prefix(autogen_context: AutogenContext) -> str:
    return autogen_context.opts.get("alembic_module_prefix", "op.")


def strip_double_quotes(sql: str) -> str:
    """
    Removes starting and ending double quotes
    Taken from alembic_utils (https://github.com/olirice/alembic_utils)
    """
    sql = sql.strip().rstrip('"')
    return sql.strip().lstrip('"').strip()


def coerce_to_quoted(text: str) -> str:
    """Coerces schema and entity names to double quoted one

    Examples:
        coerce_to_quoted('"public"') => '"public"'
        coerce_to_quoted('public') => '"public"'
        coerce_to_quoted('public.table') => '"public"."table"'
        coerce_to_quoted('"public".table') => '"public"."table"'
        coerce_to_quoted('public."table"') => '"public"."table"'

    Taken from alembic_utils (https://github.com/olirice/alembic_utils)
    """
    if "." in text:
        schema, _, name = text.partition(".")
        schema = f'"{strip_double_quotes(schema)}"'
        name = f'"{strip_double_quotes(name)}"'
        return f"{schema}.{name}"

    text = strip_double_quotes(text)
    return f'"{text}"'
