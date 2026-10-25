"""Read-only access to the Olist warehouse."""

from dataclasses import dataclass
from typing import Any

import psycopg

from olist_ai_analyst.config import Settings


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple[Any, ...]]


def connect(settings: Settings) -> psycopg.Connection:
    """Open a connection that can only read the marts schema, with a statement timeout.

    The read-only role is the real protection; the session options are a second layer.
    """
    options = (
        "-c default_transaction_read_only=on"
        f" -c statement_timeout={settings.statement_timeout_ms}"
        f" -c search_path={settings.agent_db_schema}"
    )
    return psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.agent_db_user,
        password=settings.agent_db_password.get_secret_value(),
        options=options,
        connect_timeout=5,
    )


def run_query(settings: Settings, sql: str, params: dict[str, Any] | None = None) -> QueryResult:
    with connect(settings) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        columns = [col.name for col in cur.description or []]
        return QueryResult(columns=columns, rows=cur.fetchall())
