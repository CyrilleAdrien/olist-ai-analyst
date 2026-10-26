"""Check the SQL written by the LLM before it reaches the warehouse.

The read-only role already blocks writes; this guard gives the LLM a clear error message to
correct its query, and keeps results small.
"""

import difflib
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


def _where_is(column: str, tables: dict[str, set[str]]) -> str:
    """Point the LLM to the tables that hold this column, or to close names."""
    exact = [f"{table}.{column}" for table, cols in sorted(tables.items()) if column in cols]
    if exact:
        return f" It exists in: {', '.join(exact)}."
    every = [f"{table}.{col}" for table, cols in sorted(tables.items()) for col in sorted(cols)]
    # "state" -> customer_state, seller_state; then close spellings such as "delivry_days"
    near = [c for c in every if c.split(".")[1].endswith(f"_{column}")]
    if not near:
        names = [c.split(".")[1] for c in every]
        close = difflib.get_close_matches(column, names, n=2, cutoff=0.8)
        near = [c for c in every if c.split(".")[1] in close]
    return f" Did you mean: {', '.join(near)}?" if near else ""


def _check_columns(query: exp.Query, tables: dict[str, set[str]]) -> None:
    """Refuse columns that do not exist, the most common mistake of small models."""
    if any(query.find_all(exp.Subquery)) or any(query.find_all(exp.CTE)):
        return  # derived tables have columns we do not know: let PostgreSQL check them
    aliases = {t.alias_or_name: t.name for t in query.find_all(exp.Table)}
    output_names = {e.alias_or_name for e in query.find_all(exp.Alias)}
    used = {aliases[a] for a in aliases}
    for column in query.find_all(exp.Column):
        name, qualifier = column.name, column.table
        if qualifier:
            table = aliases.get(qualifier)
            if table is None:
                raise UnsafeQueryError(f"Unknown table or alias {qualifier} in {column.sql()}.")
            if name not in tables[table]:
                raise UnsafeQueryError(
                    f"Column {name} does not exist in {table}.{_where_is(name, tables)}"
                    " Join the table that holds it."
                )
        elif name not in output_names and not any(name in tables[t] for t in used):
            raise UnsafeQueryError(
                f"Column {name} does not exist in {', '.join(sorted(used))}."
                f"{_where_is(name, tables)} Join the table that holds it."
            )


def validate_sql(sql: str, tables: dict[str, set[str]], schema: str = "marts") -> str:
    """Return the query ready to run, or raise UnsafeQueryError with the reason.

    `tables` maps each table the agent may read to its columns.
    """
    allowed_tables = set(tables)
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

    _check_columns(query, tables)
    for aggregate in query.find_all(exp.Sum, exp.Avg):
        column = aggregate.this
        if isinstance(column, exp.Column) and column.name.endswith("_id"):
            raise UnsafeQueryError(
                f"{column.name} is an identifier or a position, not a quantity: do not "
                f"{aggregate.key} it. To count rows, use count(*) or count(distinct ...)."
            )

    limit = query.args.get("limit")
    limit_value = limit.expression if limit else None
    if not isinstance(limit_value, exp.Literal) or int(limit_value.this) > MAX_ROWS:
        query = query.limit(MAX_ROWS)
    return query.sql(dialect="postgres")
