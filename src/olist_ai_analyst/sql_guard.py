"""Check the SQL written by the LLM before it reaches the warehouse.

The read-only role already blocks writes; this guard gives the LLM a clear error message to
correct its query, and keeps results small.
"""

import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

MAX_ROWS = 1000
FORBIDDEN = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Command,
)


class UnsafeQueryError(ValueError):
    """The query is refused before execution; the message is shown to the LLM."""


def extract_sql(text: str) -> str:
    """Take the SQL out of an LLM reply: a ```sql block when there is one, else the whole text."""
    block = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    sql = block.group(1) if block else text
    return sql.strip().rstrip(";").strip()


def validate_sql(sql: str, allowed_tables: set[str], schema: str = "marts") -> str:
    """Return the query ready to run, or raise UnsafeQueryError with the reason."""
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except ParseError as exc:
        message = re.sub(r"\x1b\[[0-9;]*m", "", str(exc))  # drop the terminal colours
        raise UnsafeQueryError(f"The SQL does not parse: {message}") from exc
    if len(statements) != 1:
        raise UnsafeQueryError("Write exactly one SQL statement.")
    query = statements[0]
    if not isinstance(query, exp.Query):
        raise UnsafeQueryError("Only SELECT queries are allowed.")
    if any(query.find_all(*FORBIDDEN)):
        raise UnsafeQueryError("Only SELECT queries are allowed, nothing that writes or alters.")

    ctes = {cte.alias_or_name for cte in query.find_all(exp.CTE)}
    for table in query.find_all(exp.Table):
        if table.db and table.db != schema:
            raise UnsafeQueryError(f"Only tables of the {schema} schema are allowed: {table.sql()}")
        if table.name not in allowed_tables | ctes:
            known = ", ".join(sorted(allowed_tables))
            raise UnsafeQueryError(f"Unknown table {table.name}. Available tables: {known}.")

    limit = query.args.get("limit")
    limit_value = limit.expression if limit else None
    if not isinstance(limit_value, exp.Literal) or int(limit_value.this) > MAX_ROWS:
        query = query.limit(MAX_ROWS)
    return query.sql(dialect="postgres")
