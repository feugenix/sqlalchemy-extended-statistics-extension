from alembic.autogenerate.api import AutogenContext

def _alembic_autogenerate_prefix(autogen_context: AutogenContext) -> str:
    return autogen_context.opts["alembic_module_prefix"] or ""
